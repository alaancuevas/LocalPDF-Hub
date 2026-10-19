# Changelog

All notable changes to LocalPDF Hub. Versions follow
[Semantic Versioning](https://semver.org/).

## [4.1.0] - 2026-10-19

### Added
- The result is a card: a thumbnail of the first page, the page count, the
  size before and after, and "Continue with…" to open another tool with
  the result already loaded.
- A progress bar and a spinner while a tool runs.
- Short movement that follows the state: new files fade in, reordered
  rows slide, the sidebar selection slides, and the result card draws its
  check. All of it stops when the system asks for reduced motion.
- Image to PDF: page size (A4, US Letter, fit to image), orientation,
  margin, and one PDF for all images or a ZIP with one PDF each.
- TIFF images are accepted.

### Changed
- Merge is now three tools: Merge PDF (PDFs only), Image to PDF, and
  Merge / convert all (PDFs and images), which is where the app opens.
- Images keep their quality: JPEG photos go in without re-encoding and
  without their location and camera data, PNG and TIFF go in lossless,
  and transparent areas show as white instead of a hidden colour.
- Images in Merge / convert all are placed like in Image to PDF, on A4 by
  default.
- A job takes up to 200 images of up to 50 megapixels each, and each image
  counts as a page towards the 2000-page limit.
- The images of one job may add up to 1.5 GB in the result; past that the
  job stops with a clear error instead of running out of memory.

### Security
- Images are recognised by their content and only JPEG, PNG, TIFF and
  HEIC/HEIF are opened, so a PostScript file renamed to .png is refused
  instead of reaching Ghostscript.

## [4.0.1] - 2026-10-18

### Fixed
- Watermarks are written as real text with an embedded font subset
  instead of a full-page image: files stay small, scroll smoothly and the
  mark can be searched and selected.

### Changed
- The watermark text is limited to 100 characters; line breaks and
  repeated spaces become a single space. Right-to-left scripts and
  characters the system font lacks are refused with a clear error.

## [4.0.0] - 2026-10-18

The first open source release: a new interface, a Mac app and a server
rebuilt around a written contract.

### Added
- macOS app for Apple Silicon (`.dmg`), next to the Windows `.exe`.
- PDFs that need a password: the app asks for it, opens the file and
  offers to protect the result again with the same password.
- Thumbnails to pick pages when splitting and to rotate single pages.
- Merge rotates each file and reorders the list with the keyboard.
- License texts of every bundled component in each download.

### Changed
- New interface: a sidebar with the tools, IBM Plex Sans, and its own
  icons where no common icon fit.
- The server answers only to the app's own page and listens on
  `127.0.0.1`; other devices need `LOCALPDF_LAN` (see the README).
- Protected PDFs use AES-256 instead of 128-bit RC4.
- Released under the MIT license.

### Removed
- Saving results straight to a folder: results download through the
  browser, like any other file.

## [3.0.3] - 2026-10-17

Security patch for 3.x, from the closed-source releases.

### Fixed
- Requests from other sites are refused: the server asks for a token made
  at each launch and checks where requests come from.
- Upload size, page count and processing time are limited, so a large or
  malformed file cannot fill the disk or hang the app.
