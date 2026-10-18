"""LibreOffice in headless mode: the Word-to-PDF converter on every OS."""

import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from localpdf_hub import errors
from localpdf_hub.errors import AppError

logger = logging.getLogger(__name__)

_TIMEOUT_S = 120

_KNOWN_PATHS = {
    "win32": [
        Path("C:/Program Files/LibreOffice/program/soffice.exe"),
        Path("C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
    ],
    "darwin": [Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")],
}


def find_soffice() -> Path | None:
    on_path = shutil.which("soffice") or shutil.which("libreoffice")
    if on_path:
        return Path(on_path)
    return next((path for path in _KNOWN_PATHS.get(sys.platform, []) if path.exists()), None)


class LibreOfficeConverter:
    def __init__(self, soffice: Path) -> None:
        self.soffice = soffice

    def convert(self, documents: list[Path], out_dir: Path) -> list[Path]:
        return [self.convert_one(document, out_dir) for document in documents]

    def convert_one(self, document: Path, out_dir: Path) -> Path:
        # A throwaway profile per call: two conversions sharing the user
        # profile fight over its lock and one of them fails.
        with tempfile.TemporaryDirectory() as profile:
            command = [
                str(self.soffice),
                f"-env:UserInstallation={Path(profile).as_uri()}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(out_dir),
                str(document),
            ]
            try:
                subprocess.run(  # noqa: S603 -- fixed argv, no shell
                    command,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=_TIMEOUT_S,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                raise AppError(
                    errors.INTERNAL, f"LibreOffice could not convert {document.name}."
                ) from error
        pdf = out_dir / f"{document.stem}.pdf"
        # soffice sometimes exits 0 without writing anything.
        if not pdf.exists():
            raise AppError(errors.INTERNAL, f"LibreOffice produced no PDF for {document.name}.")
        return pdf
