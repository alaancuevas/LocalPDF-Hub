# PyInstaller spec, run through build.py. Windows gets one LocalPDF-Hub.exe;
# macOS (Apple Silicon only) gets LocalPDF-Hub.app, which build.py puts in a
# .dmg. SPECPATH, Analysis, PYZ, EXE, COLLECT and BUNDLE come from PyInstaller.
import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH)
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
MAC = sys.platform == "darwin"
# Windows, the tray and the favicon use the full-bleed icon.ico; the .app
# uses a 1024 PNG drawn on Apple's icon grid, with its margin and corners.
ICON = str(ROOT / "frontend" / ("icon-macos.png" if MAC else "icon.ico"))

# Modules loaded by name at runtime, which PyInstaller cannot see.
hiddenimports = [
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "pystray._darwin" if MAC else "pystray._win32",
    # platformdirs picks its module per system, and pypdf its AES provider.
    *collect_submodules("platformdirs"),
    *collect_submodules("pypdf._crypt_providers"),
]

a = Analysis(
    [str(ROOT / "src" / "localpdf_hub" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    # build.py writes the license texts before running this spec.
    datas=[
        (str(ROOT / "frontend"), "frontend"),
        (str(ROOT / "build" / "THIRD_PARTY_LICENSES.txt"), "."),
    ],
    hiddenimports=hiddenimports,
)
pyz = PYZ(a.pure)

if MAC:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="LocalPDF-Hub",
        console=False,
        upx=False,
        target_arch="arm64",
        icon=ICON,
    )
    coll = COLLECT(exe, a.binaries, a.datas, name="LocalPDF-Hub", upx=False)
    app = BUNDLE(
        coll,
        name="LocalPDF-Hub.app",
        icon=ICON,
        bundle_identifier="io.github.alaancuevas.localpdfhub",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "LocalPDF Hub",
            "CFBundleShortVersionString": VERSION,
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            # The app lives in the menu bar, like the tray icon on Windows:
            # the UI is the browser tab, so a Dock icon would do nothing.
            "LSUIElement": True,
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="LocalPDF-Hub",
        console=False,
        upx=False,
        icon=ICON,
    )
