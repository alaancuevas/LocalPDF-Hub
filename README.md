# LocalPDF Hub

PDF tools that run on your own computer: merge, split, compress, protect
and convert, without uploading your files anywhere.

[Español](README.es.md)

![Merging a report, an invoice and a photo, in the light theme](docs/screenshot-light.png)

![Choosing pages 2 to 4 to split a report, in the dark theme](docs/screenshot-dark.png)

## What it does

| Organize | Security | Convert |
|---|---|---|
| Merge PDFs and images (JPG, PNG, HEIC) | Protect with a password (AES-256) | Extract images |
| Split by pages or ranges | Unlock a PDF you have the password for | PDF to images |
| Rotate pages | Watermark | PDF to Word |
| Compress | | Word to PDF |

## Your files stay on your computer

- The app is a small server that only listens on `127.0.0.1`, and its page
  is the only one allowed to use it. Nothing is sent over the internet.
- Files are processed in a temporary folder in your user account and
  deleted as soon as you get the result.
- The interface works offline: no fonts, scripts or analytics from other
  sites.

## Download

Get the latest version from
[Releases](https://github.com/alaancuevas/LocalPDF-Hub/releases/latest).

| System | File | Status |
|---|---|---|
| macOS 12 or later, Apple Silicon | `LocalPDF-Hub-macos-arm64.dmg` | tested by hand and in CI |
| Windows 10 or 11, 64-bit | `LocalPDF-Hub.exe` | built and smoke-tested in CI |

Macs with an Intel processor are not supported.

### First launch

The app is not signed by Apple or Microsoft, so the system warns you the
first time.

- **macOS:** open the `.dmg` and drag LocalPDF Hub to Applications. When
  you open it, macOS says it could not verify the app: click **Done**, go
  to **System Settings > Privacy & Security**, click **Open Anyway** next
  to LocalPDF Hub and confirm.
- **Windows:** if SmartScreen says it protected your PC, click
  **More info > Run anyway**.

LocalPDF Hub opens in your browser and adds an icon to the menu bar
(macOS) or the system tray (Windows). Quit it from that icon.

### Word to PDF

Word to PDF uses Microsoft Word on Windows, or
[LibreOffice](https://www.libreoffice.org/) on either system. If neither is
installed, that one tool says so; the others work without them.

### Using it from another device

To use LocalPDF Hub from a phone or another computer on your network,
start it with the environment variable `LOCALPDF_LAN` set to this
computer's IP address, then open `http://<that IP>:8000`. The app then
accepts requests addressed to that IP as well, so turn it on only on a
network you trust.

## Build from source

You need Python 3.12 and Node.js 22.

```sh
npm ci && npm run build          # pdf.js, the font and the icon sprite
python -m pip install -r requirements-build.txt
python -m pytest -q
python build.py                  # dist/LocalPDF-Hub.exe or .app and .dmg
```

To run it without packaging: `PYTHONPATH=src python -m localpdf_hub`.
The HTTP API is described in [docs/api.md](docs/api.md) and the interface
in [docs/DESIGN.md](docs/DESIGN.md).

## Maintenance

LocalPDF Hub is maintained by one person in their spare time. Issues and
pull requests are welcome (see [CONTRIBUTING.md](CONTRIBUTING.md)), but
answers may take a while. To report a security problem, follow
[SECURITY.md](SECURITY.md) instead of opening an issue.

## License

[MIT](LICENSE). The bundled components and their licenses are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
