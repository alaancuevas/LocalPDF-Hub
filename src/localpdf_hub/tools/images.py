"""Get images out of a PDF: the embedded ones, or each page rendered."""

import io
import logging
import zipfile
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from localpdf_hub import errors, settings
from localpdf_hub.errors import AppError
from localpdf_hub.limits import check_deadline
from localpdf_hub.tools.pdf_files import read_pdf

logger = logging.getLogger(__name__)

_DPI = 150
_PDF_POINTS_PER_INCH = 72


def extract_images(path: Path, out_dir: Path) -> Path:
    reader = read_pdf(path)
    out = out_dir / f"{path.stem}_images.zip"
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for page_number, page in enumerate(reader.pages, 1):
            check_deadline()
            for image_number, image in enumerate(page.images, 1):
                try:
                    with Image.open(io.BytesIO(image.data)) as picture:
                        png = io.BytesIO()
                        picture.save(png, "PNG")
                except OSError:
                    # A single image Pillow cannot decode should not cost the user the rest.
                    logger.warning("Skipped image %d on page %d", image_number, page_number)
                    continue
                name = f"page_{page_number:03d}_image_{image_number:02d}.png"
                archive.writestr(name, png.getvalue())
                count += 1
    if not count:
        out.unlink()
        raise AppError(errors.NO_IMAGES, f"{path.name} has no embedded images.")
    return out


def render_pages(path: Path, out_dir: Path) -> Path:
    read_pdf(path)
    out = out_dir / f"{path.stem}_pages.zip"
    document = pdfium.PdfDocument(path)
    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
            for index in range(len(document)):
                check_deadline()
                page = document[index]
                try:
                    bitmap = page.render(scale=_capped_scale(page))
                    png = io.BytesIO()
                    bitmap.to_pil().save(png, "PNG")
                finally:
                    page.close()
                archive.writestr(f"page_{index + 1:03d}.png", png.getvalue())
    finally:
        document.close()
    return out


def _capped_scale(page: pdfium.PdfPage) -> float:
    """Lowers the resolution of pages that would exceed MAX_RENDER_PIXELS.

    A page can declare a huge size (14400 pt is about 30000 px a side at
    150 dpi), which would need gigabytes for a single bitmap.
    """
    scale = _DPI / _PDF_POINTS_PER_INCH
    width, height = page.get_size()
    pixels = width * height * scale * scale
    if pixels <= settings.MAX_RENDER_PIXELS:
        return scale
    # Slightly under the cap so rounding the bitmap size cannot cross it.
    return float(scale * (settings.MAX_RENDER_PIXELS / pixels) ** 0.5 * 0.999)
