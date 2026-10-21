"""Reading and writing PDFs with the errors the UI can explain."""

from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError, PyPdfError
from pypdf.generic import (
    BooleanObject,
    ByteStringObject,
    DictionaryObject,
    FloatObject,
    IndirectObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from localpdf_hub import errors
from localpdf_hub.errors import AppError

# What /Info holds by the spec: text (dates are text too), names such as /Trapped, numbers.
_INFO_VALUES = (
    TextStringObject,
    ByteStringObject,
    NameObject,
    NumberObject,
    FloatObject,
    BooleanObject,
)
# A broken reference in the source: pypdf may raise any of these while resolving it.
_UNRESOLVED = (PyPdfError, IndexError, KeyError, ValueError, TypeError)


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


def clone(reader: PdfReader) -> PdfWriter:
    """A writer with the whole document, and its /Info rebuilt from the source.

    pypdf copies /Info without remapping its indirect references: they keep the source's
    numbers, so a valid /Title ends up pointing to another object of the new file (or to
    nothing, and deduplicating then fails).
    """
    writer = PdfWriter(clone_from=reader)
    info = writer._info
    if info is not None:
        info.clear()
        info.update(_source_info(reader))
    return writer


def _source_info(reader: PdfReader) -> dict[NameObject, Any]:
    """The source /Info, each value resolved in the source; broken or nested ones are left out."""
    try:
        source = reader.trailer.get("/Info")
        source = source.get_object() if source is not None else None
    except _UNRESOLVED:
        return {}
    if not isinstance(source, DictionaryObject):
        return {}
    values: dict[NameObject, Any] = {}
    for key, value in source.items():
        try:
            resolved = value.get_object() if isinstance(value, IndirectObject) else value
        except _UNRESOLVED:
            continue
        if isinstance(resolved, _INFO_VALUES):
            values[NameObject(key)] = resolved
    return values


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
