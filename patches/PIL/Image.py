"""Pure-Python image metadata reader for NanVix.

Parses PNG, JPEG, GIF, BMP, and TIFF headers to extract dimensions and
color mode — the minimum python-pptx needs from PIL.Image.
"""

from __future__ import annotations

import io
import struct
from pathlib import Path

MAX_IMAGE_HEADER_BYTES = 1 << 20  # 1 MiB
MAX_IMAGE_DIMENSION = 100_000
MAX_IMAGE_PIXELS = 100_000_000


def _validate_size(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid image dimensions: {width}x{height}")
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise ValueError(
            f"Image dimension {max(width, height)} exceeds limit {MAX_IMAGE_DIMENSION}"
        )
    if width * height > MAX_IMAGE_PIXELS:
        raise ValueError(
            f"Image pixel count {width * height} exceeds limit {MAX_IMAGE_PIXELS}"
        )


class Image:
    """Minimal image metadata container."""

    def __init__(self) -> None:
        self.format: str | None = None
        self.size: tuple[int, int] = (0, 0)
        self.mode: str = "RGB"
        self.color: str | tuple | None = None
        self.info: dict = {}
        self._fp: io.BytesIO | None = None

    @property
    def width(self) -> int:
        return self.size[0]

    @property
    def height(self) -> int:
        return self.size[1]

    def close(self) -> None:
        self._fp = None

    def save(self, fp, format=None, **kwargs):
        raise NotImplementedError("NanVix PIL shim does not support saving images")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _read_all_bytes(fp) -> bytes:
    data = fp.read(MAX_IMAGE_HEADER_BYTES + 1)
    if len(data) > MAX_IMAGE_HEADER_BYTES:
        data = data[:MAX_IMAGE_HEADER_BYTES]
    return data


def _parse_png(data: bytes) -> Image:
    if len(data) < 24:
        raise ValueError("PNG header too short")
    w = struct.unpack(">I", data[16:20])[0]
    h = struct.unpack(">I", data[20:24])[0]
    _validate_size(w, h)
    bit_depth = data[24] if len(data) > 24 else 8
    color_type = data[25] if len(data) > 25 else 2
    mode_map = {0: "L", 2: "RGB", 3: "P", 4: "LA", 6: "RGBA"}
    img = Image()
    img.format = "PNG"
    img.size = (w, h)
    img.mode = mode_map.get(color_type, "RGB")
    return img


def _parse_jpeg(data: bytes) -> Image:
    i = 2
    while i < len(data) - 1:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker == 0xFF:
            i += 1
            continue
        if marker == 0x00 or marker == 0xD8:
            i += 2
            continue
        if i + 3 >= len(data):
            break
        seglen = struct.unpack(">H", data[i + 2 : i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if seglen >= 8 and i + 9 < len(data):
                h = struct.unpack(">H", data[i + 5 : i + 7])[0]
                w = struct.unpack(">H", data[i + 7 : i + 9])[0]
                ncomp = data[i + 9] if i + 9 < len(data) else 3
                _validate_size(w, h)
                img = Image()
                img.format = "JPEG"
                img.size = (w, h)
                img.mode = {1: "L", 3: "RGB", 4: "CMYK"}.get(ncomp, "RGB")
                return img
        i += 2 + seglen
    raise ValueError("No SOF marker found in JPEG")


def _parse_gif(data: bytes) -> Image:
    if len(data) < 10:
        raise ValueError("GIF header too short")
    w = struct.unpack("<H", data[6:8])[0]
    h = struct.unpack("<H", data[8:10])[0]
    _validate_size(w, h)
    img = Image()
    img.format = "GIF"
    img.size = (w, h)
    img.mode = "P"
    return img


def _parse_bmp(data: bytes) -> Image:
    if len(data) < 26:
        raise ValueError("BMP header too short")
    w = abs(struct.unpack("<i", data[18:22])[0])
    h = abs(struct.unpack("<i", data[22:26])[0])
    _validate_size(w, h)
    img = Image()
    img.format = "BMP"
    img.size = (w, h)
    img.mode = "RGB"
    return img


def _parse_tiff(data: bytes) -> Image:
    if len(data) < 8:
        raise ValueError("TIFF header too short")
    bo = "<" if data[:2] == b"II" else ">"
    ifd_offset = struct.unpack(f"{bo}I", data[4:8])[0]
    if ifd_offset + 2 > len(data):
        raise ValueError("TIFF IFD offset out of range")
    num_entries = struct.unpack(f"{bo}H", data[ifd_offset : ifd_offset + 2])[0]
    w = h = 0
    for j in range(num_entries):
        off = ifd_offset + 2 + j * 12
        if off + 12 > len(data):
            break
        tag = struct.unpack(f"{bo}H", data[off : off + 2])[0]
        val = struct.unpack(f"{bo}I", data[off + 8 : off + 12])[0]
        if tag == 256:
            w = val
        elif tag == 257:
            h = val
    if w and h:
        _validate_size(w, h)
    img = Image()
    img.format = "TIFF"
    img.size = (w, h)
    img.mode = "RGB"
    return img


_PARSERS = [
    (b"\x89PNG\r\n\x1a\n", _parse_png),
    (b"\xff\xd8\xff", _parse_jpeg),
    (b"GIF87a", _parse_gif),
    (b"GIF89a", _parse_gif),
    (b"BM", _parse_bmp),
    (b"II", _parse_tiff),
    (b"MM", _parse_tiff),
]


def open(fp, mode="r"):
    if isinstance(fp, (str, Path)):
        with builtins_open(str(fp), "rb") as f:
            data = _read_all_bytes(f)
    elif hasattr(fp, "read"):
        data = _read_all_bytes(fp)
    else:
        raise TypeError(f"Unsupported argument type: {type(fp)}")

    for sig, parser in _PARSERS:
        if data[: len(sig)] == sig:
            img = parser(data)
            img._fp = io.BytesIO(data)
            return img
    raise ValueError("Unrecognized image format")


def new(mode, size, color=0):
    _validate_size(size[0], size[1])
    img = Image()
    img.mode = mode
    img.size = tuple(size)
    img.color = color
    return img


import builtins as _builtins
builtins_open = _builtins.open

# Rotation constants
ROTATE_90 = 2
ROTATE_180 = 3
ROTATE_270 = 4
FLIP_LEFT_RIGHT = 0
FLIP_TOP_BOTTOM = 1
TRANSPOSE = 5
TRANSVERSE = 6

# Resampling
NEAREST = 0
BILINEAR = 2
BICUBIC = 3
LANCZOS = 1
