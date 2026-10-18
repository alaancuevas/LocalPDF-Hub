"""Desktop entry point: start the server, open the browser, show a tray icon."""

import logging
import os
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn
from PIL import Image

from localpdf_hub import settings
from localpdf_hub.app import create_app

logger = logging.getLogger(__name__)


def main() -> None:
    _keep_streams_open()
    _setup_logging()
    url = f"http://127.0.0.1:{settings.PORT}"
    logger.info("Starting LocalPDF Hub on %s", url)

    server = threading.Thread(
        target=uvicorn.run,
        args=(create_app(),),
        kwargs={"host": settings.HOST, "port": settings.PORT, "use_colors": False},
        daemon=True,
    )
    server.start()
    webbrowser.open(url)
    _run_tray()
    # _run_tray returns only when no tray icon could be shown; the server
    # thread is a daemon, so without this join the app would exit at once.
    server.join()


def _keep_streams_open() -> None:
    # A windowed PyInstaller build has no console: stdout and stderr are None
    # and uvicorn's logging would crash writing to them.
    if sys.stdout is None:
        sys.stdout = Path(os.devnull).open("w")  # noqa: SIM115 -- lives as long as the process
    if sys.stderr is None:
        sys.stderr = Path(os.devnull).open("w")  # noqa: SIM115 -- lives as long as the process


def _setup_logging() -> None:
    settings.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(settings.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def _run_tray() -> None:
    try:
        import pystray
    except ImportError:
        return
    try:
        image = Image.open(settings.FRONTEND_DIR / "icon.ico")
        menu = pystray.Menu(pystray.MenuItem("Quit LocalPDF Hub", _quit))
        pystray.Icon("LocalPDF Hub", image, "LocalPDF Hub", menu).run()
    except Exception:  # noqa: BLE001 -- no tray (e.g. a headless session) is not fatal
        logger.warning("Tray icon unavailable; the server keeps running", exc_info=True)


def _quit(icon: Any, _item: object) -> None:
    icon.stop()
    # uvicorn runs in a daemon thread and has no stop hook here; ending the
    # process is the only way to free the port immediately.
    os._exit(0)
