"""Merge PDFs and images into one PDF, in the order given."""

import io
from pathlib import Path

import pi_heif
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter

from localpdf_hub.limits import check_deadline
from localpdf_hub.tools.pdf_files import read_pdf, write_pdf

pi_heif.register_heif_opener()

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".jfif", ".jif", ".heic", ".heif"}

# Photos are placed so their long side matches A4 (11.69 in); at Pillow's
# default 72 dpi a 4000 px phone photo became a 55-inch page.
_A4_LONG_SIDE_IN = 11.69


def merge(paths: list[Path], rotations: list[int], out_dir: Path) -> Path:
    """Rotations are added to each file's current rotation, one angle per file."""
    writer = PdfWriter()
    for index, path in enumerate(paths):
        check_deadline()
        rotation = rotations[index] if index < len(rotations) else 0
        reader = (
            _image_as_pdf(path, rotation)
            if path.suffix.lower() in IMAGE_SUFFIXES
            else read_pdf(path)
        )
        for page in reader.pages:
            check_deadline()
            if rotation and path.suffix.lower() not in IMAGE_SUFFIXES:
                page.rotate(rotation)
            writer.add_page(page)
    return write_pdf(writer, out_dir / "merged.pdf")


def _image_as_pdf(path: Path, rotation: int) -> PdfReader:
    with Image.open(path) as image:
        # Phones store "rotate me" as EXIF instead of rotating the pixels.
        upright = ImageOps.exif_transpose(image)
        if rotation:
            upright = upright.rotate(-rotation, expand=True)
        rgb = upright.convert("RGB")
        dpi = max(72.0, max(rgb.size) / _A4_LONG_SIDE_IN)
        buf = io.BytesIO()
        rgb.save(buf, "PDF", resolution=dpi)
    return PdfReader(buf)
