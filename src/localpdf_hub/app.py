"""Builds the FastAPI application: guard, API, error format and the UI."""

import asyncio
import logging
import mimetypes
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pypdf.errors import FileNotDecryptedError, PdfReadError

from localpdf_hub import __version__, api, errors, settings, workspace
from localpdf_hub.errors import AppError
from localpdf_hub.security import RequestGuard, SecurityHeaders

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    await asyncio.to_thread(workspace.sweep_stale)
    sweeper = asyncio.create_task(_sweep_every_hour())
    try:
        yield
    finally:
        sweeper.cancel()
        with suppress(asyncio.CancelledError):
            await sweeper


async def _sweep_every_hour() -> None:
    # Catches folders whose response never finished, e.g. a closed tab.
    while True:
        await asyncio.sleep(settings.STALE_AFTER_S)
        await asyncio.to_thread(workspace.sweep_stale)


class _RevalidatedFiles(StaticFiles):
    """Static files the browser must revalidate on every load.

    Without a Cache-Control header browsers keep scripts by heuristic, so
    after an update a user could keep running the old JavaScript. On
    localhost the ETag check costs nothing.
    """

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


def _error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"code": code, "message": message}, status_code=status)


def create_app() -> FastAPI:
    # On Windows, mimetypes reads the registry, where some installs map .js to
    # text/plain; browsers then refuse to run the UI's ES modules.
    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("text/javascript", ".mjs")
    token = secrets.token_urlsafe(32)
    # The interactive docs would publish a map of every endpoint to any local page.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=_lifespan)
    # No CORSMiddleware on purpose: the UI is served from this same origin,
    # and approving preflights is what would let a foreign page send the token.
    app.add_middleware(RequestGuard, token=token)
    # Added last, so it is outermost and also covers the guard's own answers.
    app.add_middleware(SecurityHeaders)
    app.include_router(api.router)

    @app.exception_handler(AppError)
    async def app_error(_: Request, error: AppError) -> JSONResponse:
        return _error(error.code, error.message, error.status)

    # Second line behind the check in limits.check_page_limit. Starlette picks the
    # handler of the most specific class, so this wins over PdfReadError.
    @app.exception_handler(FileNotDecryptedError)
    async def encrypted_pdf(_: Request, error: FileNotDecryptedError) -> JSONResponse:
        return _error(errors.ENCRYPTED, "The PDF needs a password to open.", 400)

    @app.exception_handler(PdfReadError)
    async def unreadable_pdf(_: Request, error: PdfReadError) -> JSONResponse:
        return _error(errors.INVALID_PDF, f"The PDF could not be read: {error}", 400)

    @app.exception_handler(RequestValidationError)
    async def invalid_form(_: Request, error: RequestValidationError) -> JSONResponse:
        fields = ", ".join(str(item["loc"][-1]) for item in error.errors())
        return _error(errors.INVALID_INPUT, f"Missing or invalid fields: {fields}", 400)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, error: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=error)
        return _error(errors.INTERNAL, "Something went wrong on our side.", 500)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    async def index() -> HTMLResponse:
        html = (settings.FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
        meta = f'<meta name="localpdf-token" content="{token}">'
        # no-store: a cached page would keep a token that dies on the next launch.
        return HTMLResponse(
            html.replace("<head>", f"<head>\n  {meta}", 1),
            headers={"Cache-Control": "no-store"},
        )

    # Before the static mount, so these paths never serve the file without the token.
    app.add_api_route("/", index, methods=["GET"], include_in_schema=False)
    app.add_api_route("/index.html", index, methods=["GET"], include_in_schema=False)
    app.mount("/", _RevalidatedFiles(directory=settings.FRONTEND_DIR, html=True), name="ui")
    return app
