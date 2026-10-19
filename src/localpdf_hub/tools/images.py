"""Get images out of a PDF: the embedded ones, or each page rendered."""

import io
import logging
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from localpdf_hub import errors, settings
from localpdf_hub.errors import AppError
from localpdf_hub.limits import check_deadline, check_result_size
from localpdf_hub.tools.pdf_files import read_pdf

logger = logging.getLogger(__name__)

_PDF_POINTS_PER_INCH = 72
_FORMATS = {"png": "PNG", "jpg": "JPEG"}
_DPIS = (72, 150, 300)
_JPEG_QUALITY = 85
# Pillow cannot write a JPEG with a side over 65500 px.
_JPEG_MAX_SIDE = 65500
# pdfium is not thread-safe, not even across documents, and two light jobs can run at once.
_PDFIUM = threading.Lock()


@dataclass(frozen=True)
class RenderOptions:
    format: str = "png"
    dpi: int = 150


def parse_render_options(image_format: str, dpi: str) -> RenderOptions:
    """Form fields as the UI sends them: an empty field means the default."""
    image_format = image_format or "png"
    if image_format not in _FORMATS:
        raise AppError(errors.INVALID_INPUT, f"The format must be one of {tuple(_FORMATS)}.")
    dpi = dpi or "150"
    if dpi not in {str(value) for value in _DPIS}:
        raise AppError(errors.INVALID_INPUT, f"The resolution must be one of {_DPIS} dpi.")
    return RenderOptions(image_format, int(dpi))


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


def render_pages(path: Path, options: RenderOptions, out_dir: Path) -> Path:
    read_pdf(path)
    out = out_dir / f"{path.stem}_pages.zip"
    jpeg = options.format == "jpg"
    total = 0
    with _PDFIUM:
        document = pdfium.PdfDocument(path)
        try:
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
                for index in range(len(document)):
                    check_deadline()
                    page = document[index]
                    try:
                        scale = _capped_scale(page, options.dpi, _JPEG_MAX_SIDE if jpeg else None)
                        image = page.render(scale=scale).to_pil()
                    finally:
                        page.close()
                    data = io.BytesIO()
                    if jpeg:
                        image.convert("RGB").save(data, "JPEG", quality=_JPEG_QUALITY)
                    else:
                        image.save(data, "PNG")
                    total += data.tell()
                    check_result_size(total)
                    archive.writestr(f"page_{index + 1:03d}.{options.format}", data.getvalue())
        finally:
            document.close()
    return out


def _capped_scale(page: pdfium.PdfPage, dpi: int, max_side: int | None = None) -> float:
    """Lowers the resolution of pages that would exceed MAX_RENDER_PIXELS, or max_side.

    A page can declare a huge size (14400 pt is about 30000 px a side at
    150 dpi), which would need gigabytes for a single bitmap.
    """
    scale = dpi / _PDF_POINTS_PER_INCH
    width, height = page.get_size()
    pixels = width * height * scale * scale
    # Slightly under each cap: pdfium rounds the bitmap size up.
    if pixels > settings.MAX_RENDER_PIXELS:
        scale = float(scale * (settings.MAX_RENDER_PIXELS / pixels) ** 0.5 * 0.999)
    if max_side is not None and max(width, height) * scale > max_side:
        scale = max_side / max(width, height) * 0.999
    return scale
