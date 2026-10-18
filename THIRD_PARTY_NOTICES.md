# Third-party notices

LocalPDF Hub is MIT licensed (see [LICENSE](LICENSE)). The downloads also
contain the software below, each under its own license. The full license
texts ship with every download as `THIRD_PARTY_LICENSES.txt`, written at
build time by [`scripts/notices.py`](scripts/notices.py) from the packages
actually bundled for that system.

## Bundled in the app

| Component | License | Used for |
|---|---|---|
| Python | PSF-2.0 | runtime |
| FastAPI, Pydantic, h11, AnyIO, python-docx, platformdirs, six, PyObjC (macOS) | MIT | server, Word files, folders, menu bar icon |
| fontTools | MIT | embedding a font subset for watermarks |
| Starlette, Uvicorn, Click, pypdf, pycparser, lxml | BSD-3-Clause | server, PDF editing, Word files |
| python-multipart | Apache-2.0 | file uploads |
| cryptography | Apache-2.0 or BSD-3-Clause | AES-256 for protected PDFs |
| cffi | MIT-0 | cryptography bindings |
| pypdfium2 and PDFium | Apache-2.0 or BSD-3-Clause, plus PDFium's third-party licenses | PDF to images, PDF to Word |
| Pillow | MIT-CMU, plus the licenses of the image libraries it bundles | images |
| pi-heif | BSD-3-Clause; bundles libheif and libde265 (LGPL-3.0) | HEIC photos |
| pystray | LGPL-3.0 | tray and menu bar icon |
| pywin32 (Windows) | PSF-2.0 | Microsoft Word conversion |
| PyInstaller bootloader | GPL-2.0 with the bootloader exception | starting the packaged app |
| pdf.js (`pdfjs-dist`) | Apache-2.0 | previews and thumbnails in the UI |
| Phosphor Icons (`@phosphor-icons/core`) | MIT | UI icons |
| IBM Plex Sans (`@fontsource/ibm-plex-sans`) | SIL Open Font License 1.1 | UI font |

## LGPL-3.0 components

pystray and libheif are used as separate libraries, unmodified. LocalPDF
Hub's complete source and build script are in this repository, so you can
rebuild the app with your own versions of them: change the pin in
`requirements-build.txt` and run `python build.py`.
