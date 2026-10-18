"""Request guard for the local server.

Any page open in the user's browser can send a "simple" multipart POST to
127.0.0.1 without a CORS preflight, so being on loopback is not enough.
Unsafe requests must carry the launch token in a custom header: a foreign
page cannot add that header without a preflight, and the server never
answers preflights with CORS approval.
"""

import hmac
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse

from localpdf_hub import settings

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

TOKEN_HEADER = "x-localpdf-token"  # noqa: S105 -- a header name, not a secret
SAFE_METHODS = frozenset({"GET", "HEAD"})
SAME_SITE_FETCH = frozenset({"same-origin", "none"})


def _allowed_hosts() -> set[str]:
    hosts = {"127.0.0.1", "localhost", "::1"}
    if settings.LAN_IP:
        hosts.add(settings.LAN_IP)
    return hosts


def _allowed_origins() -> set[str]:
    port = settings.PORT
    origins = {f"http://{host}:{port}" for host in _allowed_hosts() if host != "::1"}
    return origins | {f"http://[::1]:{port}"}


def _host_name(host_header: str) -> str:
    if host_header.startswith("["):
        return host_header[1 : host_header.find("]")]
    return host_header.split(":")[0]


class RequestGuard:
    """Rejects requests that could come from another site or overflow the disk."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        # Checking Host defeats DNS rebinding: a hostile domain resolved to
        # 127.0.0.1 would otherwise be able to read index.html and its token.
        if _host_name(headers.get("host", "")) not in _allowed_hosts():
            await PlainTextResponse("Invalid Host header", status_code=400)(scope, receive, send)
            return

        if scope["method"] not in SAFE_METHODS and not self._is_trusted(headers):
            await PlainTextResponse("Forbidden", status_code=403)(scope, receive, send)
            return

        limit = settings.MAX_UPLOAD_BYTES
        declared = headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            await PlainTextResponse("Payload Too Large", status_code=413)(scope, receive, send)
            return

        received = 0
        response_started = False
        rejected = False

        # Chunked bodies have no Content-Length, so the limit is enforced
        # while the multipart parser pulls the body, before it hits disk.
        # FastAPI turns any exception raised during body parsing into a 400,
        # so instead of raising we answer 413 here and tell the app the
        # client is gone; whatever the app sends afterwards is dropped.
        async def counting_receive() -> Message:
            nonlocal received, rejected
            message = await receive()
            if message["type"] == "http.request" and not rejected:
                received += len(message.get("body", b""))
                if received > limit and not response_started:
                    rejected = True
                    await PlainTextResponse("Payload Too Large", status_code=413)(
                        scope, receive, send
                    )
            if rejected:
                return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if rejected:
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        await self.app(scope, counting_receive, guarded_send)

    def _is_trusted(self, headers: Headers) -> bool:
        token = headers.get(TOKEN_HEADER, "")
        if not hmac.compare_digest(token.encode(), self.token.encode()):
            return False
        origin = headers.get("origin")
        if origin is not None and origin not in _allowed_origins():
            return False
        fetch_site = headers.get("sec-fetch-site")
        return fetch_site is None or fetch_site in SAME_SITE_FETCH
