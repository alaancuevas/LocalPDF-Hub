"""Compress: lossless, or JPEG scans brought down to a target dpi (recommended, extreme).

Only JPEG images listed in a page's own /XObject are recompressed; everything else (images
inside forms, Flate, CCITT, JBIG2, CMYK, masks, inline images...) stays byte for byte. The PDF
comes from a third party, so every structure walked has a linear bound (CONOCIMIENTO.md,
"Comprimir"), any data error falls back to the lossless result, and no existing dictionary is
modified: copies are made and the pages point to them.
"""

import gc
import io
import logging
import math
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image
from pypdf import PdfWriter
from pypdf.errors import PyPdfError
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    IndirectObject,
    NameObject,
    NumberObject,
)

from localpdf_hub import errors, settings
from localpdf_hub.errors import AppError
from localpdf_hub.limits import check_deadline
from localpdf_hub.tools.pdf_files import read_pdf, write_pdf

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Level:
    name: str
    dpi: int
    quality: int


# Scans brought down to 150 dpi by default, and a stronger level that can blur small print.
_LEVELS = {"recommended": Level("recommended", 150, 60), "extreme": Level("extreme", 100, 40)}
_LOSSLESS = "lossless"
# Keys a recompressed image keeps or may drop safely; anything else (masks, /Decode, /OC,
# structure...) means the image is not understood and stays as it is.
_ALLOWED = frozenset(
    {
        "/Type",
        "/Subtype",
        "/Width",
        "/Height",
        "/BitsPerComponent",
        "/ColorSpace",
        "/Filter",
        "/Length",
        "/Name",
        "/Intent",
        "/Interpolate",
    }
)
_KEPT = ("/Type", "/Subtype", "/ColorSpace", "/Intent", "/Interpolate", "/Name")
_MIN_GAIN = 0.1
_TICK_EVERY = 10_000
_SOS = bytes((0xFF, 0xDA))
_WALK_ERRORS: tuple[type[BaseException], ...] = (
    PyPdfError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ArithmeticError,
    RecursionError,
)
_FALLBACK_ERRORS: tuple[type[BaseException], ...] = (*_WALK_ERRORS, IndexError)

Key = tuple[str, int]


def parse_level(text: str) -> Level | None:
    """The form field as the UI sends it: empty means recommended; None means lossless."""
    text = text or "recommended"
    if text == _LOSSLESS:
        return None
    if text not in _LEVELS:
        raise AppError(errors.INVALID_INPUT, f"The level must be one of {(*_LEVELS, _LOSSLESS)}.")
    return _LEVELS[text]


def compress(path: Path, level: Level | None, out_dir: Path) -> Path:
    out = out_dir / f"{path.stem}_compressed.pdf"
    if level is None:
        _finish(PdfWriter(clone_from=read_pdf(path)), out, copies=False)
    else:
        failure = ""
        try:
            replaced, reason, pixels = _lossy(path, level, out)
            logger.info(
                "compress %s: %d images, %.1f GP decoded %s",
                level.name,
                replaced,
                pixels / 1e9,
                reason,
            )
        except _FALLBACK_ERRORS as error:
            failure = type(error).__name__
        if failure:
            # Outside the except block, so the traceback no longer holds the failed writer; pypdf
            # objects point back to their writer (cycles), so only the cycle collector frees it
            # before the input is cloned again.
            gc.collect()
            logger.info("compress %s: lossless, %s while rewriting", level.name, failure)
            _finish(PdfWriter(clone_from=read_pdf(path)), out, copies=False)
    if out.stat().st_size >= path.stat().st_size:
        shutil.copyfile(path, out)
    return out


def _resolve(value: Any) -> Any:
    return value.get_object() if isinstance(value, IndirectObject) else value


def _key(raw: Any, resolved: Any) -> Key:
    """The idnum of an indirect object; the identity of a direct one (kept alive by its owner)."""
    return ("ref", raw.idnum) if isinstance(raw, IndirectObject) else ("id", id(resolved))


def _page_sides(page: Any) -> tuple[float, float] | None:
    """(long, short) side in inches, or None when the page geometry is not usable."""
    box = _resolve(page.get("/MediaBox"))
    if not isinstance(box, ArrayObject) or len(box) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(_resolve(value)) for value in box)
        unit = float(_resolve(page.get("/UserUnit", 1)))
    except (TypeError, ValueError, OverflowError):
        return None
    width, height = abs(x1 - x0), abs(y1 - y0)
    if not all(math.isfinite(v) for v in (width, height, unit)):
        return None
    if width < 1 or height < 1 or unit <= 0:
        return None
    unit = max(1.0, unit)  # a viewer that ignores /UserUnit shows the page larger, never smaller
    return max(width, height) * unit / 72, min(width, height) * unit / 72


def _channels(obj: Any) -> int | None:
    space = _resolve(obj.get("/ColorSpace"))
    if space == "/DeviceRGB":
        return 3
    if space == "/DeviceGray":
        return 1
    if isinstance(space, list) and len(space) == 2 and space[0] == "/ICCBased":
        profile = _resolve(space[1])
        count = profile.get("/N") if isinstance(profile, DictionaryObject) else None
        return int(count) if count in (1, 3) else None
    return None


def _eligible(obj: Any) -> bool:
    try:
        width, height = int(obj["/Width"]), int(obj["/Height"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    return (
        not set(obj.keys()) - _ALLOWED
        and obj.get("/Filter") == "/DCTDecode"
        and obj.get("/BitsPerComponent") == 8
        and _channels(obj) is not None
        and 0 < width * height <= settings.MAX_RENDER_PIXELS
    )


class _IncompleteError(Exception):
    pass


class _Walk:
    """Images in the pages' own /XObject dicts, each structure read once (bounded by MAX_WORK)."""

    def __init__(self, tick: Callable[[], None]) -> None:
        self.tick = tick
        self.work = 0
        self.dicts: dict[Key, DictionaryObject] = {}
        self.sides: dict[Key, list[float]] = {}
        self.pages_of: dict[Key, list[int]] = {}
        self.bad: set[Key] = set()
        self.resources_seen: dict[Key, DictionaryObject] = {}
        self.poisoned: set[int] = set()
        self.verdicts: dict[int, bool] = {}
        self.forms_seen: set[int] = set()

    def spend(self, units: int = 1) -> None:
        before = self.work
        self.work += units
        if self.work > settings.COMPRESS_MAX_WORK:
            raise _IncompleteError("work cap")
        if self.work // _TICK_EVERY != before // _TICK_EVERY:
            self.tick()

    def page(self, number: int, page: Any) -> None:
        self.tick()
        self.spend()
        raw_resources = page.raw_get("/Resources") if "/Resources" in page else None
        resources = _resolve(raw_resources)
        if not isinstance(resources, DictionaryObject):
            return
        resources_key = _key(raw_resources, resources)
        if resources_key not in self.resources_seen:  # copying it once costs its size
            self.resources_seen[resources_key] = resources
            self.spend(len(resources))
        raw = resources.raw_get("/XObject") if "/XObject" in resources else None
        xobjects = _resolve(raw)
        if not isinstance(xobjects, DictionaryObject):
            return
        key = _key(raw, xobjects)
        self.dicts[key] = xobjects
        self.pages_of.setdefault(key, []).append(number)
        sides = _page_sides(page)
        if sides is None:
            self.bad.add(key)
            return
        best = self.sides.setdefault(key, [0.0, 0.0])
        best[0], best[1] = max(best[0], sides[0]), max(best[1], sides[1])

    def candidates(self) -> tuple[dict[int, float], dict[int, set[tuple[Key, str]]]]:
        """Lowest page-bound dpi and the (dict, name) entries of each image to recompress."""
        lowest: dict[int, float] = {}
        uses: dict[int, set[tuple[Key, str]]] = {}
        for key, xobjects in self.dicts.items():
            self.tick()
            for name, ref in list(xobjects.items()):
                self.spend()
                if not isinstance(ref, IndirectObject):
                    continue
                obj: Any = ref.get_object()
                subtype = obj.get("/Subtype") if isinstance(obj, DictionaryObject) else None
                if subtype == "/Form":
                    self._poison_form(ref.idnum, obj)
                    continue
                if subtype != "/Image" or ref.idnum in self.poisoned:
                    continue
                usable = key not in self.bad and key in self.sides
                if not usable or not self._eligible_once(ref.idnum, obj):
                    self.poisoned.add(ref.idnum)
                    continue
                long_in, short_in = self.sides[key]
                width, height = int(obj["/Width"]), int(obj["/Height"])
                # min over pages of min(long/long, short/short) splits by axis, so the largest
                # sides give the lowest dpi.
                dpi = min(max(width, height) / long_in, min(width, height) / short_in)
                lowest[ref.idnum] = min(lowest.get(ref.idnum, dpi), dpi)
                uses.setdefault(ref.idnum, set()).add((key, name))
        for idnum in self.poisoned:
            lowest.pop(idnum, None)
        return lowest, uses

    def _eligible_once(self, idnum: int, obj: Any) -> bool:
        if idnum not in self.verdicts:
            self.spend(len(obj))
            self.verdicts[idnum] = _eligible(obj)
        return self.verdicts[idnum]

    def _poison_form(self, idnum: int, form: Any) -> None:
        """Images a form draws keep their bytes: their size is unknown without parsing content."""
        stack: list[tuple[int, Any]] = [(idnum, form)]
        while stack:
            form_id, current = stack.pop()
            if form_id in self.forms_seen:
                continue
            self.forms_seen.add(form_id)
            resources = _resolve(current.get("/Resources"))
            inner = None
            if isinstance(resources, DictionaryObject):
                inner = _resolve(resources.get("/XObject"))
            if not isinstance(inner, DictionaryObject):
                continue
            for ref in inner.values():
                self.spend()
                if not isinstance(ref, IndirectObject):
                    continue
                obj = ref.get_object()
                subtype = obj.get("/Subtype") if isinstance(obj, DictionaryObject) else None
                if subtype == "/Image":
                    self.poisoned.add(ref.idnum)
                elif subtype == "/Form" and ref.idnum not in self.forms_seen:
                    stack.append((ref.idnum, obj))


def _draft_pixels(width: int, height: int, size: tuple[int, int]) -> int:
    """Pixels Image.draft decodes for this target: the largest 1/2^k (k <= 3) that stays >= size."""
    scale = 1
    while scale < 8 and width // (scale * 2) >= size[0] and height // (scale * 2) >= size[1]:
        scale *= 2
    return math.ceil(width / scale) * math.ceil(height / scale)


def _recompress(obj: Any, size: tuple[int, int], quality: int) -> DecodedStreamObject | None:
    width, height = int(obj["/Width"]), int(obj["/Height"])
    mode = "L" if _channels(obj) == 1 else "RGB"
    data = obj.get_data()
    # Decode time grows with the scans of a progressive JPEG, not with its pixels: FF DA counts
    # every scan (and can only overcount, e.g. inside a thumbnail, which leaves it as it is).
    if data.count(_SOS) > settings.COMPRESS_MAX_SCANS:
        return None
    with Image.open(io.BytesIO(data), formats=("JPEG",)) as image:
        modes = ("L",) if mode == "L" else ("RGB", "YCbCr")
        if image.mode not in modes or image.size != (width, height):
            return None
        image.draft(mode, size)
        small = image.convert(mode)
    if small.size != size:
        small = small.resize(size, Image.Resampling.LANCZOS)
    jpeg = io.BytesIO()
    small.save(jpeg, "JPEG", quality=quality, subsampling=2)
    if jpeg.tell() > (1 - _MIN_GAIN) * len(data):
        return None
    stream = DecodedStreamObject()  # a new object: replace() would rebuild the dict and drop keys
    stream.set_data(jpeg.getvalue())
    for key in _KEPT:
        if key in obj:
            stream[NameObject(key)] = obj.raw_get(key)
    stream.update(
        {
            NameObject("/Width"): NumberObject(size[0]),
            NameObject("/Height"): NumberObject(size[1]),
            NameObject("/BitsPerComponent"): NumberObject(8),
            NameObject("/Filter"): NameObject("/DCTDecode"),
        }
    )
    return stream


def _lossy(path: Path, level: Level, out: Path) -> tuple[int, str, int]:
    """Writes the recompressed PDF to out: (images replaced, reason, decoded pixels charged)."""
    started = time.monotonic()
    writer = PdfWriter(clone_from=read_pdf(path))
    replaced, reason, spent = 0, "", 0
    copies: dict[Key, DictionaryObject] = {}
    walk = _Walk(check_deadline)
    lowest: dict[int, float] = {}
    uses: dict[int, set[tuple[Key, str]]] = {}
    try:
        for number, page in enumerate(writer.pages):
            walk.page(number, page)
        lowest, uses = walk.candidates()
    except _IncompleteError as error:
        lowest, reason = {}, f"lossless: {error}"
    except _WALK_ERRORS as error:
        lowest, reason = {}, f"lossless: {type(error).__name__} while walking"
    for idnum in sorted(lowest):
        check_deadline()
        if spent >= settings.COMPRESS_PIXEL_BUDGET:
            reason = "stopped: pixel budget"
            break
        if time.monotonic() - started >= settings.COMPRESS_SOFT_SECONDS:
            reason = "stopped: time"
            break
        found = writer.get_object(idnum)
        if not isinstance(found, DictionaryObject):
            continue
        obj: Any = found  # pypdf types values as PdfObject; the keys were checked by _eligible
        width, height = int(obj["/Width"]), int(obj["/Height"])
        scale = min(1.0, level.dpi / lowest[idnum])
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        spent += _draft_pixels(width, height, size)  # before decoding: a broken JPEG costs too
        try:
            new = _recompress(obj, size, level.quality)
        except (Image.DecompressionBombError, PyPdfError, OSError, ValueError):
            continue
        if new is None:
            continue
        ref = writer._add_object(new)
        for key, name in uses[idnum]:
            if key not in copies:
                copies[key] = DictionaryObject(walk.dicts[key])
            copies[key][NameObject(name)] = ref
        replaced += 1
    if copies:
        _rewrite_resources(writer, walk, copies)
    _finish(writer, out, copies=bool(copies))
    return replaced, reason, spent


def _rewrite_resources(writer: PdfWriter, walk: _Walk, copies: dict[Key, DictionaryObject]) -> None:
    """Copy on write: one copy per /XObject dict and per distinct /Resources.

    The pages, and then the /Pages nodes above them, point to the copies.
    """
    resource_copies: dict[Key, IndirectObject] = {}
    copy_refs: dict[Key, IndirectObject] = {}
    kept: list[object] = []  # direct objects keyed by identity stay alive while the maps are in use
    for key, copy in copies.items():
        copy_ref = copy_refs[key] = writer._add_object(copy)
        for number in walk.pages_of[key]:
            page = writer.pages[number]
            raw = page.raw_get("/Resources")
            original = _resolve(raw)
            resources_key = _key(raw, original)
            if resources_key not in resource_copies:
                kept.append(original)
                resources = DictionaryObject(original)
                resources[NameObject("/XObject")] = copy_ref
                resource_copies[resources_key] = writer._add_object(resources)
            page[NameObject("/Resources")] = resource_copies[resources_key]
    nodes_seen: set[Key] = set()
    # After every page has its copy, so the visiting order cannot skip a node.
    for page in writer.pages:
        raw_node = page.raw_get("/Parent") if "/Parent" in page else None
        while raw_node is not None:
            node = _resolve(raw_node)
            if not isinstance(node, DictionaryObject):
                break
            node_key = _key(raw_node, node)
            if node_key in nodes_seen:
                break
            nodes_seen.add(node_key)
            kept.append(node)
            if "/Resources" in node:
                _repoint_node(writer, node, resource_copies, copy_refs, kept)
            raw_node = node.raw_get("/Parent") if "/Parent" in node else None


def _repoint_node(
    writer: PdfWriter,
    node: DictionaryObject,
    resource_copies: dict[Key, IndirectObject],
    copy_refs: dict[Key, IndirectObject],
    kept: list[object],
) -> None:
    raw = node.raw_get("/Resources")
    original = _resolve(raw)
    resources_key = _key(raw, original)
    shares = isinstance(original, DictionaryObject) and "/XObject" in original
    if resources_key not in resource_copies and shares:
        # pypdf's clone gives each page a direct copy of an inherited /Resources, so the node's
        # own /Resources has another key; what it shares with the pages is the /XObject dict.
        raw_xobjects = original.raw_get("/XObject")
        xobjects_key = _key(raw_xobjects, _resolve(raw_xobjects))
        if xobjects_key in copy_refs:
            kept.append(original)
            resources = DictionaryObject(original)
            resources[NameObject("/XObject")] = copy_refs[xobjects_key]
            resource_copies[resources_key] = writer._add_object(resources)
    if resources_key in resource_copies:
        node[NameObject("/Resources")] = resource_copies[resources_key]


def _sweep(writer: PdfWriter) -> None:
    """Drops every object unreachable from the trailer, orphan cycles included.

    O(objects + entries). pypdf's remove_unreferenced drops one level per call and never an
    orphan /Kids <-> /Parent cycle.
    """
    seen: set[int] = set()
    roots: list[Any] = [writer._root_object, writer._info, writer._ID, writer._encrypt_entry]
    stack = [root for root in roots if root is not None]
    while stack:
        item = stack.pop()
        if isinstance(item, IndirectObject):
            if item.pdf is not writer or item.idnum in seen:
                continue
            seen.add(item.idnum)
            stack.append(item.get_object())
        elif isinstance(item, DictionaryObject):
            stack.extend(item.values())
        elif isinstance(item, ArrayObject):
            stack.extend(item)
    for root in roots:
        reference = getattr(root, "indirect_reference", None)
        if reference is not None:
            seen.add(reference.idnum)
    for index in range(len(writer._objects)):
        if index + 1 not in seen:
            writer._objects[index] = None


def _finish(writer: PdfWriter, out: Path, *, copies: bool) -> None:
    for page in writer.pages:
        check_deadline()
        page.compress_content_streams()
    if copies:
        # Sweep first: with both flags, pypdf can keep an unreferenced duplicate (the old image a
        # copy left behind) as the representative of identical images and then drop it, leaving
        # the other pages pointing to nothing.
        _sweep(writer)
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=False)
    else:
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    write_pdf(writer, out)
