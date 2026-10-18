"""Per-job folders for uploads and results."""

import re
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import UploadFile

from localpdf_hub import settings

_UNSAFE = re.compile(r"[^\w.\- ]")
_MAX_NAME = 120
_UPLOAD_PREFIX = re.compile(r"^\d{3}_")


def new_job_dir() -> Path:
    settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=settings.TEMP_DIR))


def safe_name(name: str | None, fallback: str = "file") -> str:
    """Keeps a name usable on every OS and unable to leave its folder."""
    base = Path((name or "").replace("\\", "/")).name
    base = _UNSAFE.sub("_", base).strip(" .")
    return (base or fallback)[-_MAX_NAME:]


def save_uploads(uploads: list[UploadFile], job_dir: Path) -> list[Path]:
    """Writes uploads to disk; the index prefix keeps same-named files apart."""
    paths = []
    for index, upload in enumerate(uploads):
        path = job_dir / f"{index:03d}_{safe_name(upload.filename)}"
        with path.open("wb") as out:
            shutil.copyfileobj(upload.file, out)
        paths.append(path)
    return paths


def without_prefix(name: str) -> str:
    """The name a file made from an upload should have for the user."""
    return _UPLOAD_PREFIX.sub("", name)


def remove(job_dir: Path) -> None:
    shutil.rmtree(job_dir, ignore_errors=True)


def sweep_stale() -> int:
    """Removes job folders left behind by a crash or an abandoned request.

    Only old ones: a second launch runs this before it fails to bind the
    busy port, and the folder is shared with the instance already running.
    """
    if not settings.TEMP_DIR.exists():
        return 0
    cutoff = time.time() - settings.STALE_AFTER_S
    removed = 0
    for entry in settings.TEMP_DIR.iterdir():
        try:
            if entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
                removed += 1
        except OSError:
            continue
    return removed
