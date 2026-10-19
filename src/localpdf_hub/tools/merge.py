"""Merge PDFs and images into one PDF, in the order given."""

from pathlib import Path

from pypdf import PdfWriter

from localpdf_hub import settings
from localpdf_hub.limits import check_deadline, check_result_size
from localpdf_hub.tools.images_pdf import Layout, add_image_page
from localpdf_hub.tools.pdf_files import read_pdf, write_pdf


def merge(paths: list[Path], rotations: list[int], layout: Layout, out_dir: Path) -> Path:
    """Rotations are added to each file's current rotation, one angle per file.

    Images are placed on pages as Image to PDF places them; their bytes count
    against MAX_RESULT_BYTES, as the PDFs are already bounded by the upload.
    """
    writer = PdfWriter()
    images = 0
    for index, path in enumerate(paths):
        check_deadline()
        rotation = rotations[index] if index < len(rotations) else 0
        if path.suffix.lower() in settings.IMAGE_SUFFIXES:
            images += add_image_page(writer, path, rotation, layout)
            check_result_size(images)
            continue
        for page in read_pdf(path).pages:
            check_deadline()
            if rotation:
                page.rotate(rotation)
            writer.add_page(page)
    return write_pdf(writer, out_dir / "merged.pdf")
