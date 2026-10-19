"""Add or remove a PDF password."""

import secrets
from pathlib import Path

from pypdf import PasswordType, PdfWriter
from pypdf.constants import UserAccessPermissions as Permission

from localpdf_hub import errors, limits
from localpdf_hub.errors import AppError
from localpdf_hub.tools.pdf_files import read_pdf, write_pdf

# Bits 3-6 and 9-12: what an owner password can take away.
_RESTRICTABLE = (
    Permission.PRINT
    | Permission.MODIFY
    | Permission.EXTRACT
    | Permission.ADD_OR_MODIFY
    | Permission.FILL_FORM_FIELDS
    | Permission.EXTRACT_TEXT_AND_GRAPHICS
    | Permission.ASSEMBLE_DOC
    | Permission.PRINT_TO_REPRESENTATION
)


def protect(path: Path, password: str, out_dir: Path) -> Path:
    if not password:
        raise AppError(errors.INVALID_INPUT, "The password is empty.")
    reader = read_pdf(path)
    permissions = None
    if reader.is_encrypted:
        # Only an owner password (it restricts printing or copying) opens with an empty one.
        if reader.decrypt("") == PasswordType.NOT_DECRYPTED:
            raise AppError(errors.ENCRYPTED, f"{path.name} needs its password; unlock it first.")
        permissions = reader.user_access_permissions
    # clone_from keeps bookmarks, links and metadata that copying pages drops.
    writer = PdfWriter(clone_from=reader)
    # pypdf defaults to RC4, which is broken; AES-256 is revision 6 of the spec.
    if permissions is not None and (permissions & _RESTRICTABLE) != _RESTRICTABLE:
        # The restrictions stay binding for everybody, as before: nobody gets an owner password.
        writer.encrypt(
            user_password=password,
            owner_password=secrets.token_urlsafe(32),
            algorithm="AES-256",
            permissions_flag=permissions,
        )
    else:
        writer.encrypt(user_password=password, algorithm="AES-256")
    return write_pdf(writer, out_dir / f"{path.stem}_protected.pdf")


def unlock(path: Path, password: str, out_dir: Path) -> Path:
    reader = read_pdf(path)
    if not reader.is_encrypted:
        raise AppError(errors.NOT_ENCRYPTED, f"{path.name} has no password.")
    if reader.decrypt(password) == PasswordType.NOT_DECRYPTED:
        raise AppError(errors.WRONG_PASSWORD, "The password is not correct.")
    # The general check could not count the pages before the password was known.
    limits.check_page_count(len(reader.pages))
    writer = PdfWriter(clone_from=reader)
    return write_pdf(writer, out_dir / f"{path.stem}_unlocked.pdf")
