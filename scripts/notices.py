"""Writes the license texts of everything the packaged app contains.

Runs in the build environment, so it reads the packages actually installed
for that system (pywin32 on Windows, PyObjC on macOS) and their license
files, which also cover the libraries bundled inside wheels such as Pillow,
pypdfium2 and pi-heif.

    python scripts/notices.py <output file>
"""

import re
import sys
import sysconfig
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LICENSE_WORDS = ("license", "licence", "copying", "notice")
# Pinned in requirements-build.txt only to run the tests, not shipped.
NOT_SHIPPED = {"pytest", "httpx"}
# Frontend packages copied into frontend/libs by scripts/vendor.mjs.
NPM_SHIPPED = ["pdfjs-dist", "@fontsource/ibm-plex-sans", "@phosphor-icons/core"]
RULE = "=" * 78


def pinned_packages() -> list[str]:
    names = []
    for line in (ROOT / "requirements-build.txt").read_text(encoding="utf-8").splitlines():
        match = re.match(r"([A-Za-z0-9_.-]+)==", line)
        if match and match.group(1).lower() not in NOT_SHIPPED:
            names.append(match.group(1))
    return names


def python_section() -> str:
    candidates = [
        Path(sysconfig.get_paths()["stdlib"]) / "LICENSE.txt",
        Path(sys.base_prefix) / "LICENSE.txt",
    ]
    text = next((p.read_text(encoding="utf-8") for p in candidates if p.is_file()), "PSF-2.0")
    return section(f"Python {sys.version.split()[0]}", "PSF-2.0", [text])


def package_section(name: str) -> str | None:
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return None  # pinned for the other system
    classifiers = [
        c.split(" :: ")[-1]
        for c in dist.metadata.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    declared = (
        dist.metadata.get("License-Expression")
        or dist.metadata.get("License")
        or ", ".join(classifiers)
    )
    texts = [
        dist.locate_file(path).read_text(encoding="utf-8", errors="replace")
        for path in dist.files or []
        if ".dist-info/" in str(path).replace("\\", "/")
        and any(word in path.name.lower() for word in LICENSE_WORDS)
    ]
    if not texts:
        texts = [f"No license file ships in the wheel; its metadata declares: {declared}"]
    return section(f"{dist.metadata['Name']} {dist.version}", declared, texts)


def npm_section(name: str) -> str:
    folder = ROOT / "node_modules" / name
    manifest = (folder / "package.json").read_text(encoding="utf-8")
    version = re.search(r'"version":\s*"([^"]+)"', manifest).group(1)  # type: ignore[union-attr]
    declared = re.search(r'"license":\s*"([^"]+)"', manifest).group(1)  # type: ignore[union-attr]
    texts = [
        p.read_text(encoding="utf-8")
        for p in sorted(folder.iterdir())
        if any(word in p.name.lower() for word in LICENSE_WORDS)
    ]
    return section(f"{name} {version}", declared, texts)


def section(title: str, declared: str, texts: list[str]) -> str:
    header = f"{RULE}\n{title}\nLicense: {declared.strip() or 'see below'}\n{RULE}\n"
    return header + "\n\n".join(text.strip() for text in texts) + "\n"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    parts = [
        "LocalPDF Hub bundles the software below. Each part keeps its own license;\n"
        "LocalPDF Hub itself is MIT licensed (see LICENSE).\n",
        python_section(),
        *filter(None, (package_section(name) for name in pinned_packages())),
        *(npm_section(name) for name in NPM_SHIPPED),
    ]
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
