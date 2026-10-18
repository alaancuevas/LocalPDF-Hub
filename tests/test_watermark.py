"""The watermark is real text with an embedded font subset, not an image."""

import gc
import io
import sys
import weakref
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from fontTools.ttLib import TTFont
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    IndirectObject,
    NameObject,
    StreamObject,
)

from localpdf_hub.errors import AppError
from localpdf_hub.tools import watermark as wm

ORIGINAL = "Original page text"
# 100 different characters every candidate font has.
HUNDRED = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    "ÁÉÍÓÚÑÜÀÈÌÒÙÂÊÎÔÛÄËÏÖáéíóúñüàèìòùâêîôû"
)
assert len(set(HUNDRED)) == 100


def text_pdf(tmp_path: Path, pages: int = 6) -> Path:
    """Pages with a line of real text in a standard font."""
    writer = PdfWriter()
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    for _ in range(pages):
        page = writer.add_blank_page(width=595, height=842)
        content = DecodedStreamObject()
        content.set_data(f"BT /F1 12 Tf 72 760 Td ({ORIGINAL}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(content)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
    path = tmp_path / "in.pdf"
    writer.write(path)
    return path


def mark(tmp_path: Path, text: str = "CONFIDENCIAL", opacity: float = 0.3, pages: int = 6) -> Path:
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    return wm.watermark(text_pdf(tmp_path, pages), text, opacity, out)


def page_text(path: Path) -> str:
    return "".join(page.get_textpage().get_text_bounded() for page in pdfium.PdfDocument(str(path)))


def xobjects(resources) -> list:
    found = []
    for ref in (resources or {}).get("/XObject", {}).values():
        obj = ref.get_object()
        found.append(obj)
        if obj.get("/Subtype") == "/Form":
            found += xobjects(obj.get("/Resources"))
    return found


def reachable(reader: PdfReader) -> set[int]:
    seen: set[int] = set()
    stack: list = [reader.trailer]
    while stack:
        item = stack.pop()
        if isinstance(item, IndirectObject):
            if item.idnum not in seen:
                seen.add(item.idnum)
                stack.append(item.get_object())
        elif isinstance(item, (DictionaryObject, StreamObject)):
            stack.extend(item.values())
        elif isinstance(item, ArrayObject):
            stack.extend(item)
    return seen


def test_no_image_is_added_and_the_font_is_embedded_once(tmp_path):
    reader = PdfReader(mark(tmp_path))
    font_files = set()
    for page in reader.pages:
        assert not xobjects(page["/Resources"]), "the watermark added an image or form"
        type0 = [f.get_object() for f in page["/Resources"]["/Font"].values()]
        type0 = [f for f in type0 if f["/Subtype"] == "/Type0"]
        assert len(type0) == 1 and "/ToUnicode" in type0[0]
        descriptor = type0[0]["/DescendantFonts"][0].get_object()["/FontDescriptor"].get_object()
        font_files.add(descriptor.raw_get("/FontFile2").idnum)
    assert len(font_files) == 1


@pytest.mark.parametrize("text", ["CONFIDENCIAL", HUNDRED])
def test_growth_stays_under_10_kb_per_page(tmp_path, text):
    source = text_pdf(tmp_path)
    out = wm.watermark(source, text, 0.3, tmp_path)
    assert (out.stat().st_size - source.stat().st_size) / 6 < 10 * 1024


def test_opacity_is_an_ext_gstate(tmp_path):
    page = PdfReader(mark(tmp_path, opacity=0.45)).pages[0]
    states = [s.get_object() for s in page["/Resources"]["/ExtGState"].values()]
    assert any(abs(float(s.get("/ca", -1)) - 0.45) < 1e-6 for s in states)


def test_mark_and_original_text_can_be_extracted(tmp_path):
    text = page_text(mark(tmp_path))
    assert "CONFIDENCIAL" in text and ORIGINAL in text


def test_accents_are_extracted(tmp_path):
    assert "BORRADOR ÁÉÍÓÚÑ ¿?" in page_text(mark(tmp_path, "BORRADOR ÁÉÍÓÚÑ ¿?", pages=1))


def test_line_breaks_become_spaces(tmp_path):
    assert "A B" in page_text(mark(tmp_path, "A\n  B", pages=1))


def test_no_object_is_left_unreferenced(tmp_path):
    reader = PdfReader(mark(tmp_path))
    defined = set(reader.xref.get(0, {})) | set(reader.xref_objStm)
    assert defined <= reachable(reader)


def test_text_limit(tmp_path):
    mark(tmp_path, "x" * 100, pages=1)
    with pytest.raises(AppError):
        mark(tmp_path, "x" * 101, pages=1)


@pytest.mark.parametrize("text", ["emoji \U0001f600", "שלום", "مرحبا"])
def test_text_the_font_cannot_draw_is_refused(tmp_path, text):
    with pytest.raises(AppError):
        mark(tmp_path, text, pages=1)


@pytest.mark.parametrize("text", ["שלום", "مرحبا"])
def test_right_to_left_text_is_refused_even_when_the_font_has_it(tmp_path, monkeypatch, text):
    # Arial has Hebrew and Arabic glyphs; drawn one by one they would come out
    # reversed and unjoined, so the refusal must not depend on missing glyphs.
    arial = next(
        (
            path
            for path in (
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "C:/Windows/Fonts/arial.ttf",
            )
            if Path(path).exists()
        ),
        None,
    )
    if arial is None:
        pytest.skip("no font with Hebrew and Arabic glyphs on this system")
    monkeypatch.setitem(wm._FONT_CANDIDATES, sys.platform, [arial])
    with pytest.raises(AppError, match="Right-to-left"):
        mark(tmp_path, text, pages=1)


def test_a_font_that_forbids_embedding_is_skipped(tmp_path, monkeypatch):
    candidates = wm._FONT_CANDIDATES.get(sys.platform, wm._FONT_CANDIDATES["linux"])
    source = next((Path(c) for c in candidates if Path(c).exists()), None)
    if source is None:
        pytest.skip("no candidate font on this system")
    font = TTFont(source, fontNumber=0) if source.suffix == ".ttc" else TTFont(source)
    font["OS/2"].fsType = 0x0002
    restricted = tmp_path / "restricted.ttf"
    font.save(restricted)
    monkeypatch.setitem(wm._FONT_CANDIDATES, sys.platform, [str(restricted)])
    with pytest.raises(AppError, match="can be embedded"):
        mark(tmp_path, pages=1)


def test_the_job_writer_is_released(tmp_path, monkeypatch):
    refs = []

    class Tracked(PdfWriter):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            refs.append(weakref.ref(self))

    monkeypatch.setattr(wm, "PdfWriter", Tracked)
    mark(tmp_path, pages=2)
    gc.collect()
    assert refs and all(ref() is None for ref in refs)


def test_two_marks_at_once_keep_their_own_text(tmp_path):
    texts = ["PRIMERO", "SEGUNDO"]

    def run(text: str) -> str:
        folder = tmp_path / text
        folder.mkdir()
        return page_text(mark(folder, text, pages=3))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, texts))
    for text, other, result in zip(texts, reversed(texts), results, strict=True):
        assert text in result and other not in result


def test_output_opens_in_pypdf_from_memory(tmp_path):
    data = mark(tmp_path, pages=1).read_bytes()
    assert len(PdfReader(io.BytesIO(data)).pages) == 1
