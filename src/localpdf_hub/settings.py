"""Runtime settings.

Other modules read these as `settings.NAME` at call time rather than
importing the values, so tests and the LAN switch can change them.
"""

import os
import sys
from pathlib import Path

import platformdirs


def _frontend_dir() -> Path:
    if getattr(sys, "frozen", False):
        # PyInstaller sets _MEIPASS at runtime to the unpacked bundle folder.
        return Path(sys._MEIPASS) / "frontend"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2] / "frontend"


FRONTEND_DIR = _frontend_dir()

# The packaged app has no console to pass flags to, so LAN access is
# switched on through the environment.
LAN_IP = os.environ.get("LOCALPDF_LAN", "").strip()
HOST = "0.0.0.0" if LAN_IP else "127.0.0.1"  # noqa: S104 -- only when LAN access is asked for
PORT = 8000

# A per-user folder instead of the program folder, which Windows does not
# let normal users write to and which must stay untouched inside a .app.
TEMP_DIR = Path(
    os.environ.get("LOCALPDF_TEMP_DIR")
    or Path(platformdirs.user_cache_dir("LocalPDF-Hub", appauthor=False)) / "jobs"
)
LOG_FILE = Path(platformdirs.user_log_dir("LocalPDF-Hub", appauthor=False)) / "localpdf.log"
STALE_AFTER_S = 3600

MAX_UPLOAD_BYTES = 500 * 1024 * 1024

# Measured on a 555 MB, 500-page PDF: PDF to Word peaked at 2.15 GB and
# merge at 1.66 GB, so those tools take the whole job gate. 300 s is about
# twice the slowest run on Apple Silicon, for slower office PCs.
JOB_CAPACITY = 2
JOB_TIMEOUT_S = 300.0
MAX_PAGES = 2000
MAX_RENDER_PIXELS = 50_000_000
