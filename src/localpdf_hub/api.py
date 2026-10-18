"""HTTP endpoints for the tools (contract in docs/api.md)."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from localpdf_hub import limits, settings, workspace
from localpdf_hub import platform as host
from localpdf_hub.tools import images, merge, pages, password, watermark, word
from localpdf_hub.tools.pdf_files import parse_rotations

router = APIRouter(prefix="/api/v1/pdf")

# Measured peaks: PDF to Word 2.15 GB and merge 1.66 GB on a 555 MB file.
_HEAVY = 2
_LIGHT = 1

_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

Upload = Annotated[UploadFile, File()]
Uploads = Annotated[list[UploadFile], File()]

# Tools that work on every uploaded file; the rest take the first one.
_TAKES_ALL_INPUTS = {merge.merge, word.from_word}


async def _run(
    uploads: list[UploadFile],
    tool: Callable[..., Path],
    *args: Any,
    weight: int = _LIGHT,
    download_name: str | None = None,
) -> FileResponse:
    """Saves the uploads, runs the tool in a worker thread and streams the result.

    The job folder is removed after the response is sent, or right away if
    the tool fails.
    """
    job_dir = workspace.new_job_dir()
    try:
        inputs = await asyncio.to_thread(workspace.save_uploads, uploads, job_dir)
        result = await asyncio.to_thread(_run_limited, tool, inputs, args, weight, job_dir)
    except BaseException:
        workspace.remove(job_dir)
        raise
    return FileResponse(
        result,
        media_type=_MEDIA_TYPES[result.suffix],
        filename=download_name or workspace.without_prefix(result.name),
        background=BackgroundTask(workspace.remove, job_dir),
    )


def _run_limited(
    tool: Callable[..., Path], inputs: list[Path], args: tuple[Any, ...], weight: int, job_dir: Path
) -> Path:
    # The gate is taken here, in the worker thread: a request that gives up
    # leaves this thread running, and it must keep its share of memory.
    with limits.JOB_GATE.slot(weight), limits.job_deadline(settings.JOB_TIMEOUT_S):
        limits.check_page_limit(inputs)
        first = inputs if tool in _TAKES_ALL_INPUTS else inputs[0]
        return tool(first, *args, job_dir)


def _stem(upload: UploadFile) -> str:
    return Path(workspace.safe_name(upload.filename, "document")).stem


@router.post("/merge")
async def merge_files(files: Uploads, rotations: Annotated[str, Form()] = "") -> FileResponse:
    return await _run(files, merge.merge, parse_rotations(rotations), weight=_HEAVY)


@router.post("/split")
async def split(
    file: Upload,
    from_: Annotated[int | None, Form(alias="from")] = None,
    to: Annotated[int | None, Form()] = None,
    pages_: Annotated[str | None, Form(alias="pages")] = None,
) -> FileResponse:
    spec = pages_ if pages_ is not None else f"{from_ or 1}-{to or from_ or 1}"
    return await _run([file], pages.split, spec)


@router.post("/rotate")
async def rotate(file: Upload, rotations: Annotated[str, Form()]) -> FileResponse:
    return await _run([file], pages.rotate, parse_rotations(rotations))


@router.post("/compress")
async def compress(file: Upload) -> FileResponse:
    return await _run([file], pages.compress)


@router.post("/protect")
async def protect(file: Upload, password_: Annotated[str, Form(alias="password")]) -> FileResponse:
    return await _run([file], password.protect, password_, weight=_HEAVY)


@router.post("/unlock")
async def unlock(file: Upload, password_: Annotated[str, Form(alias="password")]) -> FileResponse:
    return await _run([file], password.unlock, password_, weight=_HEAVY)


@router.post("/watermark")
async def add_watermark(
    file: Upload, text: Annotated[str, Form()], opacity: Annotated[float, Form()] = 0.3
) -> FileResponse:
    return await _run([file], watermark.watermark, text, opacity)


@router.post("/extract-images")
async def extract_images(file: Upload) -> FileResponse:
    return await _run([file], images.extract_images)


@router.post("/to-images")
async def to_images(file: Upload) -> FileResponse:
    return await _run([file], images.render_pages)


@router.post("/to-word")
async def to_word(file: Upload) -> FileResponse:
    title = _stem(file)
    return await _run([file], word.to_word, title, weight=_HEAVY, download_name=f"{title}.docx")


@router.post("/from-word")
async def from_word(files: Uploads) -> FileResponse:
    converter = host.find_document_converter()
    name = f"{_stem(files[0])}.pdf" if len(files) == 1 else "converted.zip"
    return await _run(files, word.from_word, converter, weight=_HEAVY, download_name=name)
