"""Add or remove a PDF password."""

from pathlib import Path

from pypdf import PasswordType, PdfWriter

from localpdf_hub import errors
from localpdf_hub.errors import AppError
from localpdf_hub.tools.pdf_files import read_pdf, write_pdf


def protect(path: Path, password: str, out_dir: Path) -> Path:
    if not password:
        raise AppError(errors.INVALID_INPUT, "The password is empty.")
    reader = read_pdf(path)
    if reader.is_encrypted:
        raise AppError(errors.INVALID_INPUT, f"{path.name} already has a password.")
    # clone_from keeps bookmarks, links and metadata that copying pages drops.
    writer = PdfWriter(clone_from=reader)
    # pypdf defaults to RC4, which is broken; AES-256 is revision 6 of the spec.
    writer.encrypt(user_password=password, algorithm="AES-256")
    return write_pdf(writer, out_dir / f"{path.stem}_protected.pdf")


def unlock(path: Path, password: str, out_dir: Path) -> Path:
    reader = read_pdf(path)
    if not reader.is_encrypted:
        raise AppError(errors.NOT_ENCRYPTED, f"{path.name} has no password.")
    if reader.decrypt(password) == PasswordType.NOT_DECRYPTED:
        raise AppError(errors.WRONG_PASSWORD, "The password is not correct.")
    writer = PdfWriter(clone_from=reader)
    return write_pdf(writer, out_dir / f"{path.stem}_unlocked.pdf")
