"""Errors the user can act on.

The UI translates `code`; `message` is English and meant for logs.
"""

INVALID_INPUT = "ERR_INVALID_INPUT"
INVALID_PDF = "ERR_INVALID_PDF"
WRONG_PASSWORD = "ERR_WRONG_PASSWORD"
NOT_ENCRYPTED = "ERR_NOT_ENCRYPTED"
ENCRYPTED = "ERR_ENCRYPTED"
NO_PAGES = "ERR_NO_PAGES"
NO_IMAGES = "ERR_NO_IMAGES"
TOO_LARGE = "ERR_TOO_LARGE"
TOO_MANY_PAGES = "ERR_TOO_MANY_PAGES"
TOO_MANY_IMAGES = "ERR_TOO_MANY_IMAGES"
IMAGE_TOO_LARGE = "ERR_IMAGE_TOO_LARGE"
RESULT_TOO_LARGE = "ERR_RESULT_TOO_LARGE"
TIMEOUT = "ERR_TIMEOUT"
CONVERTER_MISSING = "ERR_CONVERTER_MISSING"
INTERNAL = "ERR_INTERNAL"

_STATUS = {
    INVALID_INPUT: 400,
    INVALID_PDF: 400,
    WRONG_PASSWORD: 400,
    NOT_ENCRYPTED: 400,
    ENCRYPTED: 400,
    NO_PAGES: 400,
    NO_IMAGES: 400,
    TOO_LARGE: 413,
    TOO_MANY_PAGES: 413,
    TOO_MANY_IMAGES: 413,
    IMAGE_TOO_LARGE: 413,
    RESULT_TOO_LARGE: 413,
    TIMEOUT: 503,
    CONVERTER_MISSING: 503,
    INTERNAL: 500,
}


class AppError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def status(self) -> int:
        return _STATUS[self.code]
