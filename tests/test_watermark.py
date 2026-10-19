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
from PIL import ImageChops
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    IndirectObject,
    NameObject,
    NumberObject,
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
    return wm.watermark(text_pdf(tmp_path, pages), text, opacity, wm.Layout(), out)


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
    out = wm.watermark(source, text, 0.3, wm.Layout(), tmp_path)
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

    def run(text: str) -> Path:
        folder = tmp_path / text
        folder.mkdir()
        return mark(folder, text, pages=3)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(pool.map(run, texts))
    # Read back on this thread: pdfium crashes when two threads call it at once.
    results = [page_text(path) for path in outputs]
    for text, other, result in zip(texts, reversed(texts), results, strict=True):
        assert text in result and other not in result


def test_output_opens_in_pypdf_from_memory(tmp_path):
    data = mark(tmp_path, pages=1).read_bytes()
    assert len(PdfReader(io.BytesIO(data)).pages) == 1


# --- Layout: position, rotation, size, colour and pages on the box as it is seen ---

# MediaBox, CropBox and /Rotate of pages whose visible box is not the plain [0 0 w h].
BOXES = {
    "letter, CropBox, /Rotate 90": ([0, 0, 612, 792], [36, 36, 400, 500], 90),
    "letter, CropBox from (100, 50)": ([0, 0, 612, 792], [100, 50, 500, 700], None),
    "A4, /Rotate 270": ([0, 0, 595, 842], None, 270),
    "MediaBox centred on the origin": ([-306, -396, 306, 396], None, None),
    "pdfcrop-like": ([50, 80, 562, 712], [60, 90, 552, 702], None),
}
INHERITED = "CropBox and /Rotate inherited from /Pages"
SCALE = 1  # render px per pt


def box_pdf(media, crop=None, rotate=None, pages: int = 1, inherit: bool = False) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(100, 100)
    holder = writer._root_object["/Pages"] if inherit else None
    for page in writer.pages:
        target = holder if inherit else page
        page[NameObject("/MediaBox")] = ArrayObject(FloatObject(v) for v in media)
        if crop:
            target[NameObject("/CropBox")] = ArrayObject(FloatObject(v) for v in crop)
        if rotate is not None:
            target[NameObject("/Rotate")] = NumberObject(rotate)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def stamped(tmp_path: Path, src: bytes, text: str = "CONFIDENCIAL", **options) -> bytes:
    source = tmp_path / "box.pdf"
    source.write_bytes(src)
    out = tmp_path / "stamped"
    out.mkdir(exist_ok=True)
    layout = wm.Layout(**options)
    return wm.watermark(source, text, 1.0, layout, out).read_bytes()


def ink(clean: bytes, marked: bytes, index: int = 0):
    """The pixels that got darker: (bounding box, count, render width, render height)."""
    before = pdfium.PdfDocument(clean)[index].render(scale=SCALE).to_pil().convert("L")
    after = pdfium.PdfDocument(marked)[index].render(scale=SCALE).to_pil().convert("L")
    mask = ImageChops.subtract(before, after).point(lambda value: 255 if value > 60 else 0)
    return mask.getbbox(), mask.histogram()[255], before.width, before.height, mask


def aligned(low: float, high: float, side: float, margin: float, slot: int) -> bool:
    tolerance = 0.05 * side
    if slot == 0:
        return low <= margin + tolerance
    if slot == 2:
        return high >= side - margin - tolerance
    return abs((low + high) / 2 - side / 2) <= tolerance


def check_position(tmp_path, src: bytes, text: str, position: str, **options) -> str:
    """'' when the mark sits whole inside the visible box minus the margin, on its side."""
    bbox, count, width, height, _ = ink(
        src, stamped(tmp_path, src, text, position=position, **options)
    )
    if bbox is None:
        return "no mark"
    seen_w, seen_h = pdfium.PdfDocument(src)[0].get_size()
    clean = box_pdf([0, 0, seen_w, seen_h])
    _, reference, _, _, _ = ink(clean, stamped(tmp_path, clean, text, position=position, **options))
    margin = wm._MARGIN * min(width, height)
    x0, y0, x1, y1 = bbox
    column, row = wm._GRID[position]
    problems = []
    if not (
        x0 >= margin - 2
        and y0 >= margin - 2
        and x1 <= width - margin + 2
        and y1 <= height - margin + 2
    ):
        problems.append(f"outside {bbox} of {width}x{height}")
    # Rows count from the bottom; the render's y grows downwards.
    if not (
        aligned(x0, x1, width, margin, column)
        and aligned(height - y1, height - y0, height, margin, row)
    ):
        problems.append(f"not aligned {bbox}")
    if count < 0.95 * reference:
        problems.append(f"clipped {count}/{reference} px")
    return "; ".join(problems)


def all_boxes():
    yield from BOXES.items()
    yield INHERITED, ([0, 0, 612, 792], [36, 36, 400, 500], 90)


@pytest.mark.parametrize("rotation", wm.ROTATIONS)
@pytest.mark.parametrize(("name", "box"), list(all_boxes()))
def test_every_position_stays_whole_inside_the_visible_box(tmp_path, name, box, rotation):
    src = box_pdf(*box, inherit=name == INHERITED)
    problems = {
        position: problem
        for position in wm._GRID
        if (problem := check_position(tmp_path, src, "CONFIDENCIAL", position, rotation=rotation))
    }
    assert not problems, problems


def largest_size_that_fits(tmp_path, src: bytes, text: str, **options) -> float:
    size = 200.0
    while size > 8:
        try:
            stamped(tmp_path, src, text, size=size, **options)
            return size
        except AppError as error:
            assert error.code == "ERR_MARK_TOO_LARGE"
            size *= 0.9
    pytest.fail("not even 8 pt fits")


@pytest.mark.parametrize("rotation", [0, 180])
@pytest.mark.parametrize("text", ["Copia jpgy", "ÚLTIMA VERSIÓN"])
@pytest.mark.parametrize(("name", "box"), list(BOXES.items()))
def test_descenders_and_accents_stay_inside_at_the_largest_size(
    tmp_path, name, box, text, rotation
):
    # The box of the mark is the ink of these glyphs, not the cap height of the font.
    src = box_pdf(*box)
    problems = {}
    for position in wm._GRID:
        size = largest_size_that_fits(tmp_path, src, text, position=position, rotation=rotation)
        problem = check_position(tmp_path, src, text, position, rotation=rotation, size=size)
        if problem:
            problems[position] = f"{size:.0f} pt: {problem}"
    assert not problems, problems


def test_a_size_that_does_not_fit_is_refused_with_its_own_code(tmp_path):
    with pytest.raises(AppError) as caught:
        stamped(tmp_path, box_pdf([0, 0, 612, 792]), "x" * 40, position="top-left", size=200)
    assert caught.value.code == "ERR_MARK_TOO_LARGE" and caught.value.status == 400


@pytest.mark.parametrize(
    ("label", "text", "size"),
    [
        ("12 characters at 36 pt", "CONFIDENCIAL", 36),
        ("40 at 200 pt", "X" * 40, 200),
        ("1 at 8 pt", "X", 8),
    ],
)
@pytest.mark.parametrize(("name", "box"), list(BOXES.items()))
def test_the_mosaic_covers_the_whole_page_with_at_most_100_stamps(
    tmp_path, name, box, label, text, size
):
    src = box_pdf(*box)
    marked = stamped(tmp_path, src, text, position="mosaic", size=size)
    _, _, width, height, mask = ink(src, marked)
    cells = [
        mask.crop(
            (i * width // 4, j * height // 4, (i + 1) * width // 4, (j + 1) * height // 4)
        ).getbbox()
        for i in range(4)
        for j in range(4)
    ]
    assert all(cells), f"{sum(map(bool, cells))}/16 cells"
    assert PdfReader(io.BytesIO(marked)).pages[0].get_contents().get_data().count(b"Do") <= 100


def test_the_mosaic_is_not_text(tmp_path):
    marked = stamped(tmp_path, box_pdf([0, 0, 612, 792]), position="mosaic")
    assert "CONFIDENCIAL" not in PdfReader(io.BytesIO(marked)).pages[0].extract_text()
    assert "CONFIDENCIAL" not in pdfium.PdfDocument(marked)[0].get_textpage().get_text_bounded()


def test_the_mosaic_shares_one_form_for_the_document(tmp_path):
    marked = stamped(tmp_path, box_pdf([0, 0, 612, 792], pages=5), position="mosaic")
    forms = {
        ref.idnum
        for page in PdfReader(io.BytesIO(marked)).pages
        for ref in page["/Resources"]["/XObject"].values()
    }
    assert len(forms) == 1


@pytest.mark.parametrize(
    ("label", "crop", "rotate"),
    [
        ("/Rotate -90", None, -90),
        ("/Rotate 450", None, 450),
        ("/Rotate 45", None, 45),
        ("inverted CropBox", [400, 500, 36, 36], None),
        ("CropBox outside the MediaBox", [700, 900, 800, 1000], None),
    ],
)
def test_odd_page_geometry_still_gets_the_whole_mark(tmp_path, label, crop, rotate):
    src = box_pdf([0, 0, 612, 792], crop, rotate)
    marked = stamped(tmp_path, src)
    if label == "CropBox outside the MediaBox":
        # pdfium cannot draw a page with no visible area: compare both without the CropBox.
        src, marked = (box_pdf([0, 0, 612, 792], None, rotate), _without_crop(marked))
    bbox, count, width, height, _ = ink(src, marked)
    assert bbox and bbox[0] > 0 and bbox[1] > 0 and bbox[2] < width and bbox[3] < height, bbox


def _without_crop(data: bytes) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    for page in writer.pages:
        del page[NameObject("/CropBox")]
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_colour_is_written_as_numbers(tmp_path):
    marked = stamped(tmp_path, box_pdf([0, 0, 612, 792]), color=(0.2, 0.4, 0.6))
    # merge_page parses the stamp again, so the numbers come out in their shortest form.
    assert b"0.2 0.4 0.6 rg" in PdfReader(io.BytesIO(marked)).pages[0].get_contents().get_data()


def test_only_the_chosen_pages_get_the_mark(tmp_path):
    src = box_pdf([0, 0, 612, 792], pages=3)
    marked = stamped(tmp_path, src, pages="2")
    assert [ink(src, marked, index)[0] is not None for index in range(3)] == [False, True, False]


def test_a_page_named_twice_is_stamped_once(tmp_path):
    src = box_pdf([0, 0, 612, 792], pages=2)
    once = stamped(tmp_path, src, pages="1")
    thrice = stamped(tmp_path, src, pages="1,1,1-1")
    contents = [
        PdfReader(io.BytesIO(data)).pages[0].get_contents().get_data() for data in (once, thrice)
    ]
    assert contents[0] == contents[1]


@pytest.mark.parametrize(
    ("position", "rotation", "size", "color"),
    [
        ("", "", "", ""),
        ("mosaic", "0", "8", "#ABCDEF"),
        ("bottom-right", "270", "200", "#000000"),
    ],
)
def test_layout_accepts_the_form_values(position, rotation, size, color):
    wm.parse_layout(position, rotation, size, color, "")


def test_empty_fields_mean_the_defaults():
    assert wm.parse_layout("", "", "", "", "") == wm.Layout()


@pytest.mark.parametrize(
    "fields",
    [
        {"position": "middle"},
        {"rotation": "30"},
        {"rotation": "45.0"},
        {"size": "7"},
        {"size": "200.0001"},
        {"size": "nan"},
        {"size": "inf"},
        {"size": "-0"},
        {"size": "big"},
        {"color": "#12345"},
        {"color": "#123456\n"},
        {"color": "#１２３４５６"},
        {"color": "red"},
    ],
)
def test_layout_refuses_values_outside_the_contract(fields):
    values = {"position": "", "rotation": "", "size": "", "color": ""} | fields
    with pytest.raises(AppError) as caught:
        wm.parse_layout(values["position"], values["rotation"], values["size"], values["color"], "")
    assert caught.value.code == "ERR_INVALID_INPUT"
