"""What depends on the operating system: finding a Word-to-PDF converter."""

import sys
from pathlib import Path
from typing import Protocol

from localpdf_hub.platform.libreoffice import LibreOfficeConverter, find_soffice


class DocumentConverter(Protocol):
    def convert(self, documents: list[Path], out_dir: Path) -> list[Path]: ...


def find_document_converter() -> DocumentConverter | None:
    """Word on Windows when present (with LibreOffice as its fallback), else LibreOffice."""
    soffice = find_soffice()
    libreoffice = LibreOfficeConverter(soffice) if soffice else None
    if sys.platform == "win32":
        from localpdf_hub.platform.word_com import WORD_COM_AVAILABLE, WordComConverter

        if WORD_COM_AVAILABLE:
            return WordComConverter(fallback=libreoffice)
    return libreoffice
