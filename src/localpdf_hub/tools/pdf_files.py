"""Reading and writing PDFs with the errors the UI can explain."""

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from localpdf_hub import errors
from localpdf_hub.errors import AppError


def read_pdf(path: Path) -> PdfReader:
    try:
        reader = PdfReader(path)
        # Page count forces the cross-reference table to be parsed now, so a
        # broken file fails here and not halfway through a tool.
        if not reader.is_encrypted:
            len(reader.pages)
    except PdfReadError as error:
        raise AppError(errors.INVALID_PDF, f"{path.name} is not a readable PDF.") from error
    return reader


def write_pdf(writer: PdfWriter, path: Path) -> Path:
    with path.open("wb") as out:
        writer.write(out)
    return path


def parse_rotations(text: str) -> list[int]:
    """Parses "90,0,180"; blanks mean 0 and every angle must be a multiple of 90."""
    angles = []
    for item in text.split(","):
        item = item.strip()
        try:
            angle = int(item) if item else 0
        except ValueError as error:
            raise AppError(errors.INVALID_INPUT, f"Rotation {item!r} is not a number.") from error
        if angle % 90:
            raise AppError(errors.INVALID_INPUT, f"Rotation {angle} is not a multiple of 90.")
        angles.append(angle)
    return angles
