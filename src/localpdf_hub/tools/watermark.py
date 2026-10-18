"""Stamp a diagonal text watermark on every page."""

import io
import sys
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PageObject, PdfReader, PdfWriter

from localpdf_hub import errors
from localpdf_hub.errors import AppError
from localpdf_hub.limits import check_deadline
from localpdf_hub.tools.pdf_files import read_pdf, write_pdf

_PIXELS_PER_POINT = 2
_ANGLE = 35

_FONT_CANDIDATES = {
    "win32": ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"],
    "darwin": ["/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Geneva.ttf"],
    "linux": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}


def watermark(path: Path, text: str, opacity: float, out_dir: Path) -> Path:
    text = text.strip()
    if not text:
        raise AppError(errors.INVALID_INPUT, "The watermark text is empty.")
    if not 0.05 <= opacity <= 1:
        raise AppError(errors.INVALID_INPUT, "Opacity must be between 0.05 and 1.")

    writer = PdfWriter(clone_from=read_pdf(path))
    for page in writer.pages:
        check_deadline()
        size = (float(page.mediabox.width), float(page.mediabox.height))
        page.merge_page(_stamp(size, text, opacity))
    return write_pdf(writer, out_dir / f"{path.stem}_watermarked.pdf")


@cache
def _stamp(size: tuple[float, float], text: str, opacity: float) -> PageObject:
    """One transparent page of the given size with the text centred and tilted.

    Cached per page size: a document usually has one or two sizes, and the
    old fixed 800x600 canvas left the text off-centre on anything but A4.
    """
    width, height = (round(side * _PIXELS_PER_POINT) for side in size)
    layer = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    font = _font(max(12, int(min(width, height) / max(4, len(text)) * 1.4)))
    label = Image.new("RGBA", layer.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(label)
    draw.text(
        (width / 2, height / 2),
        text,
        fill=(0, 0, 0, round(255 * opacity)),
        font=font,
        anchor="mm",
    )
    layer.alpha_composite(label.rotate(_ANGLE, center=(width / 2, height / 2)))
    buf = io.BytesIO()
    layer.save(buf, "PDF", resolution=72 * _PIXELS_PER_POINT)
    return PdfReader(buf).pages[0]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in _FONT_CANDIDATES.get(sys.platform, _FONT_CANDIDATES["linux"]):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size)
