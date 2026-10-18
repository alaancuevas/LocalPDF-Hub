"""Smoke test for a running LocalPDF Hub build.

Starts the given command (the packaged executable in CI), waits for
/health, then checks the request guard, the type the UI scripts are served
with, and one real merge. Only the standard library is used, so it runs
next to a frozen build too.

    python scripts/smoke_test.py dist/LocalPDF-Hub.exe
    python scripts/smoke_test.py python -m localpdf_hub   (with src/ on PYTHONPATH)
"""

import io
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000"
STARTUP_TIMEOUT_S = 60


def _blank_pdf() -> bytes:
    body = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    )
    offsets, out = [], io.BytesIO()
    out.write(body[: body.index(b"1 0 obj")])
    for chunk in body[body.index(b"1 0 obj") :].split(b"\n")[:-1]:
        offsets.append(out.tell())
        out.write(chunk + b"\n")
    xref = out.tell()
    out.write(b"xref\n0 4\n0000000000 65535 f \n")
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer<</Size 4/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def _multipart(field: str, files: list[bytes]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    out = io.BytesIO()
    for i, data in enumerate(files):
        out.write(f"--{boundary}\r\n".encode())
        out.write(
            f'Content-Disposition: form-data; name="{field}"; filename="f{i}.pdf"\r\n'.encode()
        )
        out.write(b"Content-Type: application/pdf\r\n\r\n" + data + b"\r\n")
    out.write(f"--{boundary}--\r\n".encode())
    return out.getvalue(), f"multipart/form-data; boundary={boundary}"


def _post(path: str, headers: dict, field: str, files: list[bytes]) -> tuple[int, bytes]:
    body, content_type = _multipart(field, files)
    request = urllib.request.Request(
        BASE + path, data=body, method="POST", headers={"Content-Type": content_type, **headers}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def _wait_for_health() -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/health", timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(1)
    raise SystemExit(f"FAIL: /health did not answer within {STARTUP_TIMEOUT_S} s")


def run_checks() -> list[str]:
    failures = []
    pdf = _blank_pdf()

    with urllib.request.urlopen(BASE + "/", timeout=10) as response:
        page = response.read().decode()
    match = re.search(r'<meta name="localpdf-token" content="([^"]+)"', page)
    if not match:
        return ["index.html carries no launch token"]
    token = match.group(1)

    checks = [
        ("no token", {"Origin": BASE}, 403),
        ("foreign origin", {"X-LocalPDF-Token": token, "Origin": "https://evil.example"}, 403),
        ("cross-site fetch", {"X-LocalPDF-Token": token, "Sec-Fetch-Site": "cross-site"}, 403),
    ]
    for name, headers, expected in checks:
        status, _ = _post("/api/v1/pdf/compress", headers, "file", [pdf])
        if status != expected:
            failures.append(f"{name}: expected {expected}, got {status}")

    # Browsers refuse ES modules served as anything but JavaScript, and on
    # Windows the registry decides what Python's mimetypes answers.
    for path in ("/js/main.js", "/libs/pdf.min.mjs"):
        with urllib.request.urlopen(BASE + path, timeout=10) as response:
            content_type = response.headers.get("Content-Type", "")
        if not content_type.startswith("text/javascript"):
            failures.append(f"{path}: served as {content_type!r}")

    status, body = _post(
        "/api/v1/pdf/merge", {"X-LocalPDF-Token": token, "Origin": BASE}, "files", [pdf, pdf]
    )
    if status != 200 or not body.startswith(b"%PDF"):
        failures.append(f"merge with token: expected a PDF, got {status}")
    return failures


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    process = subprocess.Popen(sys.argv[1:])
    try:
        _wait_for_health()
        failures = run_checks()
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    if failures:
        raise SystemExit("FAIL:\n  " + "\n  ".join(failures))
    print("PASS: health, request guard, script types and merge")


if __name__ == "__main__":
    main()
