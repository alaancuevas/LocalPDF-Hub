"""Split, rotate and compress: tools that keep the pages and change little else."""

from pathlib import Path

from pypdf import PdfWriter

from localpdf_hub import errors
from localpdf_hub.errors import AppError
from localpdf_hub.limits import check_deadline
from localpdf_hub.tools.pdf_files import read_pdf, write_pdf


def page_numbers(spec: str, total: int) -> list[int]:
    """Parses "1,3,5-7" into 1-based page numbers that exist in the document."""
    numbers: list[int] = []
    for part in (item.strip() for item in spec.split(",")):
        if not part:
            continue
        first, _, last = part.partition("-")
        try:
            start, end = int(first), int(last or first)
        except ValueError as error:
            raise AppError(errors.INVALID_INPUT, f"{part!r} is not a page or range.") from error
        if start > end or start < 1 or end > total:
            raise AppError(errors.NO_PAGES, f"Pages {part} are not in a {total}-page document.")
        numbers.extend(range(start, end + 1))
    if not numbers:
        raise AppError(errors.NO_PAGES, "No pages were selected.")
    return numbers


def split(path: Path, spec: str, out_dir: Path) -> Path:
    reader = read_pdf(path)
    writer = PdfWriter()
    for number in page_numbers(spec, len(reader.pages)):
        check_deadline()
        writer.add_page(reader.pages[number - 1])
    return write_pdf(writer, out_dir / f"{path.stem}_pages.pdf")


def rotate(path: Path, rotations: list[int], out_dir: Path) -> Path:
    """Each angle is added to the page's current rotation, like the UI preview shows."""
    writer = PdfWriter(clone_from=read_pdf(path))
    for page, angle in zip(writer.pages, rotations, strict=False):
        check_deadline()
        if angle:
            page.rotate(angle)
    return write_pdf(writer, out_dir / f"{path.stem}_rotated.pdf")


def compress(path: Path, out_dir: Path) -> Path:
    writer = PdfWriter(clone_from=read_pdf(path))
    for page in writer.pages:
        check_deadline()
        page.compress_content_streams()
    writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    return write_pdf(writer, out_dir / f"{path.stem}_compressed.pdf")
