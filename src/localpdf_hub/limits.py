"""Limits on concurrent work, job duration and document size.

Python threads cannot be killed, so the time limit is cooperative: tools
call check_deadline() once per page and the job stops on the next page.
"""

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError

from localpdf_hub import errors, settings
from localpdf_hub.errors import AppError

_job = threading.local()


class JobGate:
    """Counting semaphore where each job takes as many units as it weighs."""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self.in_use = 0
        self._cond = threading.Condition()

    @contextmanager
    def slot(self, weight: int) -> Iterator[None]:
        weight = min(weight, self.capacity)
        with self._cond:
            self._cond.wait_for(lambda: self.in_use + weight <= self.capacity)
            self.in_use += weight
        try:
            yield
        finally:
            with self._cond:
                self.in_use -= weight
                self._cond.notify_all()


JOB_GATE = JobGate(settings.JOB_CAPACITY)


@contextmanager
def job_deadline(seconds: float) -> Iterator[None]:
    _job.deadline = time.monotonic() + seconds
    try:
        yield
    finally:
        _job.deadline = None


def check_deadline() -> None:
    deadline = getattr(_job, "deadline", None)
    if deadline is not None and time.monotonic() >= deadline:
        raise AppError(errors.TIMEOUT, "The job took too long and was stopped.")


def check_page_limit(paths: list[Path], opens_encrypted: bool = False) -> None:
    """Rejects jobs over MAX_PAGES; tiny pages can dodge the byte limit.

    A PDF that needs a password to open is refused here, before any work,
    unless the tool is the one that takes the password (unlock, protect).
    One with only an owner password opens: pypdf tries the empty password.
    """
    total = 0
    for path in paths:
        if path.suffix.lower() != ".pdf":
            continue
        try:
            total += len(PdfReader(path).pages)
        except FileNotDecryptedError as error:
            if opens_encrypted:
                continue
            raise AppError(errors.ENCRYPTED, f"{path.name} needs a password to open.") from error
        except PdfReadError:
            # Unreadable: the tool itself reports the right error.
            continue
        check_page_count(total)


def check_page_count(total: int) -> None:
    if total > settings.MAX_PAGES:
        raise AppError(
            errors.TOO_MANY_PAGES,
            f"Documents over {settings.MAX_PAGES} pages are not supported.",
        )
