# HTTP API

The UI talks to a server that runs on the same computer. Every endpoint
below is a `POST` with a `multipart/form-data` body and returns the
resulting file, or a JSON error.

## Request rules

- Send the launch token in the `X-LocalPDF-Token` header. The server puts
  it in `index.html` as `<meta name="localpdf-token">` and makes a new
  one on every launch.
- Requests from another site are refused (`Origin` and `Sec-Fetch-Site`
  are checked), so the API is only usable from the app's own page.
- One upload may be up to 500 MB, and one document up to 2000 pages. For
  `unlock` the pages are counted after the password opens the document.
- A PDF that needs a password to open is refused with `ERR_ENCRYPTED` by
  every tool except `protect` and `unlock`; unlock it first. A PDF with
  only an owner password (it restricts printing or copying) opens without
  one and works everywhere.

## Endpoints

| Path | Fields | Returns |
|---|---|---|
| `/api/v1/pdf/merge` | `files` (PDFs and images, in order), `rotations` (optional, one angle per file, e.g. `0,90,0`) | PDF |
| `/api/v1/pdf/split` | `file`, and either `from` + `to` (page range) or `pages` (e.g. `1,3,5`) | PDF |
| `/api/v1/pdf/rotate` | `file`, `rotations` (one angle per page, multiples of 90) | PDF |
| `/api/v1/pdf/compress` | `file` | PDF |
| `/api/v1/pdf/protect` | `file`, `password` | PDF encrypted with AES-256 |
| `/api/v1/pdf/unlock` | `file`, `password` | PDF |
| `/api/v1/pdf/watermark` | `file`, `text` (1 to 100 characters; line breaks and repeated spaces become one space; no right-to-left scripts), `opacity` (0.05 to 1, default 0.3) | PDF, with the mark as real text in an embedded subset of a system font |
| `/api/v1/pdf/extract-images` | `file` | ZIP of PNG files |
| `/api/v1/pdf/to-images` | `file` | ZIP with one PNG per page |
| `/api/v1/pdf/to-word` | `file` | DOCX |
| `/api/v1/pdf/from-word` | `files` (DOCX) | PDF, or a ZIP when there are several files |

`GET /health` answers `{"status": "ok", "version": "..."}` and needs no token.

## Errors

Errors are JSON with a stable code the UI translates, and a message in
English for logs:

```json
{"code": "ERR_WRONG_PASSWORD", "message": "The password is not correct."}
```

| Status | Codes |
|---|---|
| 400 | `ERR_INVALID_INPUT`, `ERR_INVALID_PDF`, `ERR_ENCRYPTED`, `ERR_WRONG_PASSWORD`, `ERR_NOT_ENCRYPTED`, `ERR_NO_PAGES`, `ERR_NO_IMAGES` |
| 403 | missing or wrong token, foreign origin (plain text, no JSON body) |
| 413 | `ERR_TOO_LARGE`, `ERR_TOO_MANY_PAGES` |
| 503 | `ERR_TIMEOUT`, `ERR_CONVERTER_MISSING` (Word to PDF needs Word or LibreOffice) |
| 500 | `ERR_INTERNAL` |
