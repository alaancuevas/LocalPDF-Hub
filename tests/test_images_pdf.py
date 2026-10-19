"""HTTP contract of Image to PDF and of how /merge places images (docs/api.md).

Page sizes and placement are the ones measured in
4.1; "fit" keeps the rule from before 4.1.
"""

import io
import re
import struct
import zipfile
import zlib
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient
from PIL import EpsImagePlugin, Image, ImageChops, ImageDraw, ImageOps, ImageStat
from pypdf import PdfReader, PdfWriter

from localpdf_hub.app import create_app

ORIGIN = "http://127.0.0.1:8000"
FIXTURES = Path(__file__).parent / "fixtures"
A4 = (595, 842)
LETTER = (612, 792)


@pytest.fixture(scope="module")
def client() -> TestClient:
    test_client = TestClient(create_app(), base_url=ORIGIN)
    page = test_client.get("/").text
    token = re.search(r'<meta name="localpdf-token" content="([^"]+)"', page).group(1)
    test_client.headers.update({"X-LocalPDF-Token": token, "Origin": ORIGIN})
    return test_client


# --- helpers ---


def encode(image: Image.Image, fmt: str, **options) -> bytes:
    buf = io.BytesIO()
    image.save(buf, fmt, **options)
    return buf.getvalue()


def png(size=(60, 40), color="blue", mode="RGB") -> bytes:
    return encode(Image.new(mode, size, color), "PNG")


def marked(size=(60, 40)) -> Image.Image:
    """Asymmetric picture: a wrong turn or flip changes most pixels."""
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    w, h = size
    draw.rectangle([0, 0, w // 2 - 1, h // 2 - 1], fill="red")
    draw.rectangle([w // 2, 0, w - 1, h // 4 - 1], fill="blue")
    draw.rectangle([0, h * 3 // 4, w // 6, h - 1], fill="green")
    return image


def jpeg(image: Image.Image | None = None, **options) -> bytes:
    return encode(image or marked(), "JPEG", quality=95, **options)


def blank_pdf(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def post(client, tool, items, **fields):
    files = [("files", (name, data, "application/octet-stream")) for name, data in items]
    return client.post(f"/api/v1/pdf/{tool}", files=files, data=fields)


def to_pdf(client, data: bytes, name: str = "a.png", **fields):
    response = post(client, "images-to-pdf", [(name, data)], **fields)
    assert response.status_code == 200, response.text
    return response


def reader(response) -> PdfReader:
    return PdfReader(io.BytesIO(response.content))


def page_size(page) -> tuple[float, float]:
    return float(page.mediabox.width), float(page.mediabox.height)


def image_box(page) -> tuple[float, float, float, float]:
    """x0, y0, x1, y1 of the image drawn on the page."""
    for operands, operator in page.get_contents().operations:
        if operator == b"cm":
            a, b, c, d, e, f = (float(value) for value in operands)
            xs = [e, a + e, c + e, a + c + e]
            ys = [f, b + f, d + f, b + d + f]
            return min(xs), min(ys), max(xs), max(ys)
    raise AssertionError("no image on the page")


def xobject(page):
    return page["/Resources"]["/XObject"]["/Im0"].get_object()


def rendered(response, index: int = 0) -> Image.Image:
    document = pdfium.PdfDocument(response.content)
    return document[index].render(scale=1).to_pil().convert("RGB")


def mean_difference(first: Image.Image, second: Image.Image) -> float:
    difference = ImageChops.difference(first.convert("RGB"), second.convert("RGB"))
    return sum(ImageStat.Stat(difference).mean) / 3


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


def scan(data: bytes) -> bytes:
    return data[data.index(b"\xff\xda") :]


# --- page size and placement ---


@pytest.mark.parametrize(
    ("fields", "size"),
    [
        ({}, A4),
        ({"orientation": "landscape"}, A4[::-1]),
        ({"pagesize": "letter"}, LETTER),
        ({"pagesize": "letter", "orientation": "landscape"}, LETTER[::-1]),
    ],
)
def test_page_sizes(client, fields, size):
    page = reader(to_pdf(client, png(), **fields)).pages[0]
    assert page_size(page) == pytest.approx(size, abs=0.01)


def test_margin_keeps_the_image_inside_and_touches_two_sides(client):
    page = reader(to_pdf(client, png((300, 100)), margin="40")).pages[0]
    x0, y0, x1, y1 = image_box(page)
    assert x0 == pytest.approx(40, abs=0.01)
    assert x1 == pytest.approx(A4[0] - 40, abs=0.01)
    assert y0 > 40
    assert y1 < A4[1] - 40


def test_a_small_image_is_enlarged_to_fit_and_centred(client):
    # A 100 x 100 px image is drawn at 595 x 595 pt on A4.
    page = reader(to_pdf(client, png((100, 100)))).pages[0]
    x0, y0, x1, y1 = image_box(page)
    assert (x1 - x0, y1 - y0) == pytest.approx((595, 595), abs=0.01)
    assert y0 == pytest.approx((842 - 595) / 2, abs=0.01)


@pytest.mark.parametrize(
    ("size", "drawn"),
    [((4032, 3024), (841.68, 631.26)), ((100, 50), (100, 50))],
)
def test_fit_keeps_the_rule_from_before_with_its_72_dpi_floor(client, size, drawn):
    page = reader(to_pdf(client, png(size), pagesize="fit", margin="20")).pages[0]
    assert page_size(page) == pytest.approx((drawn[0] + 40, drawn[1] + 40), abs=0.01)
    x0, y0, x1, y1 = image_box(page)
    assert (x0, y0) == pytest.approx((20, 20), abs=0.01)
    assert (x1 - x0, y1 - y0) == pytest.approx(drawn, abs=0.01)


# --- JPEG goes in without re-encoding, and without its metadata ---


def gps_jpeg() -> bytes:
    exif = Image.Exif()
    exif[0x0110] = "Test camera"
    exif.get_ifd(0x8825).update({1: "N", 2: (40.0, 26.0, 46.0)})
    return jpeg(exif=exif.tobytes())


def test_a_jpeg_scan_goes_in_untouched(client):
    original = gps_jpeg()
    image = xobject(reader(to_pdf(client, original, "a.jpg")).pages[0])
    assert image["/Filter"] == "/DCTDecode"
    assert scan(image.get_data()) == scan(original)


def test_a_jpeg_loses_its_gps_and_camera_data(client):
    data = xobject(reader(to_pdf(client, gps_jpeg(), "a.jpg")).pages[0]).get_data()
    assert b"Exif" not in data
    assert b"Test camera" not in data
    with Image.open(io.BytesIO(data)) as image:
        assert not image.getexif().get_ifd(0x8825)


def test_a_progressive_jpeg_with_an_end_marker_inside_a_comment_survives(client):
    # A comment between two scans may legally hold the bytes FF D9.
    data = jpeg(progressive=True)
    second_scan = data.index(b"\xff\xda", data.index(b"\xff\xda") + 2)
    tricky = data[:second_scan] + b"\xff\xfe\x00\x04\xff\xd9" + data[second_scan:]
    Image.open(io.BytesIO(tricky)).load()
    response = to_pdf(client, tricky, "a.jpg")
    out = xobject(reader(response).pages[0]).get_data()
    assert len(out) == len(tricky) - 6
    Image.open(io.BytesIO(out)).load()


def test_an_mpo_keeps_only_its_first_frame(client):
    first = marked()
    data = encode(first, "MPO", save_all=True, append_images=[Image.new("RGB", (60, 40), "black")])
    out = xobject(reader(to_pdf(client, data, "a.jpg")).pages[0]).get_data()
    assert len(out) < len(data) / 1.5
    assert out.endswith(b"\xff\xd9")
    with Image.open(io.BytesIO(out)) as image:
        assert mean_difference(image, first) < 8


def test_a_png_named_jpg_is_read_by_its_content(client):
    image = xobject(reader(to_pdf(client, png(), "a.jpg")).pages[0])
    assert image["/Filter"] == "/FlateDecode"


ORIENTATIONS = [(orientation, turn) for orientation in range(1, 9) for turn in (0, 90)]


@pytest.mark.parametrize(("orientation", "turn"), ORIENTATIONS)
def test_exif_orientation_and_rotation_go_in_the_matrix(client, orientation, turn):
    exif = Image.Exif()
    exif[0x0112] = orientation
    data = jpeg(exif=exif.tobytes())
    expected = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    if turn:
        expected = expected.rotate(-turn, expand=True)
    # "fit" with a small image keeps 1 px = 1 pt, so the render compares pixel to pixel.
    response = to_pdf(client, data, "a.jpg", pagesize="fit", rotations=str(turn))
    assert scan(xobject(reader(response).pages[0]).get_data()) == scan(data)
    picture = rendered(response)
    assert picture.size == expected.size
    # A wrong map differs by 40 or more (measured for the plan).
    assert mean_difference(picture, expected) <= 8


@pytest.mark.parametrize("orientation", [0, 9])
def test_an_unknown_orientation_counts_as_upright(client, orientation):
    exif = Image.Exif()
    exif[0x0112] = orientation
    data = jpeg(exif=exif.tobytes())
    response = to_pdf(client, data, "a.jpg", pagesize="fit")
    assert mean_difference(rendered(response), marked()) <= 8


# --- every image mode ---


@pytest.mark.parametrize("mode", ["RGB", "L"])
def test_png_pixels_come_back_identical(client, mode):
    source = Image.effect_noise((64, 48), 60).convert(mode)
    image = reader(to_pdf(client, encode(source, "PNG"))).pages[0].images[0].image
    assert ImageChops.difference(image.convert(mode), source).getbbox() is None


def transparent_corner_rgba() -> Image.Image:
    image = Image.new("RGBA", (40, 40), (255, 0, 0, 0))
    ImageDraw.Draw(image).rectangle([10, 10, 29, 29], fill=(0, 0, 255, 255))
    return image


def palette_with_trns() -> bytes:
    image = Image.new("P", (40, 40), 0)
    image.putpalette([255, 0, 0, 0, 0, 255] + [0] * 762)
    ImageDraw.Draw(image).rectangle([10, 10, 29, 29], fill=1)
    return encode(image, "PNG", transparency=0)


def associated_alpha_tiff() -> bytes:
    # Pillow writes LA with unassociated alpha; ExtraSamples = 1 makes it open as "La".
    image = Image.new("LA", (40, 40), (0, 0))
    ImageDraw.Draw(image).rectangle([10, 10, 29, 29], fill=(0, 255))
    data = encode(image, "TIFF")
    extra_samples = b"\x52\x01\x03\x00\x01\x00\x00\x00"
    return data.replace(extra_samples + b"\x02\x00", extra_samples + b"\x01\x00")


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("rgba.png", encode(transparent_corner_rgba(), "PNG")),
        ("la.png", encode(transparent_corner_rgba().convert("LA"), "PNG")),
        ("palette.png", palette_with_trns()),
        (
            "key.png",
            encode(Image.new("RGB", (40, 40), (255, 0, 0)), "PNG", transparency=(255, 0, 0)),
        ),
        ("la.tif", associated_alpha_tiff()),
    ],
    ids=["rgba.png", "la.png", "palette.png", "key.png", "la.tif"],
)
def test_transparent_pixels_come_out_white(client, name, data):
    if name == "la.tif":
        assert Image.open(io.BytesIO(data)).mode == "La"
    response = to_pdf(client, data, name, pagesize="fit")
    assert "/SMask" in xobject(reader(response).pages[0])
    assert rendered(response).getpixel((1, 1)) == (255, 255, 255)


def test_16_bit_gray_is_scaled_not_clipped(client):
    data = encode(Image.new("I;16", (8, 8), 40000), "PNG")
    image = reader(to_pdf(client, data)).pages[0].images[0].image
    assert image.convert("L").getpixel((0, 0)) == 155


def test_one_bit_images_become_gray(client):
    image = xobject(reader(to_pdf(client, encode(Image.new("1", (8, 8), 1), "PNG"))).pages[0])
    assert image["/ColorSpace"] == "/DeviceGray"


@pytest.mark.parametrize("mode", ["CMYK", "YCbCr", "LAB"])
def test_tiff_colour_modes_become_rgb(client, mode):
    data = encode(Image.new("RGB", (8, 8), (200, 40, 40)).convert(mode), "TIFF")
    image = xobject(reader(to_pdf(client, data, "a.tif")).pages[0])
    assert (image["/Filter"], image["/ColorSpace"]) == ("/FlateDecode", "/DeviceRGB")


def test_a_cmyk_jpeg_is_reencoded_as_rgb(client):
    data = encode(Image.new("CMYK", (8, 8), (0, 200, 200, 0)), "JPEG")
    image = xobject(reader(to_pdf(client, data, "a.jpg")).pages[0])
    assert (image["/Filter"], image["/ColorSpace"]) == ("/DCTDecode", "/DeviceRGB")


def test_heic_becomes_a_full_size_jpeg(client):
    response = to_pdf(client, (FIXTURES / "photo.heic").read_bytes(), "photo.heic")
    image = xobject(reader(response).pages[0])
    assert image["/Filter"] == "/DCTDecode"
    assert (image["/Width"], image["/Height"]) == (64, 48)


def test_a_tiff_with_two_pages_gives_its_first(client):
    first = Image.new("RGB", (40, 30), "red")
    data = encode(first, "TIFF", save_all=True, append_images=[Image.new("RGB", (80, 60), "blue")])
    pages = reader(to_pdf(client, data, "a.tif")).pages
    assert len(pages) == 1
    assert (xobject(pages[0])["/Width"], xobject(pages[0])["/Height"]) == (40, 30)


def test_an_unsupported_mode_is_refused(client):
    data = encode(Image.new("F", (8, 8)), "TIFF")
    assert_error(post(client, "images-to-pdf", [("a.tif", data)]), 400, "ERR_INVALID_INPUT")


# --- hostile and broken files ---


def test_postscript_named_png_never_reaches_ghostscript(client, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("the EPS reader must not run")

    monkeypatch.setattr(EpsImagePlugin.EpsImageFile, "_open", refuse)
    data = b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\nshowpage\n"
    assert_error(post(client, "images-to-pdf", [("evil.png", data)]), 400, "ERR_INVALID_INPUT")


def broken_huffman_table() -> bytes:
    # Every segment is in place, so only decoding finds the damage.
    data = jpeg(Image.effect_noise((300, 200), 50).convert("RGB"))
    table = data.index(b"\xff\xc4")
    return data[: table + 5] + bytes(16) + data[table + 21 :]


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("cut.jpg", jpeg()[: len(jpeg()) // 3]),
        ("huffman.jpg", broken_huffman_table()),
        ("junk.png", b"not an image at all"),
    ],
    ids=["cut.jpg", "huffman.jpg", "junk.png"],
)
def test_a_broken_image_is_refused(client, name, data):
    assert_error(post(client, "images-to-pdf", [(name, data)]), 400, "ERR_INVALID_INPUT")


def png_header(width: int, height: int) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = struct.pack(">I", zlib.crc32(kind + body))
        return struct.pack(">I", len(body)) + kind + body + crc

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IEND", b"")


@pytest.mark.parametrize("side", [7100, 14000])
def test_too_many_pixels_is_refused_from_the_header(client, side):
    # 14000 x 14000 is a decompression bomb for Pillow; neither is decoded.
    response = post(client, "images-to-pdf", [("big.png", png_header(side, side))])
    assert_error(response, 413, "ERR_IMAGE_TOO_LARGE")


# --- limits ---


def test_two_hundred_images_pass_and_one_more_does_not(client):
    tiny = png((1, 1))
    assert (
        post(client, "images-to-pdf", [(f"{i}.png", tiny) for i in range(200)]).status_code == 200
    )
    response = post(client, "images-to-pdf", [(f"{i}.png", tiny) for i in range(201)])
    assert_error(response, 413, "ERR_TOO_MANY_IMAGES")


def test_the_image_limit_counts_images_only(client):
    items = [(f"{i}.pdf", blank_pdf()) for i in range(201)]
    assert post(client, "merge", items).status_code == 200


def test_images_count_as_pages(client, monkeypatch):
    from localpdf_hub import settings

    monkeypatch.setattr(settings, "MAX_PAGES", 3)
    response = post(client, "merge", [("a.pdf", blank_pdf(2)), ("b.png", png()), ("c.png", png())])
    assert_error(response, 413, "ERR_TOO_MANY_PAGES")


def noise_png() -> bytes:
    """About 43 KB of image stream: noise barely compresses."""
    bands = [Image.effect_noise((120, 120), 80) for _ in range(3)]
    return encode(Image.merge("RGB", bands), "PNG")


@pytest.mark.parametrize(
    ("tool", "fields"),
    [("images-to-pdf", {}), ("images-to-pdf", {"merge_after": "false"}), ("merge", {})],
)
def test_the_result_stops_at_its_byte_limit(client, monkeypatch, tool, fields):
    from localpdf_hub import settings

    monkeypatch.setattr(settings, "MAX_RESULT_BYTES", 60_000)
    assert post(client, tool, [("a.png", noise_png())], **fields).status_code == 200
    items = [("a.png", noise_png()), ("b.png", noise_png())]
    assert_error(post(client, tool, items, **fields), 413, "ERR_RESULT_TOO_LARGE")


def test_the_alpha_channel_counts_towards_the_byte_limit(client, monkeypatch):
    from localpdf_hub import settings

    # About 43 KB of colour plus 14 KB of alpha.
    bands = [Image.effect_noise((120, 120), 80) for _ in range(4)]
    data = encode(Image.merge("RGBA", bands), "PNG")
    monkeypatch.setattr(settings, "MAX_RESULT_BYTES", 50_000)
    assert_error(post(client, "images-to-pdf", [("a.png", data)]), 413, "ERR_RESULT_TOO_LARGE")


def test_merge_counts_only_the_images_against_the_byte_limit(client, monkeypatch):
    from localpdf_hub import settings

    monkeypatch.setattr(settings, "MAX_RESULT_BYTES", 60_000)
    bands = [Image.effect_noise((300, 300), 80) for _ in range(3)]
    heavy = encode(Image.merge("RGB", bands), "PDF", quality=95)
    assert len(heavy) > 60_000
    assert post(client, "merge", [("a.pdf", heavy), ("b.png", noise_png())]).status_code == 200


# --- contract ---


def encrypted_pdf() -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(blank_pdf())))
    writer.encrypt(user_password="s3cret", owner_password="owner", algorithm="AES-256")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.mark.parametrize("data", [blank_pdf(), encrypted_pdf()], ids=["plain", "encrypted"])
def test_a_pdf_is_not_an_image(client, data):
    assert_error(post(client, "images-to-pdf", [("a.pdf", data)]), 400, "ERR_INVALID_INPUT")


@pytest.mark.parametrize(
    "fields", [{"pagesize": "foo"}, {"margin": "13"}, {"margin": "abc"}, {"orientation": "x"}]
)
def test_invalid_options_are_refused(client, fields):
    response = post(client, "images-to-pdf", [("a.png", png())], **fields)
    assert_error(response, 400, "ERR_INVALID_INPUT")


def filename_of(response) -> str:
    return re.search(r'filename="?([^";]+)', response.headers["content-disposition"]).group(1)


def test_merged_images_are_named_after_the_first(client):
    response = post(client, "images-to-pdf", [("a.png", png()), ("b.png", png())])
    assert filename_of(response) == "a.pdf"
    assert len(reader(response).pages) == 2


def test_unmerged_images_give_a_zip_with_one_pdf_each_in_order(client):
    items = [("a.png", png()), ("b.jpg", jpeg()), ("c.png", png()), ("a.png", png())]
    response = post(client, "images-to-pdf", items, merge_after="false")
    assert response.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert names == ["a.pdf", "b.pdf", "c.pdf", "003_a.pdf"]


def test_merge_places_images_on_a4_by_default(client):
    response = post(client, "merge", [("a.pdf", blank_pdf()), ("b.png", png())])
    assert page_size(reader(response).pages[1]) == pytest.approx(A4, abs=0.01)


def test_merge_takes_the_page_options(client):
    items = [("a.pdf", blank_pdf()), ("b.png", png((300, 100)))]
    page = reader(
        post(client, "merge", items, pagesize="letter", orientation="landscape", margin="20")
    ).pages[1]
    assert page_size(page) == pytest.approx(LETTER[::-1], abs=0.01)
    assert image_box(page)[0] == pytest.approx(20, abs=0.01)


def test_pypdf_private_api():
    # images_pdf.py adds streams with PdfWriter._add_object (no public twin in pypdf 6).
    assert callable(getattr(PdfWriter, "_add_object", None))
