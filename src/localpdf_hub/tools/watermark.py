"""Stamp a diagonal text watermark on every page."""

import hashlib
import io
import logging
import math
import sys
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont, TTLibError
from pypdf import PageObject, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    IndirectObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from localpdf_hub import errors
from localpdf_hub.errors import AppError
from localpdf_hub.limits import check_deadline
from localpdf_hub.tools.pdf_files import read_pdf, write_pdf

_ANGLE = 35
_MAX_CHARS = 100

_FONT_CANDIDATES = {
    "win32": ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"],
    "darwin": ["/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Geneva.ttf"],
    "linux": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}

# OS/2 fsType bits that forbid embedding a subset: restricted licence,
# no subsetting, bitmap embedding only.
_NO_EMBEDDING = 0x0002 | 0x0100 | 0x0200

# fontTools logs every table subsetting drops, and quirks of system fonts, at WARNING.
logging.getLogger("fontTools").setLevel(logging.ERROR)


@dataclass(frozen=True)
class _Font:
    data: bytes
    name: str
    glyphs: dict[str, int]
    widths: dict[int, int]
    cap_height: int
    ascent: int
    descent: int
    bbox: tuple[int, int, int, int]


def watermark(path: Path, text: str, opacity: float, out_dir: Path) -> Path:
    text = " ".join(text.split())
    if not text:
        raise AppError(errors.INVALID_INPUT, "The watermark text is empty.")
    if len(text) > _MAX_CHARS:
        raise AppError(errors.INVALID_INPUT, f"The watermark text is longer than {_MAX_CHARS}.")
    if not 0.05 <= opacity <= 1:
        raise AppError(errors.INVALID_INPUT, "Opacity must be between 0.05 and 1.")
    _check_direction(text)
    font = _subset_font(text)

    writer = PdfWriter(clone_from=read_pdf(path))
    resources = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/LpdfWM"): _add_font(writer, font)}),
            NameObject("/ExtGState"): DictionaryObject(
                {NameObject("/LpdfGS"): _opacity_state(writer, opacity)}
            ),
        }
    )
    for page in writer.pages:
        check_deadline()
        page.merge_page(_stamp(page, text, font, resources))
        page.compress_content_streams()
    writer.compress_identical_objects(remove_duplicates=False, remove_unreferenced=True)
    return write_pdf(writer, out_dir / f"{path.stem}_watermarked.pdf")


def _check_direction(text: str) -> None:
    # Right-to-left text needs bidi reordering and Arabic needs contextual
    # shaping; drawn glyph by glyph it would come out reversed and unjoined.
    for char in text:
        if unicodedata.bidirectional(char) in ("R", "AL"):
            raise AppError(
                errors.INVALID_INPUT, f"Right-to-left text such as {char!r} is not supported yet."
            )


def _subset_font(text: str) -> _Font:
    """The first system font with every character, cut down to those characters."""
    for candidate in _FONT_CANDIDATES.get(sys.platform, _FONT_CANDIDATES["linux"]):
        try:
            font = (
                TTFont(candidate, fontNumber=0) if candidate.endswith(".ttc") else TTFont(candidate)
            )
        except (OSError, TTLibError):
            continue
        if "glyf" not in font or font["OS/2"].fsType & _NO_EMBEDDING:
            continue
        cmap = font.getBestCmap()
        missing = next((char for char in text if ord(char) not in cmap), None)
        if missing is not None:
            raise AppError(errors.INVALID_INPUT, f"The system font has no glyph for {missing!r}.")
        return _cut(font, text, cmap)
    raise AppError(errors.INVALID_INPUT, "No system font can be embedded for the watermark.")


def _cut(font: TTFont, text: str, cmap: dict[int, str]) -> _Font:
    postscript_name = (font["name"].getDebugName(6) or "Font").replace(" ", "")
    options = subset.Options()
    # Original glyph ids survive, so CIDs equal glyph ids (CIDToGIDMap /Identity).
    options.retain_gids = True
    options.notdef_outline = True
    options.layout_features = []
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=text)
    subsetter.subset(font)
    buf = io.BytesIO()
    font.save(buf)

    scale = 1000 / font["head"].unitsPerEm
    glyphs = {char: font.getGlyphID(cmap[ord(char)]) for char in set(text)}
    widths = {
        gid: round(font["hmtx"][font.getGlyphName(gid)][0] * scale) for gid in glyphs.values()
    }
    head, os2 = font["head"], font["OS/2"]
    return _Font(
        data=buf.getvalue(),
        name=f"{_subset_tag(glyphs.values())}+{postscript_name}",
        glyphs=glyphs,
        widths=widths,
        cap_height=round(getattr(os2, "sCapHeight", 0) * scale or os2.sTypoAscender * scale),
        ascent=round(os2.sTypoAscender * scale),
        descent=round(os2.sTypoDescender * scale),
        bbox=(
            round(head.xMin * scale),
            round(head.yMin * scale),
            round(head.xMax * scale),
            round(head.yMax * scale),
        ),
    )


def _subset_tag(gids: Iterable[int]) -> str:
    """Six capitals derived from the glyph set, so two different subsets never share a name."""
    digest = hashlib.sha256(",".join(map(str, sorted(gids))).encode()).digest()
    return "".join(chr(ord("A") + byte % 26) for byte in digest[:6])


def _add_font(writer: PdfWriter, font: _Font) -> IndirectObject:
    """One Type0 font with the TrueType subset, shared by every page."""
    font_file = DecodedStreamObject()
    font_file.set_data(font.data)
    font_file[NameObject("/Length1")] = NumberObject(len(font.data))
    name = NameObject(f"/{font.name}")
    descriptor = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/FontDescriptor"),
            NameObject("/FontName"): name,
            NameObject("/Flags"): NumberObject(32),
            NameObject("/FontBBox"): ArrayObject(NumberObject(value) for value in font.bbox),
            NameObject("/ItalicAngle"): NumberObject(0),
            NameObject("/Ascent"): NumberObject(font.ascent),
            NameObject("/Descent"): NumberObject(font.descent),
            NameObject("/CapHeight"): NumberObject(font.cap_height),
            NameObject("/StemV"): NumberObject(80),
            NameObject("/FontFile2"): writer._add_object(font_file.flate_encode()),
        }
    )
    widths = ArrayObject()
    for gid in sorted(font.widths):
        widths += [NumberObject(gid), ArrayObject([NumberObject(font.widths[gid])])]
    descendant = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/CIDFontType2"),
            NameObject("/BaseFont"): name,
            NameObject("/CIDSystemInfo"): DictionaryObject(
                {
                    NameObject("/Registry"): TextStringObject("Adobe"),
                    NameObject("/Ordering"): TextStringObject("Identity"),
                    NameObject("/Supplement"): NumberObject(0),
                }
            ),
            NameObject("/FontDescriptor"): writer._add_object(descriptor),
            NameObject("/W"): widths,
            NameObject("/CIDToGIDMap"): NameObject("/Identity"),
        }
    )
    return writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type0"),
                NameObject("/BaseFont"): name,
                NameObject("/Encoding"): NameObject("/Identity-H"),
                NameObject("/DescendantFonts"): ArrayObject([writer._add_object(descendant)]),
                NameObject("/ToUnicode"): writer._add_object(_to_unicode(font).flate_encode()),
            }
        )
    )


def _to_unicode(font: _Font) -> DecodedStreamObject:
    pairs = "\n".join(
        f"<{gid:04X}> <{char.encode('utf-16-be').hex().upper()}>"
        for char, gid in sorted(font.glyphs.items(), key=lambda item: item[1])
    )
    cmap = DecodedStreamObject()
    cmap.set_data(
        (
            "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
            "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
            "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
            f"{len(font.glyphs)} beginbfchar\n{pairs}\nendbfchar\n"
            "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend"
        ).encode()
    )
    return cmap


def _opacity_state(writer: PdfWriter, opacity: float) -> IndirectObject:
    return writer._add_object(
        DictionaryObject(
            {NameObject("/Type"): NameObject("/ExtGState"), NameObject("/ca"): FloatObject(opacity)}
        )
    )


def _stamp(page: PageObject, text: str, font: _Font, resources: DictionaryObject) -> PageObject:
    """A page the size of `page` with the text centred and tilted, to merge on top."""
    box = page.mediabox
    width, height = float(box.width), float(box.height)
    size = min(width, height) / max(4, len(text)) * 1.4
    text_width = sum(font.widths[font.glyphs[char]] for char in text) / 1000 * size
    cos, sin = math.cos(math.radians(_ANGLE)), math.sin(math.radians(_ANGLE))
    centre_x, centre_y = float(box.left) + width / 2, float(box.bottom) + height / 2
    glyph_ids = "".join(f"{font.glyphs[char]:04X}" for char in text)

    content = DecodedStreamObject()
    content.set_data(
        (
            f"q /LpdfGS gs 0 0 0 rg BT /LpdfWM {size:.2f} Tf "
            f"{cos:.5f} {sin:.5f} {-sin:.5f} {cos:.5f} {centre_x:.2f} {centre_y:.2f} Tm "
            f"{-text_width / 2:.2f} {-font.cap_height * size / 2000:.2f} Td <{glyph_ids}> Tj ET Q"
        ).encode()
    )
    stamp = PageObject.create_blank_page(width=width, height=height)
    stamp[NameObject("/Contents")] = content
    stamp[NameObject("/Resources")] = resources
    return stamp
