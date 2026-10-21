"""HTTP contract of the v4 API (docs/api.md).

These tests are written against the contract, not the code: when the
implementation is reorganised they must keep passing unchanged.
"""

import contextlib
import io
import mimetypes
import re
import threading
import time
import tracemalloc
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PasswordType, PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions

from localpdf_hub import platform as host
from localpdf_hub import settings
from localpdf_hub.app import create_app
from localpdf_hub.errors import AppError
from localpdf_hub.tools import images, pages

ORIGIN = "http://127.0.0.1:8000"


@pytest.fixture(scope="module")
def client() -> TestClient:
    test_client = TestClient(create_app(), base_url=ORIGIN)
    page = test_client.get("/").text
    token = re.search(r'<meta name="localpdf-token" content="([^"]+)"', page).group(1)
    test_client.headers.update({"X-LocalPDF-Token": token, "Origin": ORIGIN})
    return test_client


def pdf(pages: int = 1, rotation: int = 0, size: float = 200) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=size, height=size)
        if rotation:
            page.rotate(rotation)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def pdf_with_image() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), "red").save(buf, "PDF")
    return buf.getvalue()


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), "blue").save(buf, "PNG")
    return buf.getvalue()


def post(client, tool, files, **fields):
    return client.post(f"/api/v1/pdf/{tool}", files=files, data=fields)


def one(name: str, data: bytes, mime: str = "application/pdf"):
    return [("file", (name, data, mime))]


def many(*items):
    return [("files", item) for item in items]


def pages_of(response) -> list:
    return PdfReader(io.BytesIO(response.content)).pages


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == code


def filename_of(response) -> str:
    return re.search(r'filename="?([^";]+)', response.headers["content-disposition"]).group(1)


# --- merge ---


def test_merge_pdfs_and_images_in_order(client):
    response = post(
        client,
        "merge",
        many(("a.pdf", pdf(2), "application/pdf"), ("b.png", png(), "image/png")),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert len(pages_of(response)) == 3


def test_merge_keeps_files_with_the_same_name(client):
    response = post(
        client,
        "merge",
        many(("a.pdf", pdf(1), "application/pdf"), ("a.pdf", pdf(2), "application/pdf")),
    )
    assert len(pages_of(response)) == 3


def test_merge_rotations_add_to_existing_rotation(client):
    response = post(
        client,
        "merge",
        many(
            ("a.pdf", pdf(1, rotation=90), "application/pdf"), ("b.pdf", pdf(1), "application/pdf")
        ),
        rotations="90,180",
    )
    assert [page.rotation for page in pages_of(response)] == [180, 180]


# --- split ---


def test_split_by_range(client):
    response = post(client, "split", one("a.pdf", pdf(3)), **{"from": "2", "to": "3"})
    assert response.status_code == 200
    assert len(pages_of(response)) == 2


def test_split_by_page_list(client):
    response = post(client, "split", one("a.pdf", pdf(3)), pages="1,3")
    assert len(pages_of(response)) == 2


@pytest.mark.parametrize("fields", [{"from": "3", "to": "1"}, {"pages": "5"}, {"pages": ""}])
def test_split_with_no_valid_page_is_rejected(client, fields):
    assert_error(post(client, "split", one("a.pdf", pdf(3)), **fields), 400, "ERR_NO_PAGES")


# --- rotate ---


def test_rotate_each_page(client):
    response = post(client, "rotate", one("a.pdf", pdf(3)), rotations="90,0,270")
    assert [page.rotation for page in pages_of(response)] == [90, 0, 270]


def test_rotate_rejects_angles_that_are_not_multiples_of_90(client):
    response = post(client, "rotate", one("a.pdf", pdf(1)), rotations="45")
    assert_error(response, 400, "ERR_INVALID_INPUT")


# --- compress ---


def test_compress_returns_a_pdf(client):
    response = post(client, "compress", one("a.pdf", pdf(2)))
    assert response.status_code == 200
    assert len(pages_of(response)) == 2


def test_download_is_named_after_the_upload(client):
    # Uploads are stored with an index prefix that must not reach the user.
    response = post(client, "compress", one("report.pdf", pdf(1)))
    assert filename_of(response) == "report_compressed.pdf"


def test_garbage_is_reported_as_an_invalid_pdf(client):
    response = post(client, "compress", one("a.pdf", b"not a pdf"))
    assert_error(response, 400, "ERR_INVALID_PDF")


def scan(pages: int = 1) -> bytes:
    """Letter pages of the approved 300 dpi scan (tests/fixtures/legibility_8pt.jpg)."""
    from tests.test_compress import scan_pdf

    return scan_pdf(pages)


def test_compress_level_left_empty_is_recommended(client):
    # The UI sends "" for an option left untouched.
    source = scan()
    empty = post(client, "compress", one("a.pdf", source), level="")
    recommended = post(client, "compress", one("a.pdf", source), level="recommended")
    assert empty.status_code == recommended.status_code == 200
    assert len(empty.content) == len(recommended.content) <= 0.25 * len(source)


def test_compress_lossless_keeps_the_images(client):
    source = scan()
    response = post(client, "compress", one("a.pdf", source), level="lossless")
    assert response.status_code == 200
    image = PdfReader(io.BytesIO(response.content)).pages[0]["/Resources"]["/XObject"]["/Im"]
    assert image.get_object()["/Width"] == 2550


def test_compress_never_returns_a_larger_file(client):
    source = pdf(3)  # vector pages: nothing to recompress
    response = post(client, "compress", one("a.pdf", source))
    assert response.status_code == 200
    assert len(response.content) <= len(source)


def test_compress_level_must_be_known(client):
    assert_error(
        post(client, "compress", one("a.pdf", pdf(1)), level="low"), 400, "ERR_INVALID_INPUT"
    )


@pytest.mark.parametrize("case", ["no media box", "reversed box", "inherited tree", "cycle parent"])
def test_compress_odd_structures_never_give_5xx(client, case):
    from pypdf.generic import ArrayObject, FloatObject, NameObject

    from tests import test_compress as engine

    if case == "inherited tree":
        source = engine._tree("deep_root")
    elif case == "cycle parent":
        source = engine._tree("cycle_parent")
    else:
        box = ArrayObject([FloatObject(v) for v in (144, 144, 0, 0)])
        source = engine.one_page(engine.jpeg(), page_extra={"/MediaBox": box})
        if case == "no media box":
            writer = PdfWriter(clone_from=PdfReader(io.BytesIO(source)))
            del writer.pages[0][NameObject("/MediaBox")]
            out = io.BytesIO()
            writer.write(out)
            source = out.getvalue()
    assert post(client, "compress", one("a.pdf", source)).status_code == 200


# --- protect and unlock ---


def test_protect_uses_aes_256(client):
    response = post(client, "protect", one("a.pdf", pdf(1)), password="s3cret")
    reader = PdfReader(io.BytesIO(response.content))
    assert reader.is_encrypted
    encrypt = reader.trailer["/Encrypt"]
    assert (encrypt["/V"], encrypt["/R"]) == (5, 6)
    assert reader.decrypt("s3cret")


def owner_only(algorithm: str, permissions: UserAccessPermissions) -> bytes:
    """A PDF that opens without a password and restricts what can be done with it."""
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf(1))))
    writer.encrypt(
        user_password="", owner_password="owner", algorithm=algorithm, permissions_flag=permissions
    )
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


NO_PRINT_NO_COPY = (
    UserAccessPermissions.all()
    & ~UserAccessPermissions.PRINT
    & ~UserAccessPermissions.EXTRACT
    & ~UserAccessPermissions.EXTRACT_TEXT_AND_GRAPHICS
)


@pytest.mark.parametrize("algorithm", ["RC4-128", "AES-256"])
def test_protect_keeps_the_restrictions_of_an_owner_only_pdf(client, algorithm):
    source = owner_only(algorithm, NO_PRINT_NO_COPY)
    original = PdfReader(io.BytesIO(source))
    original.decrypt("")
    response = post(client, "protect", one("a.pdf", source), password="nueva")
    assert response.status_code == 200, response.text
    assert PdfReader(io.BytesIO(response.content)).decrypt("") == PasswordType.NOT_DECRYPTED
    reader = PdfReader(io.BytesIO(response.content))
    assert reader.decrypt("nueva") == PasswordType.USER_PASSWORD
    assert reader.user_access_permissions == original.user_access_permissions
    assert PdfReader(io.BytesIO(response.content)).decrypt("owner") == PasswordType.NOT_DECRYPTED
    # A second reader agrees on what is allowed.
    document = pdfium.PdfDocument(response.content, password="nueva")
    allowed = pdfium.raw.FPDF_GetDocPermissions(document) & 0xFFFFFFFF
    assert allowed == int(original.user_access_permissions) & 0xFFFFFFFF


def test_protect_an_owner_only_pdf_without_restrictions(client):
    response = post(
        client,
        "protect",
        one("a.pdf", owner_only("AES-256", UserAccessPermissions.all())),
        password="nueva",
    )
    assert PdfReader(io.BytesIO(response.content)).decrypt("nueva") == PasswordType.OWNER_PASSWORD


def test_protect_a_pdf_that_needs_a_password(client):
    response = post(client, "protect", one("a.pdf", encrypted(pdf(1))), password="nueva")
    assert_error(response, 400, "ERR_ENCRYPTED")


def test_unlock_round_trip(client):
    locked = post(client, "protect", one("a.pdf", pdf(2)), password="s3cret").content
    response = post(client, "unlock", one("a.pdf", locked), password="s3cret")
    reader = PdfReader(io.BytesIO(response.content))
    assert not reader.is_encrypted
    assert len(reader.pages) == 2


def test_unlock_with_a_wrong_password(client):
    locked = post(client, "protect", one("a.pdf", pdf(1)), password="s3cret").content
    response = post(client, "unlock", one("a.pdf", locked), password="nope")
    assert_error(response, 400, "ERR_WRONG_PASSWORD")


def test_unlock_a_pdf_that_is_not_encrypted(client):
    response = post(client, "unlock", one("a.pdf", pdf(1)), password="x")
    assert_error(response, 400, "ERR_NOT_ENCRYPTED")


def test_unlock_also_applies_the_page_limit(client, monkeypatch):
    from localpdf_hub import settings

    monkeypatch.setattr(settings, "MAX_PAGES", 2)
    response = post(client, "unlock", one("a.pdf", encrypted(pdf(3))), password="s3cret")
    assert_error(response, 413, "ERR_TOO_MANY_PAGES")


# --- PDFs with a password in the other tools ---


def encrypted(source: bytes, user: str = "s3cret") -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(source)))
    writer.encrypt(user_password=user, owner_password="owner", algorithm="AES-256")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# Every tool that is not about passwords, with the fields it needs.
PASSWORDLESS_TOOLS = [
    ("compress", "file", {}),
    ("split", "file", {"pages": "1"}),
    ("rotate", "file", {"rotations": "90"}),
    ("merge", "files", {}),
    ("watermark", "file", {"text": "X"}),
    ("extract-images", "file", {}),
    ("to-images", "file", {}),
    ("to-word", "file", {}),
]


@pytest.mark.parametrize(("tool", "field", "fields"), PASSWORDLESS_TOOLS)
def test_a_pdf_that_needs_a_password_is_refused_with_its_own_code(client, tool, field, fields):
    files = [(field, ("a.pdf", encrypted(pdf_with_image()), "application/pdf"))]
    assert_error(post(client, tool, files, **fields), 400, "ERR_ENCRYPTED")


def test_a_tool_that_reads_an_encrypted_pdf_still_gets_the_right_code():
    # The page check catches these first; this is the second line for a
    # route that would read a PDF without going through it.
    from pypdf.errors import FileNotDecryptedError

    async def read_encrypted() -> None:
        raise FileNotDecryptedError("File has not been decrypted")

    app = create_app()
    app.add_api_route("/read-encrypted", read_encrypted, methods=["GET"])
    # Ahead of the static mount at "/", which would answer 404.
    app.router.routes.insert(0, app.router.routes.pop())
    assert_error(TestClient(app, base_url=ORIGIN).get("/read-encrypted"), 400, "ERR_ENCRYPTED")


@pytest.mark.parametrize(("tool", "field", "fields"), PASSWORDLESS_TOOLS)
def test_a_pdf_with_only_an_owner_password_still_works(client, tool, field, fields):
    # It only restricts printing or copying and opens without a password, as in pdf.js.
    files = [(field, ("a.pdf", encrypted(pdf_with_image(), user=""), "application/pdf"))]
    assert post(client, tool, files, **fields).status_code == 200


# --- watermark ---


def test_watermark_keeps_the_page_count(client):
    response = post(client, "watermark", one("a.pdf", pdf(2)), text="DRAFT", opacity="0.3")
    assert len(pages_of(response)) == 2


@pytest.mark.parametrize(
    "fields",
    [
        {"text": "", "opacity": "0.3"},
        {"text": "X", "opacity": "1.5"},
        {"text": "x" * 101, "opacity": "0.3"},
        {"text": "\U0001f600", "opacity": "0.3"},
    ],
)
def test_watermark_rejects_bad_options(client, fields):
    response = post(client, "watermark", one("a.pdf", pdf(1)), **fields)
    assert_error(response, 400, "ERR_INVALID_INPUT")


def test_watermark_options_left_empty_mean_the_defaults(client):
    # The UI sends every option, "" when it is left empty.
    fields = {"position": "", "rotation": "", "size": "", "color": "", "pages": ""}
    response = post(client, "watermark", one("a.pdf", pdf(1)), text="DRAFT", **fields)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "fields",
    [
        {"size": "nan"},
        {"size": "7"},
        {"rotation": "30"},
        {"position": "middle"},
        {"color": "#12345"},
    ],
)
def test_watermark_rejects_options_outside_the_contract(client, fields):
    response = post(client, "watermark", one("a.pdf", pdf(1)), text="DRAFT", **fields)
    assert_error(response, 400, "ERR_INVALID_INPUT")


def test_watermark_that_does_not_fit_has_its_own_code(client):
    response = post(
        client,
        "watermark",
        one("a.pdf", pdf(1, size=612)),
        text="x" * 40,
        position="top-left",
        size="200",
    )
    assert_error(response, 400, "ERR_MARK_TOO_LARGE")


# --- page selections ---


def pdf_of_widths(widths: list[int]) -> bytes:
    writer = PdfWriter()
    for width in widths:
        writer.add_blank_page(width=width, height=100)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def format_ranges(pages: list[int]) -> str:
    """frontend/js/ranges.js formatRanges: the text the page picker puts in the field."""
    parts, i = [], 0
    while i < len(pages):
        j = i
        while j + 1 < len(pages) and pages[j + 1] == pages[j] + 1:
            j += 1
        parts.append(str(pages[i]) if i == j else f"{pages[i]}-{pages[j]}")
        i = j + 1
    return ", ".join(parts)


@pytest.mark.parametrize(
    "chosen",
    [[p for p in range(1, 2001) if p % 2], [p for p in range(1, 2001) if p % 3]],
    ids=["odd pages", "two of every three"],
)
def test_split_takes_the_longest_selections_the_picker_writes(client, chosen):
    response = post(client, "split", one("a.pdf", pdf(2000)), pages=format_ranges(chosen))
    assert response.status_code == 200, response.text
    assert len(pages_of(response)) == len(chosen)


def test_split_keeps_the_order_asked(client):
    response = post(client, "split", one("a.pdf", pdf_of_widths([101, 102, 103])), pages="3,1")
    assert [float(page.mediabox.width) for page in pages_of(response)] == [103, 101]


def test_split_stops_a_selection_longer_than_the_page_limit(client):
    response = post(client, "split", one("a.pdf", pdf(2000)), pages="1-2000,1-2000")
    assert_error(response, 413, "ERR_TOO_MANY_PAGES")


def test_watermark_counts_a_repeated_selection_once(client):
    response = post(client, "watermark", one("a.pdf", pdf(2000)), text="X", pages="1-2000,1-2000")
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(("tool", "fields"), [("split", {}), ("watermark", {"text": "X"})])
def test_a_megabyte_of_pages_is_answered(client, tool, fields):
    response = post(client, tool, one("a.pdf", pdf(1)), pages="1," * 500_000, **fields)
    assert response.status_code in (200, 413), response.text


@pytest.mark.parametrize(
    ("spec", "total"),
    [("1," * 500_000, 1), ("1-2000," * 140_000, 2000)],
    ids=["one page named 500000 times", "the whole document 140000 times"],
)
@pytest.mark.parametrize("parse", [pages.page_numbers, pages.page_set], ids=["split", "watermark"])
def test_a_megabyte_of_pages_costs_little(parse, spec, total):
    # The parser alone: the time of the whole request depends on the CI machine.
    started = time.monotonic()
    with contextlib.suppress(AppError):
        parse(spec, total)
    elapsed = time.monotonic() - started
    tracemalloc.start()
    with contextlib.suppress(AppError):
        parse(spec, total)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert elapsed < 1 and peak < 50 * 1024 * 1024, f"{elapsed:.2f} s, {peak / 1e6:.0f} MB"


# --- images ---


def test_extract_images_returns_a_zip_of_pngs(client):
    response = post(client, "extract-images", one("a.pdf", pdf_with_image()))
    assert response.status_code == 200
    assert filename_of(response).endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        assert zf.namelist()
        assert all(name.endswith(".png") for name in zf.namelist())


def test_extract_images_from_a_pdf_without_images(client):
    response = post(client, "extract-images", one("a.pdf", pdf(1)))
    assert_error(response, 400, "ERR_NO_IMAGES")


def test_to_images_returns_one_png_per_page(client):
    response = post(client, "to-images", one("a.pdf", pdf(3)))
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        assert len(zf.namelist()) == 3


def rendered(response) -> list[tuple[str, bytes]]:
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        return [(name, zf.read(name)) for name in zf.namelist()]


def side(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as image:
        return image.size


def a4_pdf() -> bytes:
    return pdf_of_size(595, 842)


def pdf_of_size(width: float, height: float) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=height)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_to_images_as_jpg(client):
    [(name, data)] = rendered(post(client, "to-images", one("a.pdf", a4_pdf()), format="jpg"))
    assert name.endswith(".jpg") and data[:2] == b"\xff\xd8"


def test_to_images_resolution_follows_dpi(client):
    sizes = {
        dpi: side(rendered(post(client, "to-images", one("a.pdf", a4_pdf()), dpi=dpi))[0][1])
        for dpi in ("72", "150", "300")
    }
    assert abs(sizes["300"][0] - 2 * sizes["150"][0]) <= 1
    assert abs(sizes["72"][0] - 0.48 * sizes["150"][0]) <= 1


def test_to_images_empty_options_mean_png_at_150_dpi(client):
    [(name, data)] = rendered(post(client, "to-images", one("a.pdf", a4_pdf()), format="", dpi=""))
    assert name.endswith(".png") and abs(side(data)[0] - 595 * 150 / 72) <= 1


@pytest.mark.parametrize("width", [40000, 55850.2], ids=["40000 pt", "55850.2 pt"])
def test_to_images_keeps_a_very_long_page_under_the_jpeg_limit(client, width):
    # Pillow cannot write a JPEG side over 65500 px, and pdfium rounds the bitmap size up.
    [(_, data)] = rendered(
        post(client, "to-images", one("a.pdf", pdf_of_size(width, 20)), format="jpg")
    )
    assert max(side(data)) <= 65500


def test_to_images_stops_at_the_result_limit(client, monkeypatch):
    noise = io.BytesIO()
    Image.effect_noise((800, 800), 100).convert("RGB").save(noise, "PDF", resolution=72)
    monkeypatch.setattr(settings, "MAX_RESULT_BYTES", 1024 * 1024)
    response = post(client, "to-images", one("a.pdf", noise.getvalue()), dpi="300")
    assert_error(response, 413, "ERR_RESULT_TOO_LARGE")


@pytest.mark.parametrize("fields", [{"dpi": "96"}, {"format": "gif"}, {"dpi": "150.0"}])
def test_to_images_rejects_options_outside_the_contract(client, fields):
    assert_error(
        post(client, "to-images", one("a.pdf", pdf(1)), **fields), 400, "ERR_INVALID_INPUT"
    )


def test_two_renders_never_call_pdfium_at_once(tmp_path, monkeypatch):
    # pdfium is not thread-safe, not even across documents, and two light jobs can run together.
    # A crash is a poor oracle: count the threads inside the pdfium section instead.
    inside, peak, guard = 0, 0, threading.Lock()
    real = images._capped_scale

    def counted(*args, **kwargs):
        nonlocal inside, peak
        with guard:
            inside += 1
            peak = max(peak, inside)
        time.sleep(0.02)
        with guard:
            inside -= 1
        return real(*args, **kwargs)

    monkeypatch.setattr(images, "_capped_scale", counted)
    source = tmp_path / "a.pdf"
    source.write_bytes(pdf(4, size=600))
    options = images.parse_render_options("png", "150")

    def render(index: int) -> int:
        folder = tmp_path / str(index)
        folder.mkdir()
        return images.render_pages(source, options, folder).stat().st_size

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(list(pool.map(render, range(4))))
    assert peak == 1


# --- Word ---


def test_to_word_returns_a_docx_named_docx(client):
    response = post(client, "to-word", one("report.pdf", pdf(1)))
    assert response.status_code == 200
    assert filename_of(response) == "report.docx"
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        assert "word/document.xml" in zf.namelist()


def test_from_word_without_a_converter(client, monkeypatch):
    monkeypatch.setattr(host, "find_document_converter", lambda: None)
    docx = ("files", ("a.docx", b"PK", "application/octet-stream"))
    response = client.post("/api/v1/pdf/from-word", files=[docx])
    assert_error(response, 503, "ERR_CONVERTER_MISSING")


# --- limits and the request guard ---


def test_page_limit_answers_413(client, monkeypatch):
    from localpdf_hub import settings

    monkeypatch.setattr(settings, "MAX_PAGES", 2)
    assert_error(post(client, "compress", one("a.pdf", pdf(3))), 413, "ERR_TOO_MANY_PAGES")


def test_requests_without_the_token_are_refused():
    bare = TestClient(create_app(), base_url=ORIGIN)
    response = bare.post("/api/v1/pdf/compress", files=one("a.pdf", pdf(1)))
    assert response.status_code == 403


def test_health_reports_the_version(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert re.fullmatch(r"\d+\.\d+\.\d+", body["version"])


def test_old_spanish_routes_are_gone(client):
    assert client.post("/procesar").status_code in (404, 405)


def test_every_response_carries_a_strict_content_security_policy(client):
    # Defence in depth for the launch token: injected markup could not run.
    for path in ("/", "/js/main.js", "/health"):
        policy = client.get(path).headers["content-security-policy"]
        assert "default-src 'self'" in policy
        assert "frame-ancestors 'none'" in policy
        assert "unsafe-inline" not in policy
        assert "unsafe-eval" not in policy


def test_index_has_no_inline_script():
    from localpdf_hub import settings

    html = (settings.FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html)


def test_static_files_are_revalidated(client):
    # Otherwise browsers keep old JavaScript after an update.
    response = client.get("/js/main.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


def test_scripts_are_served_as_javascript_whatever_the_registry_says(monkeypatch):
    # Some Windows registries map .js to text/plain; browsers then refuse ES modules.
    monkeypatch.setattr(mimetypes, "_db", None)
    mimetypes.init(files=[])
    mimetypes.add_type("text/plain", ".js")
    response = TestClient(create_app(), base_url=ORIGIN).get("/js/main.js")
    assert response.headers["content-type"].startswith("text/javascript")
