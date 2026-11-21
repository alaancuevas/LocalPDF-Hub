"""Request guard behaviour that the HTTP test client cannot show."""

import asyncio
import io
import os
import re
import runpy
import threading
import time
import types

import pytest
from fastapi.testclient import TestClient

from localpdf_hub.app import create_app
from localpdf_hub.security import RequestGuard


def _refused_post(chunks: list[bytes], content_length: int) -> list[str]:
    events = []

    async def app(scope, receive, send):
        raise AssertionError("a refused request must not reach the app")

    async def receive():
        events.append("read")
        body = chunks.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(chunks)}

    async def send(message):
        events.append(message["type"])

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/pdf/compress",
        "headers": [
            (b"host", b"127.0.0.1:8000"),
            (b"content-length", str(content_length).encode()),
        ],
    }
    asyncio.run(RequestGuard(app, "token")(scope, receive, send))
    return events


def test_a_refused_upload_is_read_before_the_answer():
    # Windows resets a connection closed with unread data, and the client
    # then loses the 403 that tells the page to reload.
    events = _refused_post([b"a" * 10, b"b" * 10], 20)
    assert events[:3] == ["read", "read", "http.response.start"]


def test_an_upload_over_the_limit_is_refused_unread(monkeypatch):
    from localpdf_hub import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 10)
    events = _refused_post([b"a" * 20], 20)
    assert "read" not in events
    assert events[0] == "http.response.start"


def test_an_upload_with_the_token_over_the_limit_is_also_refused_unread(monkeypatch):
    # A valid token does not skip the size check: nothing past the limit is read.
    from localpdf_hub import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 10)
    read, sent = [], []

    async def app(scope, receive, send):
        raise AssertionError("an oversized request must not reach the app")

    async def receive():
        read.append(True)
        return {"type": "http.request", "body": b"a" * 20, "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/pdf/compress",
        "headers": [
            (b"host", b"127.0.0.1:8000"),
            (b"x-localpdf-token", b"token"),
            (b"content-length", b"20"),
        ],
    }
    asyncio.run(RequestGuard(app, "token")(scope, receive, send))
    assert read == []
    assert sent[0]["status"] == 413


# --- through the whole app ---

ORIGIN = "http://127.0.0.1:8000"


def _client(**kwargs) -> TestClient:
    return TestClient(create_app(), base_url=ORIGIN, **kwargs)


def test_the_guards_own_refusals_carry_the_security_headers():
    # SecurityHeaders wraps RequestGuard, so the guard's refusals are covered too.
    response = _client().post("/api/v1/pdf/compress", files={"file": ("a.pdf", b"x")})
    assert response.status_code == 403
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_the_policy_blocks_plugins():
    assert "object-src 'none'" in _client().get("/").headers["content-security-policy"]


def test_the_policy_fixes_the_base_url():
    # An injected <base> tag would otherwise send the page's relative requests elsewhere.
    assert "base-uri 'none'" in _client().get("/").headers["content-security-policy"]


def test_the_policy_keeps_forms_on_this_server():
    assert "form-action 'self'" in _client().get("/").headers["content-security-policy"]


def test_responses_are_not_sniffed():
    assert _client().get("/").headers["x-content-type-options"] == "nosniff"


def test_responses_send_no_referrer():
    assert _client().get("/").headers["referrer-policy"] == "no-referrer"


@pytest.mark.parametrize("foreign", ["https://evil.example", "http://localhost:3000"])
def test_another_origin_gets_no_cors_approval(foreign):
    # Approving it would let a foreign page read index.html, and with it the token.
    client = _client()
    preflight = client.options(
        "/api/v1/pdf/compress",
        headers={
            "Origin": foreign,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-localpdf-token",
        },
    )
    page = client.get("/", headers={"Origin": foreign})
    assert preflight.status_code == 403
    assert "access-control-allow-origin" not in preflight.headers
    assert "access-control-allow-origin" not in page.headers


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_the_api_map_is_not_published(path):
    assert _client().get(path).status_code == 404


def _trusted_client(**kwargs) -> TestClient:
    client = _client(**kwargs)
    page = client.get("/").text
    token = re.search(r'<meta name="localpdf-token" content="([^"]+)"', page).group(1)
    client.headers.update({"X-LocalPDF-Token": token, "Origin": ORIGIN})
    return client


def test_an_unreadable_pdf_gets_a_fixed_message(monkeypatch):
    # What pypdf says about the file stays out of the answer.
    from pypdf.errors import PdfReadError

    from localpdf_hub.tools import pages

    def fail(*_args):
        raise PdfReadError("xref at /Users/someone/private/report.pdf")

    monkeypatch.setattr(pages, "rotate", fail)
    files = {"file": ("a.pdf", b"x", "application/pdf")}
    response = _trusted_client().post("/api/v1/pdf/rotate", files=files, data={"rotations": "90"})
    assert response.json() == {"code": "ERR_INVALID_PDF", "message": "The PDF could not be read."}


def test_an_unexpected_error_is_answered_without_its_details(monkeypatch):
    from localpdf_hub.tools import pages

    def fail(*_args):
        raise RuntimeError("/Users/someone/private/report.pdf")

    monkeypatch.setattr(pages, "rotate", fail)
    client = _trusted_client(raise_server_exceptions=False)
    files = {"file": ("a.pdf", b"x", "application/pdf")}
    response = client.post("/api/v1/pdf/rotate", files=files, data={"rotations": "90"})
    assert response.status_code == 500
    body = response.json()
    assert body == {"code": "ERR_INTERNAL", "message": "Something went wrong on our side."}


def test_an_unexpected_error_carries_the_security_headers(monkeypatch):
    # Starlette builds this 500 in its outermost middleware; the headers must wrap even that.
    from localpdf_hub.tools import pages

    def fail(*_args):
        raise RuntimeError("boom")

    monkeypatch.setattr(pages, "rotate", fail)
    client = _trusted_client(raise_server_exceptions=False)
    files = {"file": ("a.pdf", b"x", "application/pdf")}
    response = client.post("/api/v1/pdf/rotate", files=files, data={"rotations": "90"})
    assert response.status_code == 500
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"


# --- job folders ---


def test_an_upload_name_keeps_only_its_last_part():
    from localpdf_hub.workspace import safe_name

    assert safe_name("../../etc/passwd.pdf") == "passwd.pdf"
    assert safe_name("C:\\Users\\me\\report.pdf") == "report.pdf"


def test_an_upload_name_loses_characters_some_systems_refuse():
    from localpdf_hub.workspace import safe_name

    assert safe_name('re:po*rt?"<>|.pdf') == "re_po_rt_____.pdf"


def test_each_job_gets_its_own_folder():
    from localpdf_hub import settings, workspace

    first, second = workspace.new_job_dir(), workspace.new_job_dir()
    assert first != second
    assert first.parent == second.parent == settings.TEMP_DIR


def _pdf() -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_a_job_folder_is_removed_after_the_answer():
    from localpdf_hub import settings

    files = {"file": ("a.pdf", _pdf(), "application/pdf")}
    response = _trusted_client().post("/api/v1/pdf/compress", files=files)
    assert response.status_code == 200
    assert list(settings.TEMP_DIR.iterdir()) == []


def test_a_job_folder_is_removed_when_the_tool_fails(monkeypatch):
    from localpdf_hub import settings, workspace

    made = []
    real = workspace.new_job_dir

    def recorded():
        made.append(real())
        return made[-1]

    monkeypatch.setattr(workspace, "new_job_dir", recorded)
    files = {"file": ("a.pdf", b"not a pdf", "application/pdf")}
    response = _trusted_client().post("/api/v1/pdf/compress", files=files)
    assert response.json()["code"] == "ERR_INVALID_PDF"
    assert len(made) == 1
    assert not made[0].exists()
    assert list(settings.TEMP_DIR.iterdir()) == []


def test_stale_job_folders_are_swept_and_recent_ones_kept():
    from localpdf_hub import settings, workspace

    settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    old, recent = settings.TEMP_DIR / "old", settings.TEMP_DIR / "recent"
    old.mkdir()
    recent.mkdir()
    past = time.time() - settings.STALE_AFTER_S - 60
    os.utime(old, (past, past))
    assert workspace.sweep_stale() == 1
    assert not old.exists()
    assert recent.exists()


@pytest.mark.parametrize("lan", [None, "", "  "], ids=["unset", "empty", "blank"])
def test_the_server_listens_only_on_this_computer_by_default(monkeypatch, lan):
    from localpdf_hub import desktop, settings

    if lan is None:
        monkeypatch.delenv("LOCALPDF_LAN", raising=False)
    else:
        monkeypatch.setenv("LOCALPDF_LAN", lan)
    # Settings as a fresh start would read them, without touching the loaded module.
    fresh = types.SimpleNamespace(**runpy.run_path(settings.__file__))
    monkeypatch.setattr(desktop, "settings", fresh)
    binds = []
    monkeypatch.setattr(desktop.uvicorn, "run", lambda *_args, **kwargs: binds.append(kwargs))
    monkeypatch.setattr(desktop.webbrowser, "open", lambda _url: None)
    monkeypatch.setattr(desktop, "_setup_logging", lambda: None)
    monkeypatch.setattr(desktop, "_run_tray", lambda: None)
    desktop.main()
    assert binds[0]["host"] == "127.0.0.1"


# --- limits ---


def test_a_job_past_its_deadline_is_stopped(monkeypatch):
    # Through the API: the job opens its deadline and the tool checks it on every page.
    from localpdf_hub import settings

    monkeypatch.setattr(settings, "JOB_TIMEOUT_S", 0)
    files = {"file": ("a.pdf", _pdf(), "application/pdf")}
    response = _trusted_client().post("/api/v1/pdf/split", files=files, data={"pages": "1"})
    assert response.status_code == 503
    assert response.json()["code"] == "ERR_TIMEOUT"


def test_the_job_gate_holds_a_job_that_does_not_fit():
    from localpdf_hub.limits import JobGate

    gate = JobGate(2)
    light, heavy = threading.Event(), threading.Event()

    def job(weight, entered):
        with gate.slot(weight):
            entered.set()

    with gate.slot(1):
        threading.Thread(target=job, args=(1, light), daemon=True).start()
        threading.Thread(target=job, args=(2, heavy), daemon=True).start()
        assert light.wait(5)
        assert not heavy.wait(0.5)
    assert heavy.wait(5)


# --- request guard checks ---


@pytest.mark.parametrize(
    "host", ["evil.example", "evil.localhost", "127.0.0.1.evil.example", "localhost.evil.example"]
)
def test_a_foreign_host_name_is_refused(host):
    # DNS rebinding: a hostile domain resolved to 127.0.0.1 must not get index.html and its token.
    response = TestClient(create_app(), base_url=f"http://{host}:8000").get("/")
    assert response.status_code == 400
    assert "localpdf-token" not in response.text


@pytest.mark.parametrize(
    "origin",
    ["https://evil.example", "null", "http://127.0.0.1:9999", "http://127.0.0.1.evil.example"],
)
def test_another_origin_is_refused_even_with_the_token(origin):
    client = _trusted_client()
    files = {"file": ("a.pdf", _pdf(), "application/pdf")}
    allowed = client.post("/api/v1/pdf/compress", files=files)
    refused = client.post("/api/v1/pdf/compress", files=files, headers={"Origin": origin})
    assert allowed.status_code == 200
    assert refused.status_code == 403
