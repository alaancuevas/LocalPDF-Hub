"""Microsoft Word through COM (Windows only), with LibreOffice as its fallback.

The COM calls are carried over from 3.x unchanged: they cannot be tested
outside Windows with Word installed, so only their wrapping changed.
"""

import logging
from contextlib import suppress
from pathlib import Path
from typing import Any

from localpdf_hub import errors
from localpdf_hub.errors import AppError
from localpdf_hub.platform.libreoffice import LibreOfficeConverter

try:
    import pythoncom
    import pywintypes
    import win32com.client

    WORD_COM_AVAILABLE = True
except ImportError:
    WORD_COM_AVAILABLE = False

logger = logging.getLogger(__name__)

_WD_FORMAT_PDF = 17
_WD_DO_NOT_SAVE_CHANGES = 0
# DISP_E_EXCEPTION: what Word 2007 (Office12) raises when asked to save as PDF.
_DISP_E_EXCEPTION = -2147352567


class WordComConverter:
    def __init__(self, fallback: LibreOfficeConverter | None) -> None:
        self.fallback = fallback

    def convert(self, documents: list[Path], out_dir: Path) -> list[Path]:
        # COM objects belong to the thread that created them, and every
        # request runs in a worker thread.
        pythoncom.CoInitialize()
        word = None
        try:
            word = _start_word()
            pdfs = []
            for document in documents:
                pdf = out_dir / f"{document.stem}.pdf"
                if word is not None and _save_as_pdf(word, document, pdf):
                    pdfs.append(pdf)
                elif self.fallback is not None:
                    logger.warning("Word could not convert %s; using LibreOffice", document.name)
                    pdfs.append(self.fallback.convert_one(document, out_dir))
                else:
                    raise AppError(
                        errors.CONVERTER_MISSING,
                        "This Word version cannot export PDF and LibreOffice is not installed.",
                    )
            return pdfs
        finally:
            _quit_word(word)
            pythoncom.CoUninitialize()


def _start_word() -> Any | None:
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        return word
    except Exception as error:  # noqa: BLE001 -- any COM failure means "no Word"
        logger.warning("Could not start Word through COM: %s", error)
        return None


def _save_as_pdf(word: Any, document: Path, pdf: Path) -> bool:
    """False when this Word version cannot export PDF; other COM errors raise."""
    doc = None
    try:
        # OpenAndRepair skips Protected View, which blocks SaveAs on downloaded files.
        doc = word.Documents.Open(
            str(document.resolve()),
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
            OpenAndRepair=True,
        )
        doc.SaveAs(str(pdf.resolve()), FileFormat=_WD_FORMAT_PDF)
        doc.Close(_WD_DO_NOT_SAVE_CHANGES)
        return True
    except pywintypes.com_error as error:
        if doc:
            with suppress(pywintypes.com_error):
                doc.Close(_WD_DO_NOT_SAVE_CHANGES)
        if "Office12" in str(error) or getattr(error, "hresult", None) == _DISP_E_EXCEPTION:
            logger.warning("Word 2007 cannot export PDF natively")
            return False
        raise AppError(errors.INTERNAL, f"Word could not convert {document.name}.") from error


def _quit_word(word: Any | None) -> None:
    if word is None:
        return
    # Word may already be gone; there is nothing left to do then.
    with suppress(Exception):
        word.Quit()
