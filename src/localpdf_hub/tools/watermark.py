"""Stamp a text watermark: one mark in a 3 x 3 grid position, or a mosaic over the page."""

import hashlib
import io
import logging
import math
import re
import sys
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from fontTools import subset
from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
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
    RectangleObject,
    TextStringObject,
)

from localpdf_hub import errors
from localpdf_hub.errors import AppError
from localpdf_hub.limits import check_deadline
from localpdf_hub.tools import pages
from localpdf_hub.tools.pdf_files import clone, read_pdf, write_pdf

_MAX_CHARS = 100
_MIN_SIZE, _MAX_SIZE = 8.0, 200.0
_MARGIN = 0.05
_MAX_STAMPS = 100
# Column and row of each grid position, counted from the bottom left as the page is seen.
_GRID = {
    "top-left": (0, 2),
    "top": (1, 2),
    "top-right": (2, 2),
    "left": (0, 1),
    "center": (1, 1),
    "right": (2, 1),
    "bottom-left": (0, 0),
    "bottom": (1, 0),
    "bottom-right": (2, 0),
}
POSITIONS = (*_GRID, "mosaic")
ROTATIONS = (0, 45, 90, 180, 270)

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
class Layout:
    position: str = "center"
    rotation: int = 45
    size: float | None = None
    color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    pages: str = ""


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
    # Inked box of the whole text and its outlines as path operators, both in 1/1000 of the size.
    ink: tuple[float, float, float, float]
    outline: str


def parse_layout(position: str, rotation: str, size: str, color: str, page_spec: str) -> Layout:
    """Form fields as the UI sends them: an empty field means the default."""
    position = position or "center"
    if position not in POSITIONS:
        raise AppError(errors.INVALID_INPUT, f"Unknown position {position[:20]!r}.")
    rotation = rotation or "45"
    if rotation not in {str(angle) for angle in ROTATIONS}:
        raise AppError(errors.INVALID_INPUT, f"Rotation must be one of {ROTATIONS}.")
    points = None
    if size:
        try:
            points = float(size)
        except ValueError as error:
            raise AppError(errors.INVALID_INPUT, "The size is not a number.") from error
        # NaN fails every comparison, so the range check refuses it along with inf and -0.
        if not (math.isfinite(points) and _MIN_SIZE <= points <= _MAX_SIZE):
            message = f"The size must be {_MIN_SIZE:g}-{_MAX_SIZE:g} pt."
            raise AppError(errors.INVALID_INPUT, message)
    color = color or "#000000"
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise AppError(errors.INVALID_INPUT, "The colour must be #RRGGBB.")
    red, green, blue = (int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return Layout(position, int(rotation), points, (red, green, blue), page_spec)


def watermark(path: Path, text: str, opacity: float, layout: Layout, out_dir: Path) -> Path:
    text = " ".join(text.split())
    if not text:
        raise AppError(errors.INVALID_INPUT, "The watermark text is empty.")
    if len(text) > _MAX_CHARS:
        raise AppError(errors.INVALID_INPUT, f"The watermark text is longer than {_MAX_CHARS}.")
    if not 0.05 <= opacity <= 1:
        raise AppError(errors.INVALID_INPUT, "Opacity must be between 0.05 and 1.")
    _check_direction(text)
    font = _subset_font(text)

    writer = clone(read_pdf(path))
    chosen = pages.page_set(layout.pages, len(writer.pages)) if layout.pages else None
    resources = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/LpdfWM"): _add_font(writer, font)}),
            NameObject("/ExtGState"): DictionaryObject(
                {NameObject("/LpdfGS"): _opacity_state(writer, opacity)}
            ),
        }
    )
    if layout.position == "mosaic":
        # One form with the outlines for the whole document; each stamp only scales and places it.
        resources[NameObject("/XObject")] = DictionaryObject(
            {NameObject("/LpdfWMForm"): _outline_form(writer, font)}
        )
    for number, page in enumerate(writer.pages, start=1):
        check_deadline()
        if chosen is not None and number not in chosen:
            continue
        page.merge_page(_stamp(page, number, text, font, layout, resources))
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
    ink, outline = _ink_and_outline(font, text, cmap, widths, scale)
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
        ink=ink,
        outline=outline,
    )


class _PathPen(BasePen):  # type: ignore[misc]
    """Glyph outlines as PDF path operators."""

    def __init__(self, glyph_set: object) -> None:
        super().__init__(glyph_set)
        self.ops: list[str] = []

    def _moveTo(self, pt: tuple[float, float]) -> None:  # noqa: N802
        self.ops.append(f"{pt[0]:.1f} {pt[1]:.1f} m")

    def _lineTo(self, pt: tuple[float, float]) -> None:  # noqa: N802
        self.ops.append(f"{pt[0]:.1f} {pt[1]:.1f} l")

    def _curveToOne(  # noqa: N802
        self, pt1: tuple[float, float], pt2: tuple[float, float], pt3: tuple[float, float]
    ) -> None:
        self.ops.append(" ".join(f"{x:.1f} {y:.1f}" for x, y in (pt1, pt2, pt3)) + " c")

    def _qCurveToOne(self, pt1: tuple[float, float], pt2: tuple[float, float]) -> None:  # noqa: N802
        # A quadratic segment is the cubic with control points 2/3 of the way to the quadratic one.
        x0, y0 = self._getCurrentPoint()
        self._curveToOne(
            (x0 + 2 / 3 * (pt1[0] - x0), y0 + 2 / 3 * (pt1[1] - y0)),
            (pt2[0] + 2 / 3 * (pt1[0] - pt2[0]), pt2[1] + 2 / 3 * (pt1[1] - pt2[1])),
            pt2,
        )

    def _closePath(self) -> None:  # noqa: N802
        self.ops.append("h")


def _ink_and_outline(
    font: TTFont, text: str, cmap: dict[int, str], widths: dict[int, int], scale: float
) -> tuple[tuple[float, float, float, float], str]:
    """The inked box of the text and its outlines, laid out with the same advances as the Tj."""
    glyph_set = font.getGlyphSet()
    bounds = BoundsPen(glyph_set)
    path = _PathPen(glyph_set)
    x = 0.0
    for char in text:
        name = cmap[ord(char)]
        placement = (scale, 0, 0, scale, x, 0)
        glyph_set[name].draw(TransformPen(bounds, placement))
        glyph_set[name].draw(TransformPen(path, placement))
        x += widths[font.getGlyphID(name)]
    if bounds.bounds is None:
        raise AppError(errors.INVALID_INPUT, "The watermark text has nothing to draw.")
    return bounds.bounds, " ".join(path.ops)


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


def _outline_form(writer: PdfWriter, font: _Font) -> IndirectObject:
    x0, y0, x1, y1 = font.ink
    form = DecodedStreamObject()
    form.set_data(f"{font.outline} f".encode())
    form.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/BBox"): ArrayObject(
                FloatObject(round(value, 1)) for value in (x0 - 1, y0 - 1, x1 + 1, y1 + 1)
            ),
        }
    )
    return writer._add_object(form.flate_encode())


def _sorted_box(box: RectangleObject) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = (float(value) for value in box)
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def _visible_box(page: PageObject) -> tuple[tuple[float, float, float, float], int]:
    """The CropBox cut to the MediaBox, and the page rotation, as viewers apply them.

    A cut under 1 pt falls back to the MediaBox, and a /Rotate that is not a multiple of 90
    counts as 0, as pdfium does.
    """
    media, crop = _sorted_box(page.mediabox), _sorted_box(page.cropbox)
    box = (
        max(media[0], crop[0]),
        max(media[1], crop[1]),
        min(media[2], crop[2]),
        min(media[3], crop[3]),
    )
    if box[2] - box[0] < 1 or box[3] - box[1] < 1:
        box = media
    rotate = page.rotation % 360
    return box, rotate if rotate % 90 == 0 else 0


def _mosaic_centres(
    seen_w: float, seen_h: float, mark_w: float, mark_h: float, angle: float
) -> list[tuple[float, float]]:
    """Staggered lines of stamps along the text, from the centre of the page outwards.

    Both spacings grow until at most _MAX_STAMPS stamps touch the page, so the mosaic always
    covers the whole page instead of stopping after the first rows.
    """
    ux, uy, nx, ny = math.cos(angle), math.sin(angle), -math.sin(angle), math.cos(angle)
    reach = math.hypot(mark_w, mark_h) / 2
    along, across = mark_w + 2 * mark_h, 1.6 * mark_h
    diagonal = math.hypot(seen_w, seen_h)
    while True:
        span = diagonal / 2 + reach
        centres = []
        for line in range(-math.ceil(span / across), math.ceil(span / across) + 1):
            # A stamp longer than the page stays centred on its line instead of shifting off it.
            shift = along / 2 if line % 2 and along < diagonal else 0.0
            for step in range(-math.ceil(span / along) - 1, math.ceil(span / along) + 2):
                a, b = step * along + shift, line * across
                x, y = seen_w / 2 + a * ux + b * nx, seen_h / 2 + a * uy + b * ny
                if -reach <= x <= seen_w + reach and -reach <= y <= seen_h + reach:
                    centres.append((x, y))
        if len(centres) <= _MAX_STAMPS:
            return centres
        along, across = along * 1.1, across * 1.1


def _stamp(
    page: PageObject,
    number: int,
    text: str,
    font: _Font,
    layout: Layout,
    resources: DictionaryObject,
) -> PageObject:
    """A page with the page's own MediaBox and the mark on its visible box, to merge on top.

    Positions and the angle are worked out on the box as it is seen, then taken to user space
    through the page rotation: u = c + Rot(rotate)(d - c').
    """
    box, rotate = _visible_box(page)
    width, height = box[2] - box[0], box[3] - box[1]
    seen_w, seen_h = (height, width) if rotate in (90, 270) else (width, height)
    angle = math.radians(layout.rotation)
    ink_x0, ink_y0, ink_x1, ink_y1 = font.ink
    # Half the extent of the turned inked box per point of size.
    ink_w, ink_h = ink_x1 - ink_x0, ink_y1 - ink_y0
    half_w = (abs(ink_w * math.cos(angle)) + abs(ink_h * math.sin(angle))) / 2000
    half_h = (abs(ink_w * math.sin(angle)) + abs(ink_h * math.cos(angle))) / 2000
    auto = min(seen_w, seen_h) / max(4, len(text)) * 1.4

    if layout.position == "mosaic":
        size = layout.size or max(_MIN_SIZE, auto / 3)
        centres = _mosaic_centres(seen_w, seen_h, ink_w * size / 1000, ink_h * size / 1000, angle)
    else:
        margin = _MARGIN * min(seen_w, seen_h)
        fit = min((seen_w - 2 * margin) / (2 * half_w), (seen_h - 2 * margin) / (2 * half_h))
        if layout.size is None:
            size = min(auto, fit)
        elif layout.size > fit:
            raise AppError(
                errors.MARK_TOO_LARGE,
                f"The mark does not fit on page {number} at {layout.size:g} pt.",
            )
        else:
            size = layout.size
        column, row = _GRID[layout.position]
        reach_x, reach_y = half_w * size, half_h * size
        centres = [
            (
                (margin + reach_x, seen_w / 2, seen_w - margin - reach_x)[column],
                (margin + reach_y, seen_h / 2, seen_h - margin - reach_y)[row],
            )
        ]

    turn = math.radians(layout.rotation + rotate)
    cos, sin = math.cos(turn), math.sin(turn)
    k = size / 1000
    # The inked box's centre, in text space, is what lands on each centre.
    mid_x, mid_y = (ink_x0 + ink_x1) / 2 * k, (ink_y0 + ink_y1) / 2 * k
    page_turn = math.radians(rotate)
    marks = []
    for seen_x, seen_y in centres:
        dx, dy = seen_x - seen_w / 2, seen_y - seen_h / 2
        x = box[0] + width / 2 + dx * math.cos(page_turn) - dy * math.sin(page_turn)
        y = box[1] + height / 2 + dx * math.sin(page_turn) + dy * math.cos(page_turn)
        origin_x, origin_y = x - (mid_x * cos - mid_y * sin), y - (mid_x * sin + mid_y * cos)
        if layout.position == "mosaic":
            marks.append(
                f"q {k * cos:.6f} {k * sin:.6f} {-k * sin:.6f} {k * cos:.6f} "
                f"{origin_x:.2f} {origin_y:.2f} cm /LpdfWMForm Do Q"
            )
        else:
            glyph_ids = "".join(f"{font.glyphs[char]:04X}" for char in text)
            marks.append(
                f"BT /LpdfWM {size:.2f} Tf {cos:.5f} {sin:.5f} {-sin:.5f} {cos:.5f} "
                f"{origin_x:.2f} {origin_y:.2f} Tm <{glyph_ids}> Tj ET"
            )
    red, green, blue = layout.color
    content = DecodedStreamObject()
    content.set_data(
        f"q /LpdfGS gs {red:.4f} {green:.4f} {blue:.4f} rg {' '.join(marks)} Q".encode()
    )
    stamp = PageObject.create_blank_page(width=width, height=height)
    # merge_page clips the stamp to the stamp's MediaBox: it must be the page's own, wherever
    # its origin is, or a page whose box does not start at (0, 0) loses part of the mark.
    stamp[NameObject("/MediaBox")] = RectangleObject(_sorted_box(page.mediabox))
    stamp[NameObject("/Contents")] = content
    stamp[NameObject("/Resources")] = resources
    return stamp
