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
- Images count as one page each, and a job takes up to 200 images
  (`ERR_TOO_MANY_IMAGES`) of up to 50 megapixels each (`ERR_IMAGE_TOO_LARGE`).
  The images of one job may add up to 1.5 GB in the result
  (`ERR_RESULT_TOO_LARGE`); lossless photos take about 65 MB per 50 MP.
  Images are recognised by their content, not their name; JPEG, PNG, TIFF
  (first page) and HEIC/HEIF are accepted.
- Many large images can take longer than the 300 s job limit (about 0.045 s
  per megapixel on an Apple M4) and end in `ERR_TIMEOUT`.
- A PDF that needs a password to open is refused with `ERR_ENCRYPTED` by
  every tool except `protect` and `unlock`; unlock it first. A PDF with
  only an owner password (it restricts printing or copying) opens without
  one and works everywhere.

## Endpoints

| Path | Fields | Returns |
|---|---|---|
| `/api/v1/pdf/merge` | `files` (PDFs and images, in order), `rotations` (optional, one angle per file, e.g. `0,90,0`), and for the images `pagesize`, `orientation`, `margin` (as in `images-to-pdf`) | PDF |
| `/api/v1/pdf/images-to-pdf` | `files` (images only, in order), `rotations` (optional, clockwise, one angle per file), `pagesize` (`A4` default, `letter`, `fit`), `orientation` (`portrait` default, `landscape`; not used with `fit`), `margin` (`0` default, `20`, `40` points), `merge_after` (`true` default) | PDF named after the first image, or `images.zip` with one PDF per image |
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

## How images are placed

- `A4` (595 × 842 pt) and `letter` (612 × 792 pt): the whole image fits inside
  the margins, centred, and small images are enlarged to fit.
- `fit`: the page takes the image's proportions with its long side at
  11.69 in (A4); images under 842 px keep their size at 72 dpi. The margin
  is added around it.
- JPEG photos go in without re-encoding. Their EXIF orientation is applied
  when drawing, and their metadata (EXIF, GPS, XMP, comments) is removed
  without touching the pixels. A JPEG with arithmetic coding also goes in as
  it is, and some PDF readers cannot show it.
- PNG and TIFF go in lossless; transparent pixels show as white. HEIC/HEIF
  and CMYK JPEG are re-encoded as JPEG (quality 90) at full size.

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
| 413 | `ERR_TOO_LARGE`, `ERR_TOO_MANY_PAGES`, `ERR_TOO_MANY_IMAGES`, `ERR_IMAGE_TOO_LARGE`, `ERR_RESULT_TOO_LARGE` |
| 503 | `ERR_TIMEOUT`, `ERR_CONVERTER_MISSING` (Word to PDF needs Word or LibreOffice) |
| 500 | `ERR_INTERNAL` |
