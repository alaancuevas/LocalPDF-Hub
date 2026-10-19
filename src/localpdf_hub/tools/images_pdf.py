"""Images as PDF pages, centred on the chosen page size and kept lossless.

JPEG photos go in as they are (minus their metadata); PNG and TIFF go in
as PNG-predicted Flate streams, which PDF readers decode back to the same
pixels. Only HEIC and CMYK JPEG are re-encoded, as JPEG q90.
"""

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pi_heif
from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, IndirectObject, NameObject, NumberObject, StreamObject

from localpdf_hub import errors, settings
from localpdf_hub.errors import AppError
from localpdf_hub.limits import check_deadline, check_result_size
from localpdf_hub.tools.pdf_files import write_pdf
from localpdf_hub.workspace import without_prefix

# Before any Image.open: "HEIF" in _FORMATS is unknown to Pillow until then.
pi_heif.register_heif_opener()

# Never by suffix: an EPS renamed to .png would otherwise run Ghostscript.
_FORMATS = ("JPEG", "PNG", "TIFF", "HEIF")

_PAGE_SIZES = {"A4": (595.0, 842.0), "letter": (612.0, 792.0)}
_ORIENTATIONS = ("portrait", "landscape")
_MARGINS = (0, 20, 40)
# "fit" keeps the rule from before 4.1: the long side matches A4 (11.69 in),
# and small images keep their size at 72 dpi.
_FIT_LONG_SIDE_IN = 11.69
_JPEG_QUALITY = 90

# EXIF orientation as a map of the unit square (x = a u + c v + e, y = b u + d v + f).
_Matrix = tuple[float, float, float, float, float, float]
_IDENTITY: _Matrix = (1, 0, 0, 1, 0, 0)
_EXIF_MAPS: dict[int, _Matrix] = {
    1: (1, 0, 0, 1, 0, 0),
    2: (-1, 0, 0, 1, 1, 0),
    3: (-1, 0, 0, -1, 1, 1),
    4: (1, 0, 0, -1, 0, 1),
    5: (0, -1, -1, 0, 1, 1),
    6: (0, -1, 1, 0, 0, 1),
    7: (0, 1, 1, 0, 0, 0),
    8: (0, 1, -1, 0, 1, 0),
}
_CLOCKWISE_90: _Matrix = (0, -1, 1, 0, 0, 1)
_EXIF_ORIENTATION = 0x0112

# JPEG segments kept: JFIF (APP0), ICC profile (APP2) and Adobe (APP14).
_KEPT_APP_MARKERS = {0xE0, 0xE2, 0xEE}
_COMMENT = 0xFE
_START_OF_SCAN = 0xDA
_END_OF_IMAGE = 0xD9

_GRAY_16 = ("I;16", "I;16B", "I;16L", "I")
_WITH_ALPHA = ("RGBA", "LA", "La", "PA", "RGBa")
_TO_RGB = ("P", "CMYK", "YCbCr", "LAB")


@dataclass(frozen=True)
class Layout:
    pagesize: str = "A4"
    orientation: str = "portrait"
    margin: int = 0


def parse_layout(pagesize: str = "A4", orientation: str = "portrait", margin: int = 0) -> Layout:
    if pagesize not in (*_PAGE_SIZES, "fit"):
        raise AppError(errors.INVALID_INPUT, f"Page size {pagesize!r} is not supported.")
    if orientation not in _ORIENTATIONS:
        raise AppError(errors.INVALID_INPUT, f"Orientation {orientation!r} is not supported.")
    if margin not in _MARGINS:
        raise AppError(errors.INVALID_INPUT, f"Margin {margin} is not one of {_MARGINS}.")
    return Layout(pagesize, orientation, margin)


def images_to_pdf(
    paths: list[Path], rotations: list[int], layout: Layout, merge_after: bool, out_dir: Path
) -> Path:
    """One PDF named after the first image, or a ZIP with one PDF per image."""
    total = 0
    if merge_after:
        writer = PdfWriter()
        for index, path in enumerate(paths):
            total += add_image_page(writer, path, _rotation(rotations, index), layout)
            check_result_size(total)
        return write_pdf(writer, out_dir / f"{paths[0].stem}.pdf")

    out = out_dir / "images.zip"
    used: set[str] = set()
    # PDF streams are already compressed.
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as archive:
        for index, path in enumerate(paths):
            writer = PdfWriter()
            total += add_image_page(writer, path, _rotation(rotations, index), layout)
            check_result_size(total)
            pdf = write_pdf(writer, out_dir / f"{path.stem}.pdf")
            # Uploads are stored as "000_name.png"; the user expects "name.pdf",
            # unless two uploads had the same name.
            name = without_prefix(pdf.name)
            if name in used:
                name = pdf.name
            used.add(name)
            archive.write(pdf, arcname=name)
            pdf.unlink()
    return out


def add_image_page(writer: PdfWriter, path: Path, rotation: int, layout: Layout) -> int:
    """Adds one page holding the image and returns the bytes of its image streams.

    Rotation is clockwise, in multiples of 90.
    """
    check_deadline()
    turns = (rotation // 90) % 4
    with _open(path) as image:
        try:
            if image.format in ("JPEG", "MPO") and image.mode in ("RGB", "L"):
                xobject, unit, size = _jpeg_as_is(writer, path, image, turns)
            else:
                upright = ImageOps.exif_transpose(image)
                if turns:
                    upright = upright.rotate(-90 * turns, expand=True)
                if image.format in ("JPEG", "MPO", "HEIF"):
                    xobject = _jpeg_reencoded(writer, upright)
                else:
                    xobject = _lossless(writer, upright)
                unit, size = _IDENTITY, upright.size
        except ValueError as error:
            # Pillow has no conversion for some rare modes.
            raise AppError(errors.INVALID_INPUT, f"{path.name}: {error}") from error
        except OSError as error:
            raise AppError(errors.INVALID_INPUT, f"{path.name} is not a readable image.") from error

    width, height, x, y, drawn_w, drawn_h = _place(layout, *size)
    page = writer.add_blank_page(width, height)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): xobject})}
    )
    a, b, c, d, e, f = unit
    matrix = (a * drawn_w, b * drawn_h, c * drawn_w, d * drawn_h, e * drawn_w + x, f * drawn_h + y)
    content = StreamObject()
    content.set_data(f"q {' '.join(f'{v:.4f}' for v in matrix)} cm /Im0 Do Q".encode())
    page[NameObject("/Contents")] = writer._add_object(content)
    return _stream_bytes(xobject)


def _stream_bytes(xobject: IndirectObject) -> int:
    stream = cast(StreamObject, xobject.get_object())
    size = len(stream.get_data())
    if "/SMask" in stream:
        size += len(cast(StreamObject, stream["/SMask"].get_object()).get_data())
    return size


def _rotation(rotations: list[int], index: int) -> int:
    return rotations[index] if index < len(rotations) else 0


def _open(path: Path) -> Image.Image:
    try:
        image = Image.open(path, formats=_FORMATS)
    except Image.DecompressionBombError as error:
        raise AppError(errors.IMAGE_TOO_LARGE, f"{path.name} has too many pixels.") from error
    except (UnidentifiedImageError, OSError) as error:
        raise AppError(errors.INVALID_INPUT, f"{path.name} is not a readable image.") from error
    # The size comes from the header; nothing is decoded yet.
    if image.width * image.height > settings.MAX_RENDER_PIXELS:
        image.close()
        raise AppError(
            errors.IMAGE_TOO_LARGE,
            f"{path.name} is over {settings.MAX_RENDER_PIXELS // 1_000_000} megapixels.",
        )
    return image


def _place(layout: Layout, width: int, height: int) -> tuple[float, ...]:
    """Page size, image origin and drawn size, in points."""
    margin = layout.margin
    if layout.pagesize == "fit":
        dpi = max(72.0, max(width, height) / _FIT_LONG_SIDE_IN)
        drawn_w, drawn_h = width * 72 / dpi, height * 72 / dpi
        return drawn_w + 2 * margin, drawn_h + 2 * margin, margin, margin, drawn_w, drawn_h
    page_w, page_h = _PAGE_SIZES[layout.pagesize]
    if layout.orientation == "landscape":
        page_w, page_h = page_h, page_w
    # Whole image inside the margins, centred, enlarged if small.
    scale = min((page_w - 2 * margin) / width, (page_h - 2 * margin) / height)
    drawn_w, drawn_h = width * scale, height * scale
    return page_w, page_h, (page_w - drawn_w) / 2, (page_h - drawn_h) / 2, drawn_w, drawn_h


def _jpeg_as_is(
    writer: PdfWriter, path: Path, image: Image.Image, turns: int
) -> tuple[IndirectObject, _Matrix, tuple[int, int]]:
    orientation = image.getexif().get(_EXIF_ORIENTATION, 1)
    if orientation not in _EXIF_MAPS:
        orientation = 1
    data = strip_jpeg_metadata(path.read_bytes(), path.name)
    _check_jpeg(data, path.name)

    unit = _EXIF_MAPS[orientation]
    for _ in range(turns):
        unit = _multiply(unit, _CLOCKWISE_90)
    width, height = image.size
    # Orientations 5 to 8 swap the sides, and so does each quarter turn.
    if (orientation >= 5) != (turns % 2 == 1):
        width, height = height, width
    colorspace = "/DeviceRGB" if image.mode == "RGB" else "/DeviceGray"
    xobject = _image_xobject(writer, data, image.size, colorspace, "/DCTDecode")
    return xobject, unit, (width, height)


def strip_jpeg_metadata(data: bytes, name: str) -> bytes:
    """Drops EXIF, XMP and comments segment by segment, also between scans.

    The scan data is copied untouched, so the pixels stay the same; the copy
    ends at the real end-of-image marker, which also drops the extra frames
    of an MPO file.
    """
    if data[:2] != b"\xff\xd8":
        raise AppError(errors.INVALID_INPUT, f"{name} is not a readable image.")
    out = bytearray(data[:2])
    pos, end = 2, len(data)
    while pos + 1 < end:
        if data[pos] != 0xFF:
            break
        marker = data[pos + 1]
        if marker == 0xFF:
            pos += 1
            continue
        if marker == _END_OF_IMAGE:
            out += data[pos : pos + 2]
            return bytes(out)
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            out += data[pos : pos + 2]
            pos += 2
            continue
        if pos + 4 > end:
            break
        segment_end = pos + 2 + int.from_bytes(data[pos + 2 : pos + 4], "big")
        if segment_end > end:
            break
        application = 0xE1 <= marker <= 0xEF and marker not in _KEPT_APP_MARKERS
        if not (application or marker == _COMMENT):
            out += data[pos:segment_end]
        pos = segment_end
        if marker == _START_OF_SCAN:
            scan_end = _end_of_scan(data, pos)
            out += data[pos:scan_end]
            pos = scan_end
    raise AppError(errors.INVALID_INPUT, f"{name} is cut short or damaged.")


def _end_of_scan(data: bytes, pos: int) -> int:
    """Index of the first marker after entropy-coded data (not FF00 or a restart)."""
    while True:
        pos = data.find(b"\xff", pos)
        if pos == -1 or pos + 1 >= len(data):
            return len(data)
        following = data[pos + 1]
        if following == 0x00 or 0xD0 <= following <= 0xD7:
            pos += 2
        elif following == 0xFF:
            pos += 1
        else:
            return pos


def _check_jpeg(data: bytes, name: str) -> None:
    # Decoding at 1/8 scale catches a cut or broken file in a few milliseconds.
    try:
        with Image.open(io.BytesIO(data), formats=("JPEG",)) as probe:
            probe.draft(probe.mode, (probe.width // 8, probe.height // 8))
            probe.load()
    except (UnidentifiedImageError, OSError) as error:
        raise AppError(errors.INVALID_INPUT, f"{name} is cut short or damaged.") from error


def _jpeg_reencoded(writer: PdfWriter, image: Image.Image) -> IndirectObject:
    if image.mode in _WITH_ALPHA or "transparency" in image.info:
        rgba = image.convert("LA").convert("RGBA") if image.mode == "La" else image.convert("RGBA")
        image = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba)
    rgb = image.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, "JPEG", quality=_JPEG_QUALITY)
    return _image_xobject(writer, buf.getvalue(), rgb.size, "/DeviceRGB", "/DCTDecode")


def _lossless(writer: PdfWriter, image: Image.Image) -> IndirectObject:
    base, alpha = _normalized(image)
    colorspace = "/DeviceRGB" if base.mode == "RGB" else "/DeviceGray"
    smask = None if alpha is None else _predicted_xobject(writer, alpha, "/DeviceGray")
    return _predicted_xobject(writer, base, colorspace, smask)


def _normalized(image: Image.Image) -> tuple[Image.Image, Image.Image | None]:
    """8-bit gray or RGB pixels, plus the alpha channel when there is one."""
    mode = image.mode
    if mode in _WITH_ALPHA or "transparency" in image.info:
        # From RGBA, never straight from a palette: that would bring back
        # the colour hidden under transparent pixels.
        rgba = image.convert("LA").convert("RGBA") if mode == "La" else image.convert("RGBA")
        return rgba.convert("RGB"), rgba.getchannel("A")
    if mode in ("L", "RGB"):
        return image, None
    if mode in _GRAY_16:
        # convert("L") clips 16-bit values instead of scaling them.
        return image.convert("I").point(lambda value: value * (1 / 257)).convert("L"), None
    if mode == "1":
        return image.convert("L"), None
    if mode in _TO_RGB:
        return image.convert("RGB"), None
    raise ValueError(f"image mode {mode} is not supported")


def _predicted_xobject(
    writer: PdfWriter, image: Image.Image, colorspace: str, smask: IndirectObject | None = None
) -> IndirectObject:
    colors = 3 if image.mode == "RGB" else 1
    parms = DictionaryObject(
        {
            NameObject("/Predictor"): NumberObject(15),
            NameObject("/Colors"): NumberObject(colors),
            NameObject("/BitsPerComponent"): NumberObject(8),
            NameObject("/Columns"): NumberObject(image.width),
        }
    )
    data = _png_idat(image)
    return _image_xobject(writer, data, image.size, colorspace, "/FlateDecode", parms, smask)


def _png_idat(image: Image.Image) -> bytes:
    """The zlib stream of PNG-filtered rows, which FlateDecode with Predictor 15 reads."""
    buf = io.BytesIO()
    image.save(buf, "PNG", compress_level=6)
    data = buf.getvalue()
    chunks = []
    pos = 8
    while pos < len(data):
        length = int.from_bytes(data[pos : pos + 4], "big")
        if data[pos + 4 : pos + 8] == b"IDAT":
            chunks.append(data[pos + 8 : pos + 8 + length])
        pos += 12 + length
    return b"".join(chunks)


def _image_xobject(
    writer: PdfWriter,
    data: bytes,
    size: tuple[int, int],
    colorspace: str,
    filter_name: str,
    parms: DictionaryObject | None = None,
    smask: IndirectObject | None = None,
) -> IndirectObject:
    # A plain StreamObject writes the bytes as given, with our own /Filter.
    stream = StreamObject()
    stream.set_data(data)
    stream.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(size[0]),
            NameObject("/Height"): NumberObject(size[1]),
            NameObject("/BitsPerComponent"): NumberObject(8),
            NameObject("/ColorSpace"): NameObject(colorspace),
            NameObject("/Filter"): NameObject(filter_name),
        }
    )
    if parms is not None:
        stream[NameObject("/DecodeParms")] = parms
    if smask is not None:
        stream[NameObject("/SMask")] = smask
    # pypdf 6 has no public add_object; tests/test_images_pdf.py pins this.
    return writer._add_object(stream)


def _multiply(first: _Matrix, second: _Matrix) -> _Matrix:
    a, b, c, d, e, f = first
    g, h, i, j, k, m = second
    return (
        a * g + b * i,
        a * h + b * j,
        c * g + d * i,
        c * h + d * j,
        e * g + f * i + k,
        e * h + f * j + m,
    )
