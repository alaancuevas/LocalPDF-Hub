"""Request guard behaviour that the HTTP test client cannot show."""

import asyncio

from localpdf_hub.security import RequestGuard


def _refused_post(chunks: list[bytes], content_length: int) -> list[str]:
    events = []

    async def app(scope, receive, send):
        raise AssertionError("a refused request must not reach the app")

    async def receive():
        events.append("read")
        body = chunks.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(chunks)}

    async def send(message):
        events.append(message["type"])

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/pdf/compress",
        "headers": [
            (b"host", b"127.0.0.1:8000"),
            (b"content-length", str(content_length).encode()),
        ],
    }
    asyncio.run(RequestGuard(app, "token")(scope, receive, send))
    return events


def test_a_refused_upload_is_read_before_the_answer():
    # Windows resets a connection closed with unread data, and the client
    # then loses the 403 that tells the page to reload.
    events = _refused_post([b"a" * 10, b"b" * 10], 20)
    assert events[:3] == ["read", "read", "http.response.start"]


def test_an_upload_over_the_limit_is_refused_unread(monkeypatch):
    from localpdf_hub import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 10)
    events = _refused_post([b"a" * 20], 20)
    assert "read" not in events
    assert events[0] == "http.response.start"


def test_an_upload_with_the_token_over_the_limit_is_also_refused_unread(monkeypatch):
    # A valid token does not skip the size check: nothing past the limit is read.
    from localpdf_hub import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 10)
    read, sent = [], []

    async def app(scope, receive, send):
        raise AssertionError("an oversized request must not reach the app")

    async def receive():
        read.append(True)
        return {"type": "http.request", "body": b"a" * 20, "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/pdf/compress",
        "headers": [
            (b"host", b"127.0.0.1:8000"),
            (b"x-localpdf-token", b"token"),
            (b"content-length", b"20"),
        ],
    }
    asyncio.run(RequestGuard(app, "token")(scope, receive, send))
    assert read == []
    assert sent[0]["status"] == 413
