"""HTTP contract of the v4 API (docs/api.md).

These tests are written against the contract, not the code: when the
implementation is reorganised they must keep passing unchanged.
"""

import io
import mimetypes
import re
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader, PdfWriter

from localpdf_hub import platform as host
from localpdf_hub.app import create_app

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


# --- protect and unlock ---


def test_protect_uses_aes_256(client):
    response = post(client, "protect", one("a.pdf", pdf(1)), password="s3cret")
    reader = PdfReader(io.BytesIO(response.content))
    assert reader.is_encrypted
    encrypt = reader.trailer["/Encrypt"]
    assert (encrypt["/V"], encrypt["/R"]) == (5, 6)
    assert reader.decrypt("s3cret")


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


# --- watermark ---


def test_watermark_keeps_the_page_count(client):
    response = post(client, "watermark", one("a.pdf", pdf(2)), text="DRAFT", opacity="0.3")
    assert len(pages_of(response)) == 2


@pytest.mark.parametrize(
    "fields", [{"text": "", "opacity": "0.3"}, {"text": "X", "opacity": "1.5"}]
)
def test_watermark_rejects_bad_options(client, fields):
    response = post(client, "watermark", one("a.pdf", pdf(1)), **fields)
    assert_error(response, 400, "ERR_INVALID_INPUT")


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
