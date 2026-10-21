"""Compress engine (tools/compress.py), measured before the API's output rule unless a test says so.

Every output goes through valid(): each reference reachable from the trailer resolves, and when the
engine made copies nothing unreachable is left. The cost cases at full scale (500 MB inputs, 1820
images of 49 MP) live in the vault's experiments; here the same shapes run with smaller limits.
"""

import ast
import io
import math
import sys
import zlib
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image, ImageChops, ImageStat
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    DictionaryObject,
    FloatObject,
    IndirectObject,
    NameObject,
    NumberObject,
    StreamObject,
)

from localpdf_hub import settings
from localpdf_hub.tools import compress

FIXTURES = Path(__file__).parent / "fixtures"
RECOMMENDED = compress.parse_level("recommended")
EXTREME = compress.parse_level("extreme")
# Approved 8 pt sheet (D6): mean grey difference of the paragraph against the input, 0-255.
# Measured 6.06 (recommended) and 11.40 (extreme); 120 dpi already gives 7.99.
PARAGRAPH = (300, 330, 2250, 700)


# --- building PDFs ---


def jpeg(size=(600, 600), mode="RGB", quality=85, seed=40, **kwargs) -> bytes:
    if mode == "CMYK":
        image = Image.new("CMYK", size, (10, 80, 30, 5))
    else:
        image = Image.effect_noise(size, seed).convert(mode)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=quality, **kwargs)
    return out.getvalue()


def image_stream(writer, data: bytes, extra=None, width=600, height=600):
    stream = StreamObject()
    stream._data = data
    entries = {
        "/Type": NameObject("/XObject"),
        "/Subtype": NameObject("/Image"),
        "/Width": NumberObject(width),
        "/Height": NumberObject(height),
        "/BitsPerComponent": NumberObject(8),
        "/ColorSpace": NameObject("/DeviceRGB"),
        "/Filter": NameObject("/DCTDecode"),
    }
    entries.update(extra or {})
    stream.update({NameObject(k): v for k, v in entries.items()})
    return writer._add_object(stream)


def contents(writer, data: bytes = b"q 144 0 0 144 0 0 cm /Im Do Q"):
    stream = StreamObject()
    stream._data = data
    return writer._add_object(stream)


def one_page(data: bytes, extra=None, size=(600, 600), side=144.0, page_extra=None) -> bytes:
    """One square page drawing one image; 600 px on 2 in is 300 dpi."""
    writer = PdfWriter()
    ref = image_stream(writer, data, extra, *size)
    page = writer.add_blank_page(side, side)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Im"): ref})}
    )
    page[NameObject("/Contents")] = contents(writer, b"q %f 0 0 %f 0 0 cm /Im Do Q" % (side, side))
    for key, value in (page_extra or {}).items():
        page[NameObject(key)] = value(writer) if callable(value) else value
    return write(writer)


def write(writer) -> bytes:
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def run(tmp_path, data: bytes, level=RECOMMENDED, name="in") -> bytes:
    """The engine without the output rule: what compress() writes before comparing sizes."""
    src = tmp_path / f"{name}.pdf"
    src.write_bytes(data)
    out = tmp_path / f"{name}_compressed.pdf"
    if level is None:
        compress._finish(PdfWriter(clone_from=compress.read_pdf(src)), out, copies=False)
    else:
        try:
            compress._lossy(src, level, out)
        except compress._FALLBACK_ERRORS:
            compress._finish(PdfWriter(clone_from=compress.read_pdf(src)), out, copies=False)
    result = out.read_bytes()
    assert valid(result, data)
    return result


def valid(data: bytes, source: bytes) -> bool:
    """Every reference reachable from the trailer resolves (unless it was dangling in the source)
    and no object is left unreachable."""
    return not dangling(data) - dangling(source) and not unreachable(data)


def _walk(reader) -> tuple[set[int], set[int]]:
    seen, broken = set(), set()
    stack = [
        reader.trailer.raw_get(key) for key in ("/Root", "/Info", "/ID") if key in reader.trailer
    ]
    while stack:
        item = stack.pop()
        if isinstance(item, IndirectObject):
            if item.idnum in seen | broken:
                continue
            try:
                target = item.get_object()
            except Exception:  # noqa: BLE001
                target = None
            if target is None:
                broken.add(item.idnum)
                continue
            seen.add(item.idnum)
            stack.append(target)
        elif isinstance(item, dict):
            stack.extend(item.raw_get(key) for key in item)
        elif isinstance(item, list):
            stack.extend(item)
    return seen, broken


def dangling(data: bytes) -> set[int]:
    return _walk(PdfReader(io.BytesIO(data)))[1]


def unreachable(data: bytes) -> set[int]:
    reader = PdfReader(io.BytesIO(data))
    seen, _ = _walk(reader)
    written = {idnum for table in reader.xref.values() for idnum in table} - {0}
    return written - seen


def images(data: bytes) -> list:
    out = []
    for page in PdfReader(io.BytesIO(data)).pages:
        resources = page.get("/Resources")
        xobjects = resources.get_object().get("/XObject") if resources is not None else None
        for ref in xobjects.get_object().values() if xobjects is not None else ():
            obj = ref.get_object()
            if obj.get("/Subtype") == "/Image":
                out.append(obj)
    return out


def streams(data: bytes) -> list[bytes]:
    return [obj._data for obj in images(data)]


def render(data: bytes, index: int = 0, dpi: int = 100) -> Image.Image:
    document = pdfium.PdfDocument(data)
    return document[index].render(scale=dpi / 72, draw_annots=True).to_pil().convert("RGB")


def diff(a: Image.Image, b: Image.Image, box=None, gray=False) -> float:
    if box:
        a, b = a.crop(box), b.crop(box)
    if gray:
        a, b = a.convert("L"), b.convert("L")
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / (1 if gray else 3)


def scan_pdf(pages: int = 3) -> bytes:
    """Letter pages of the approved scan (300 dpi, JPEG q85), one image each: the shape of F1."""
    data = (FIXTURES / "legibility_8pt.jpg").read_bytes()
    writer = PdfWriter()
    for _ in range(pages):
        ref = image_stream(writer, data, None, 2550, 3300)
        page = writer.add_blank_page(612, 792)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/XObject"): DictionaryObject({NameObject("/Im"): ref})}
        )
        page[NameObject("/Contents")] = contents(writer, b"q 612 0 0 792 0 0 cm /Im Do Q")
    return write(writer)


# --- contract ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [("", (150, 60)), ("recommended", (150, 60)), ("extreme", (100, 40)), ("lossless", None)],
)
def test_parse_level(text, expected):
    level = compress.parse_level(text)
    assert (None if level is None else (level.dpi, level.quality)) == expected


def test_parse_level_refuses_others():
    with pytest.raises(compress.AppError):
        compress.parse_level("low")


# --- what it compresses ---


def test_scan_goes_to_a_quarter_or_less(tmp_path):
    source = scan_pdf()
    recommended = run(tmp_path, source, name="r")
    extreme = run(tmp_path, source, EXTREME, name="e")
    assert len(recommended) / len(source) <= 0.25
    assert len(extreme) < len(recommended)
    for obj, page in zip(
        images(recommended), PdfReader(io.BytesIO(recommended)).pages, strict=True
    ):
        long_in = max(float(page.mediabox.width), float(page.mediabox.height)) / 72
        assert max(int(obj["/Width"]), int(obj["/Height"])) / long_in >= 150 * 0.999


def test_pypdfium2_writes_a_scan_it_compresses(tmp_path):
    scan = jpeg((2550, 3300), quality=85, seed=20)
    document = pdfium.PdfDocument.new()
    page = document.new_page(612, 792)
    image = pdfium.PdfImage.new(document)
    path = tmp_path / "scan.jpg"
    path.write_bytes(scan)
    image.load_jpeg(str(path), inline=False)
    image.set_matrix(pdfium.PdfMatrix().scale(612, 792))
    page.insert_obj(image)
    page.gen_content()
    out = io.BytesIO()
    document.save(out)
    source = out.getvalue()
    assert len(run(tmp_path, source)) / len(source) <= 0.25


@pytest.mark.skipif(sys.platform != "darwin", reason="Quartz is the macOS PDF writer")
def test_quartz_scan_keeps_its_colour_keys(tmp_path):
    import Quartz  # no importorskip: on macOS a missing module must fail
    from Foundation import NSURL

    jpg = tmp_path / "scan.jpg"
    jpg.write_bytes(jpeg((2550, 3300), quality=85, seed=20))
    source_path = tmp_path / "quartz.pdf"
    image = Quartz.CGImageSourceCreateImageAtIndex(
        Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(str(jpg)), None), 0, None
    )
    rect = Quartz.CGRectMake(0, 0, 612, 792)
    context = Quartz.CGPDFContextCreateWithURL(NSURL.fileURLWithPath_(str(source_path)), rect, None)
    Quartz.CGContextBeginPage(context, rect)
    Quartz.CGContextDrawImage(context, rect, image)
    Quartz.CGContextEndPage(context)
    Quartz.CGPDFContextClose(context)
    del context
    source = source_path.read_bytes()
    result = run(tmp_path, source)
    obj = images(result)[0]
    space = obj["/ColorSpace"]
    assert len(result) / len(source) <= 0.25
    assert space[0] == "/ICCBased" and "/Intent" in obj and "/Interpolate" in obj
    # Quartz writes the colour space as an indirect object: the new image keeps the reference.
    assert isinstance(images(result)[0].raw_get("/ColorSpace"), IndirectObject)


@pytest.mark.parametrize(("level", "quality"), [(RECOMMENDED, 60), (EXTREME, 40)])
def test_quality_tables_and_chroma(tmp_path, level, quality):
    result = run(tmp_path, one_page(jpeg()), level)
    reference = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(reference, "JPEG", quality=quality, subsampling=2)
    with Image.open(io.BytesIO(images(result)[0].get_data())) as out:
        assert out.quantization == Image.open(io.BytesIO(reference.getvalue())).quantization
        assert out.layers == 3 and out.layer[0][1:3] == (2, 2)  # 4:2:0


@pytest.mark.parametrize(("level", "limit"), [(RECOMMENDED, 7.0), (EXTREME, 12.5)])
def test_small_print_stays_readable(tmp_path, level, limit):
    writer = PdfWriter()
    ref = image_stream(writer, (FIXTURES / "legibility_8pt.jpg").read_bytes(), None, 2550, 3300)
    page = writer.add_blank_page(612, 792)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Im"): ref})}
    )
    page[NameObject("/Contents")] = contents(writer, b"q 612 0 0 792 0 0 cm /Im Do Q")
    source = write(writer)
    result = run(tmp_path, source, level)
    difference = diff(render(source, dpi=300), render(result, dpi=300), PARAGRAPH, gray=True)
    print(f"libjpeg {__import__('PIL.features', fromlist=['x']).version('jpg')}: {difference:.2f}")
    assert difference <= limit


# --- what it must not touch ---


def _untouched_cases():
    noise = Image.effect_noise((600, 600), 40)
    jpx = io.BytesIO()
    noise.convert("RGB").save(jpx, "JPEG2000")
    flate = {"/Filter": NameObject("/FlateDecode")}
    return {
        "cmyk": (jpeg(mode="CMYK"), {"/ColorSpace": NameObject("/DeviceCMYK")}),
        "indexed": (
            zlib.compress(noise.tobytes()),
            {
                **flate,
                "/ColorSpace": ArrayObject(
                    [
                        NameObject("/Indexed"),
                        NameObject("/DeviceRGB"),
                        NumberObject(255),
                        ByteStringObject(bytes(range(256)) * 3),
                    ]
                ),
            },
        ),
        "decode": (
            jpeg(mode="L"),
            {
                "/ColorSpace": NameObject("/DeviceGray"),
                "/Decode": ArrayObject([NumberObject(1), NumberObject(0)]),
            },
        ),
        "broken icc": (
            jpeg(),
            {"/ColorSpace": ArrayObject([NameObject("/ICCBased"), NumberObject(0)])},
        ),
        "jpx": (jpx.getvalue(), {"/Filter": NameObject("/JPXDecode")}),
        "oc": (jpeg(), {"/OC": DictionaryObject({NameObject("/Type"): NameObject("/OCG")})}),
        "struct": (jpeg(), {"/StructParent": NumberObject(3)}),
        "16 bits": (
            zlib.compress(noise.convert("I;16").tobytes()),
            {
                **flate,
                "/ColorSpace": NameObject("/DeviceGray"),
                "/BitsPerComponent": NumberObject(16),
            },
        ),
        "chained": (
            zlib.compress(jpeg()),
            {"/Filter": ArrayObject([NameObject("/FlateDecode"), NameObject("/DCTDecode")])},
        ),
        "flate rgb": (zlib.compress(noise.convert("RGB").tobytes()), flate),
        "color transform": (
            jpeg(),
            {"/DecodeParms": DictionaryObject({NameObject("/ColorTransform"): NumberObject(0)})},
        ),
        "more than 11 scans": (
            _with_scans(jpeg(progressive=True), settings.COMPRESS_MAX_SCANS + 1),
            {},
        ),
    }


def _with_scans(data: bytes, total: int) -> bytes:
    """A valid progressive JPEG with its last scan repeated up to `total` scans."""
    eoi = data.rindex(b"\xff\xd9")
    last = data.rindex(b"\xff\xda")
    return data[:eoi] + data[last:eoi] * (total - data.count(b"\xff\xda")) + data[eoi:]


@pytest.mark.parametrize("case", list(_untouched_cases()))
def test_untouched_images_keep_their_bytes(tmp_path, case):
    data, extra = _untouched_cases()[case]
    source = one_page(data, extra)
    assert streams(run(tmp_path, source)) == streams(source)


def test_a_jpeg_at_the_scan_cap_is_compressed(tmp_path):
    data = _with_scans(jpeg(progressive=True), settings.COMPRESS_MAX_SCANS)
    assert streams(run(tmp_path, one_page(data))) != [data]


def test_an_image_drawn_by_a_form_stays(tmp_path):
    writer = PdfWriter()
    ref = image_stream(writer, jpeg())
    form = StreamObject()
    form._data = b"/Fm Do /Im Do"
    form.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/BBox"): ArrayObject([NumberObject(0)] * 2 + [NumberObject(144)] * 2),
        }
    )
    form_ref = writer._add_object(form)
    form[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject(
                {NameObject("/Fm"): form_ref, NameObject("/Im"): ref}
            )
        }
    )
    page = writer.add_blank_page(144, 144)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject(
                {NameObject("/Fm"): form_ref, NameObject("/Im"): ref}
            )
        }
    )
    source = write(writer)
    # Listed by the page too, but a form draws it at a size nobody measured: the page keeps it.
    assert streams(run(tmp_path, source)) == streams(source)


def test_generations_do_not_eat_quality(tmp_path):
    first = run(tmp_path, one_page(jpeg()), name="a")
    second = run(tmp_path, first, name="b")
    assert streams(second) == streams(first)
    # The approved scan at 150 dpi: q60 and q75 gain less than 10 % at q60, q90 gains 43 %.
    with Image.open(FIXTURES / "legibility_8pt.jpg") as scan:
        half = scan.resize((1275, 1650), Image.Resampling.LANCZOS)
    for quality, replaced in ((60, False), (75, False), (90, True)):
        data = io.BytesIO()
        half.save(data, "JPEG", quality=quality)
        writer = PdfWriter()
        ref = image_stream(writer, data.getvalue(), None, 1275, 1650)
        page = writer.add_blank_page(612, 792)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/XObject"): DictionaryObject({NameObject("/Im"): ref})}
        )
        source = write(writer)
        assert (streams(run(tmp_path, source, name=f"q{quality}")) != streams(source)) == replaced


def test_shared_image_once_and_old_stream_dropped(tmp_path):
    writer = PdfWriter()
    ref = image_stream(writer, jpeg())
    for _ in range(2):
        page = writer.add_blank_page(144, 144)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/XObject"): DictionaryObject({NameObject("/Im"): ref})}
        )
    source = write(writer)
    result = run(tmp_path, source)
    assert [int(obj["/Width"]) for obj in images(result)] == [300, 300]
    assert result.count(b"/Subtype /Image") == 1


# --- page geometry and the page tree ---


def test_reversed_media_box_is_the_same_page(tmp_path):
    data = jpeg()
    normal = run(tmp_path, one_page(data), name="n")
    reversed_box = ArrayObject([FloatObject(v) for v in (144, 144, 0, 0)])
    flipped = run(tmp_path, one_page(data, page_extra={"/MediaBox": reversed_box}), name="f")
    assert streams(flipped) == streams(normal)


@pytest.mark.parametrize(
    "extra",
    [
        {"/MediaBox": ArrayObject([FloatObject(v) for v in (0, 0, 0, 144)])},
        {"/MediaBox": ArrayObject([FloatObject(v) for v in (0, 0, 144)])},
        {"/UserUnit": NumberObject(-1)},
        {"/UserUnit": NumberObject(0)},
        {"/UserUnit": NameObject("/Foo")},
    ],
)
def test_unusable_geometry_leaves_the_image(tmp_path, extra):
    source = one_page(jpeg(), page_extra=extra)
    assert streams(run(tmp_path, source)) == streams(source)


def test_user_unit_counts(tmp_path):
    source = one_page(
        jpeg((1200, 1200)), size=(1200, 1200), page_extra={"/UserUnit": NumberObject(2)}
    )
    assert int(images(run(tmp_path, source))[0]["/Width"]) >= 600  # 4 in at 150 dpi


def _tree(kind: str) -> bytes:
    """A page tree whose /Resources sit on /Pages nodes (re-audit v7, S1)."""
    writer = PdfWriter()
    letter = ArrayObject([NumberObject(0), NumberObject(0), NumberObject(612), NumberObject(792)])
    drawing = contents(writer, b"q 612 0 0 792 0 0 cm /Im Do Q")

    def resources(seed):
        ref = image_stream(writer, jpeg((1700, 2200), seed=25 + seed), None, 1700, 2200)
        inner = writer._add_object(DictionaryObject({NameObject("/Im"): ref}))
        return writer._add_object(DictionaryObject({NameObject("/XObject"): inner}))

    def page(parent, extra=None):
        entries = {
            NameObject("/Type"): NameObject("/Page"),
            NameObject("/MediaBox"): letter,
            NameObject("/Contents"): drawing,
            NameObject("/Parent"): parent,
        }
        entries.update({NameObject(k): v for k, v in (extra or {}).items()})
        return writer._add_object(DictionaryObject(entries))

    root_ref = writer._root_object.raw_get("/Pages")
    root = root_ref.get_object()
    if kind.startswith("deep"):
        shared = resources(0)
        a = DictionaryObject(
            {NameObject("/Type"): NameObject("/Pages"), NameObject("/Parent"): root_ref}
        )
        a_ref = writer._add_object(a)
        b = DictionaryObject(
            {NameObject("/Type"): NameObject("/Pages"), NameObject("/Parent"): a_ref}
        )
        b_ref = writer._add_object(b)
        kids = [page(b_ref) for _ in range(3)]
        b[NameObject("/Kids")], b[NameObject("/Count")] = ArrayObject(kids), NumberObject(3)
        a[NameObject("/Kids")], a[NameObject("/Count")] = ArrayObject([b_ref]), NumberObject(3)
        root[NameObject("/Kids")], root[NameObject("/Count")] = (
            ArrayObject([a_ref]),
            NumberObject(3),
        )
        {"deep_root": root, "deep_a": a, "deep_b": b}[kind][NameObject("/Resources")] = shared
    elif kind == "own_and_inherited":
        first = page(root_ref, {"/Resources": resources(1)})
        second = page(root_ref)
        root[NameObject("/Resources")] = resources(2)
        root[NameObject("/Kids")], root[NameObject("/Count")] = (
            ArrayObject([first, second]),
            NumberObject(2),
        )
    else:
        mid = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Pages"),
                NameObject("/Count"): NumberObject(1),
                NameObject("/Resources"): resources(0),
                NameObject("/Parent"): root_ref,
            }
        )
        mid_ref = writer._add_object(mid)
        mid[NameObject("/Kids")] = ArrayObject([page(mid_ref)])
        if kind == "cycle_parent":
            mid[NameObject("/Parent")] = mid_ref
        root[NameObject("/Kids")], root[NameObject("/Count")] = (
            ArrayObject([mid_ref]),
            NumberObject(1),
        )
    return write(writer)


@pytest.mark.parametrize(
    ("kind", "count"),
    [("deep_root", 1), ("deep_a", 1), ("deep_b", 1), ("cycle_parent", 1), ("own_and_inherited", 2)],
)
def test_inherited_resources_leave_no_old_image(tmp_path, kind, count):
    result = run(tmp_path, _tree(kind))
    assert result.count(b"/Subtype /Image") == count
    assert {int(obj["/Width"]) for obj in images(result)} == {1275}


def _shared_outside(kind: str) -> bytes:
    """The page's /XObject (or its /Resources) is also used by something the walk does not visit."""
    writer = PdfWriter()
    ref = image_stream(writer, jpeg((1200, 1200)), None, 1200, 1200)
    if kind == "resources":
        page_resources = writer._add_object(
            DictionaryObject({NameObject("/XObject"): DictionaryObject({NameObject("/Im"): ref})})
        )
        outside = page_resources
    else:
        shared = writer._add_object(DictionaryObject({NameObject("/Im"): ref}))
        page_resources = DictionaryObject({NameObject("/XObject"): shared})
        outside = DictionaryObject({NameObject("/XObject"): shared})
    first = writer.add_blank_page(144, 144)
    first[NameObject("/Resources")] = page_resources
    first[NameObject("/Contents")] = contents(writer)
    second = writer.add_blank_page(576, 576)
    box = ArrayObject([FloatObject(0), FloatObject(0), FloatObject(576), FloatObject(576)])
    body = StreamObject()
    body._data = b"q 576 0 0 576 0 0 cm /Im Do Q"
    body.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/BBox"): box,
            NameObject("/Resources"): outside,
        }
    )
    annotation = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Stamp"),
            NameObject("/Rect"): box,
            NameObject("/AP"): DictionaryObject({NameObject("/N"): writer._add_object(body)}),
        }
    )
    second[NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])
    second[NameObject("/Contents")] = contents(writer, b"")
    return write(writer)


@pytest.mark.parametrize("kind", ["xobject", "resources"])
def test_copy_on_write_keeps_what_others_draw(tmp_path, kind):
    source = _shared_outside(kind)
    result = run(tmp_path, source)
    assert int(images(result)[0]["/Width"]) == 300
    assert diff(render(source, 1, 150), render(result, 1, 150)) < 0.01


# --- bounds and failures ---


def test_content_with_a_million_draws_is_not_parsed(tmp_path):
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(one_page(jpeg((600, 600), mode="CMYK")))))
    stream = writer.pages[0]["/Contents"].get_object()
    stream._data = zlib.compress(b"q 144 0 0 144 0 0 cm /Im Do Q\n" * 1_000_000)
    stream[NameObject("/Filter")] = NameObject("/FlateDecode")
    source = write(writer)
    assert run(tmp_path, source, name="r") == run(tmp_path, source, None, name="l")


def test_work_cap_falls_back_to_lossless(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "COMPRESS_MAX_WORK", 3)
    source = one_page(jpeg())
    assert streams(run(tmp_path, source)) == streams(source)


def test_budget_cut_with_identical_images_stays_readable(tmp_path, monkeypatch):
    # The cut leaves identical old images on some pages while copies orphan others: run() checks
    # that every page still finds its image (pypdf's dedupe once kept an orphan and dropped it).
    monkeypatch.setattr(settings, "COMPRESS_PIXEL_BUDGET", 5 * 300 * 300)
    data = jpeg()
    writer = PdfWriter()
    for _ in range(20):
        ref = image_stream(writer, data)
        page = writer.add_blank_page(144, 144)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/XObject"): DictionaryObject({NameObject("/Im"): ref})}
        )
    assert len(run(tmp_path, write(writer))) > 0


@pytest.mark.parametrize("target", ["_sweep", "_rewrite_resources"])
def test_a_failure_while_rewriting_gives_the_lossless_result(tmp_path, monkeypatch, target):
    source = _tree("deep_a")
    src = tmp_path / "in.pdf"
    src.write_bytes(source)

    def broken(*_args, **_kwargs):
        raise KeyError("injected")

    monkeypatch.setattr(compress, target, broken)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = compress.compress(src, RECOMMENDED, out_dir).read_bytes()
    assert valid(result, source)
    assert streams(result) == streams(source)


def test_indirect_id_survives_the_sweep(tmp_path):
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(_tree("deep_a"))))
    first, second = b"\x01" * 16, b"\x02" * 16
    writer._ID = ArrayObject(
        [writer._add_object(ByteStringObject(first)), writer._add_object(ByteStringObject(second))]
    )
    result = run(tmp_path, write(writer))
    identifiers = PdfReader(io.BytesIO(result)).trailer.raw_get("/ID")
    assert all(isinstance(item, IndirectObject) for item in identifiers)
    assert [item.get_object().original_bytes for item in identifiers] == [first, second]


def test_broken_and_bomb_jpegs_stay(tmp_path):
    truncated = jpeg()[:-200]
    bomb = io.BytesIO()
    Image.new("L", (14000, 14000), 200).save(bomb, "JPEG", quality=50)
    for data, extra, size in (
        (truncated, None, (600, 600)),
        (bomb.getvalue(), {"/ColorSpace": NameObject("/DeviceGray")}, (14000, 14000)),
    ):
        source = one_page(data, extra, size)
        assert streams(run(tmp_path, source)) == streams(source)


def test_root_xobject_nobody_inherits_never_grows_the_file(tmp_path):
    # The /Pages root lists the image but no page inherits it: the old image stays for it, so the
    # output rule hands back the input (CONOCIMIENTO.md, T4).
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(one_page(jpeg()))))
    image_ref = writer.pages[0]["/Resources"]["/XObject"].raw_get("/Im")
    root = writer._root_object["/Pages"].get_object()
    root[NameObject("/XObject")] = DictionaryObject({NameObject("/Im"): image_ref})
    src = tmp_path / "in.pdf"
    src.write_bytes(write(writer))
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out = compress.compress(src, RECOMMENDED, out_dir)
    assert out.stat().st_size <= src.stat().st_size


def test_private_pypdf_state_the_sweep_reads():
    writer = PdfWriter()
    reference = writer._add_object(StreamObject())
    assert isinstance(reference, IndirectObject) and reference.pdf is writer
    assert isinstance(writer._objects, list)
    assert isinstance(writer._root_object, DictionaryObject)
    assert isinstance(writer._info, DictionaryObject)
    assert hasattr(writer, "_ID") and hasattr(writer, "_encrypt_entry")


def test_engine_does_not_import_pdfium():
    # pdfium is not thread-safe; the engine runs in job threads.
    tree = ast.parse(Path(compress.__file__).read_text(encoding="utf-8"))
    names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    names |= {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(name and name.startswith("pypdfium2") for name in names)


def test_draft_pixels_match_pillow():
    data = jpeg((1200, 900))
    for size in ((1200, 900), (590, 440), (300, 225), (100, 80)):
        with Image.open(io.BytesIO(data)) as image:
            image.draft("RGB", size)
            assert compress._draft_pixels(1200, 900, size) == image.size[0] * image.size[1]
    assert math.isclose(compress._draft_pixels(1200, 900, (150, 112)), 150 * 113, rel_tol=0.02)


def _shared_dict(second_page: dict) -> bytes:
    """One /XObject dict on a 2 in page and on a second page."""
    writer = PdfWriter()
    ref = image_stream(writer, jpeg())
    shared = writer._add_object(DictionaryObject({NameObject("/Im"): ref}))
    first = writer.add_blank_page(144, 144)
    first[NameObject("/Resources")] = DictionaryObject({NameObject("/XObject"): shared})
    other = writer.add_blank_page(second_page.get("side", 144), second_page.get("side", 144))
    other[NameObject("/Resources")] = DictionaryObject({NameObject("/XObject"): shared})
    for key, value in second_page.items():
        if key != "side":
            other[NameObject(key)] = value
    return write(writer)


def test_the_largest_page_sets_the_dpi(tmp_path):
    # 600 px is 300 dpi on the 2 in page and 75 dpi on the 8 in one: it must not shrink.
    result = run(tmp_path, _shared_dict({"side": 576}))
    assert {int(obj["/Width"]) for obj in images(result)} == {600}


def test_a_shared_dict_on_an_unusable_page_stays_everywhere(tmp_path):
    source = _shared_dict({"/UserUnit": NumberObject(-1)})
    assert streams(run(tmp_path, source)) == streams(source)
