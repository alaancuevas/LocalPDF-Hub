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
# Images (Apple M4): 250 HEIC photos of 12 MP took 129 s and peaked at
# 1.45 GB; 20 TIFFs of 50 MP kept lossless took 42 s and peaked at 1.74 GB.
JOB_CAPACITY = 2
JOB_TIMEOUT_S = 300.0
MAX_PAGES = 2000
MAX_RENDER_PIXELS = 50_000_000
# Each image costs about 0.5 s per 12 MP to decode; PDFs are bounded by MAX_PAGES.
MAX_IMAGES = 200
# Lossless noisy photos grow to about 65 MB per 50 MP image, and PdfWriter
# holds the whole result in memory: 120 of them gave 6.5 GB and a 7.1 GB peak.
# With this cap, 500 MB of 50 MP TIFFs (Apple M4) peaked at 1.95 GB for a
# 1.3 GB result (q90, 47 s) and at 2.31 GB when stopped (q25, 51 s).
MAX_RESULT_BYTES = 1536 * 1024 * 1024
# Compress, recommended and extreme (Apple M4): the costliest honest input measured, 1853
# letter scans at 300 dpi, decodes 3.9 GP in 13 s; 1820 near-50 MP JPEGs that draft cannot
# shrink stop at the 20 GP budget in 116 s. One 49 MP image takes at most 2.1 s and 1.3 GB
# (11 scans, 4:4:4, a 46 in page); a JPEG with more scans stays as it is. MAX_WORK bounds the
# dictionary walk.
COMPRESS_MAX_WORK = 1_000_000
COMPRESS_PIXEL_BUDGET = 20_000_000_000
COMPRESS_SOFT_SECONDS = JOB_TIMEOUT_S / 2
COMPRESS_MAX_SCANS = 11
IMAGE_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".jfif", ".jif", ".heic", ".heif", ".tif", ".tiff"}
)
