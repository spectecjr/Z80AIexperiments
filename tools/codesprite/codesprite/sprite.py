"""Sprite import and packing into mode 4 byte cells.

A :class:`Sprite` is a rectangle of 4-bit colour indices where ``None``
means transparent.  Packing it for the screen is the only place nibble
arithmetic lives:

  * mode 4 stores the LEFT pixel of a byte in the HIGH nibble;
  * an odd screen x means the sprite is shifted by one pixel, which is
    expressed by prepending one transparent pixel (``phase`` 1);
  * every resulting byte becomes a :class:`Cell` with a mask of 0xFF
    (both pixels opaque), 0xF0 (left pixel only), or 0x0F (right pixel
    only).  Fully transparent bytes are dropped - the compiled code never
    touches them.

Mask convention: ``mask`` names the bits the sprite OWNS.  Read-modify-write
code therefore does ``AND ~mask : OR value``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MASK_BOTH = 0xFF
MASK_HIGH = 0xF0  # left pixel only
MASK_LOW = 0x0F  # right pixel only


class SpriteError(ValueError):
    """Raised for malformed sprite input."""


@dataclass(frozen=True)
class Cell:
    """One screen byte written by the sprite.

    ``row`` is the sprite row (0-based), ``col`` the byte column within the
    shifted sprite (0-based).  ``value`` holds the sprite's pixels already
    positioned in their nibbles, with the non-owned nibble zeroed.
    """

    row: int
    col: int
    value: int
    mask: int

    @property
    def opaque(self) -> bool:
        return self.mask == MASK_BOTH


@dataclass(frozen=True)
class PackedSprite:
    """A sprite packed for one x phase."""

    phase: int
    byte_width: int
    height: int
    cells: tuple[Cell, ...]

    def rows(self) -> dict[int, list[Cell]]:
        out: dict[int, list[Cell]] = {}
        for cell in self.cells:
            out.setdefault(cell.row, []).append(cell)
        for cells in out.values():
            cells.sort(key=lambda c: c.col)
        return out

    @property
    def opaque_count(self) -> int:
        return sum(1 for c in self.cells if c.opaque)

    @property
    def half_count(self) -> int:
        return sum(1 for c in self.cells if not c.opaque)

    def span(self, row: int) -> tuple[int, int] | None:
        """Inclusive byte-column span touched in ``row``, or None if empty."""
        cols = [c.col for c in self.cells if c.row == row]
        if not cols:
            return None
        return min(cols), max(cols)


class Sprite:
    """A 16-colour sprite with per-pixel transparency."""

    def __init__(self, pixels: list[list[int | None]], name: str = "sprite") -> None:
        if not pixels or not pixels[0]:
            raise SpriteError("sprite is empty")
        width = len(pixels[0])
        for y, row in enumerate(pixels):
            if len(row) != width:
                raise SpriteError(f"row {y} has {len(row)} pixels, expected {width}")
            for x, value in enumerate(row):
                if value is not None and not 0 <= value <= 15:
                    raise SpriteError(
                        f"pixel ({x},{y}) = {value} is not a 4-bit colour index"
                    )
        self.pixels = [list(row) for row in pixels]
        self.name = name

    @property
    def width(self) -> int:
        return len(self.pixels[0])

    @property
    def height(self) -> int:
        return len(self.pixels)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Sprite {self.name} {self.width}x{self.height}>"

    def get(self, x: int, y: int) -> int | None:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.pixels[y][x]
        return None

    def crop(self, x: int, y: int, w: int, h: int) -> "Sprite":
        if w <= 0 or h <= 0:
            raise SpriteError("crop rectangle must be positive")
        if x < 0 or y < 0 or x + w > self.width or y + h > self.height:
            raise SpriteError("crop rectangle lies outside the sprite")
        rows = [row[x : x + w] for row in self.pixels[y : y + h]]
        return Sprite(rows, f"{self.name}_{x}_{y}")

    def trimmed(self) -> tuple["Sprite", int, int]:
        """Drop fully transparent border rows/columns.

        Returns the trimmed sprite plus the (dx, dy) offset that must be
        added to a draw position to keep the image in the same place.
        """
        xs = [x for y in range(self.height) for x in range(self.width)
              if self.pixels[y][x] is not None]
        ys = [y for y in range(self.height) for x in range(self.width)
              if self.pixels[y][x] is not None]
        if not xs:
            return self, 0, 0
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        return self.crop(x0, y0, x1 - x0 + 1, y1 - y0 + 1), x0, y0

    def pack(self, phase: int = 0) -> PackedSprite:
        """Pack into screen bytes for x phase 0 (even x) or 1 (odd x)."""
        if phase not in (0, 1):
            raise SpriteError(f"phase must be 0 or 1, not {phase}")
        byte_width = (self.width + phase + 1) // 2
        cells: list[Cell] = []
        for row in range(self.height):
            for col in range(byte_width):
                # Pixel offsets inside the shifted sprite.
                left = self.get(col * 2 - phase, row)
                right = self.get(col * 2 + 1 - phase, row)
                mask = 0
                value = 0
                if left is not None:
                    mask |= MASK_HIGH
                    value |= (left & 0x0F) << 4
                if right is not None:
                    mask |= MASK_LOW
                    value |= right & 0x0F
                if mask:
                    cells.append(Cell(row, col, value, mask))
        return PackedSprite(phase, byte_width, self.height, tuple(cells))


# --------------------------------------------------------------------------
# Loaders
# --------------------------------------------------------------------------

_TXT_RE = re.compile(r"^[0-9a-fA-F.]+$")


def load_txt(path: str | Path) -> Sprite:
    """Load a text sprite: one hex digit per pixel, ``.`` = transparent.

    Blank lines and lines starting with ``#`` or ``;`` are ignored.
    """
    path = Path(path)
    rows: list[list[int | None]] = []
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if not _TXT_RE.match(line):
            raise SpriteError(f"{path}:{lineno}: expected hex digits or '.', got {raw!r}")
        rows.append([None if ch == "." else int(ch, 16) for ch in line])
    if not rows:
        raise SpriteError(f"{path}: no pixel rows found")
    return Sprite(rows, path.stem)


def save_txt(sprite: Sprite, path: str | Path) -> None:
    """Write a sprite back out in the text format (used by tests/tools)."""
    lines = [
        "".join("." if v is None else f"{v:x}" for v in row) for row in sprite.pixels
    ]
    Path(path).write_text("\n".join(lines) + "\n")


def load_bin(
    path: str | Path,
    width: int,
    height: int,
    mask_path: str | Path | None = None,
    transparent_index: int | None = None,
) -> Sprite:
    """Load packed nibbles (``width//2`` bytes per row, high nibble left).

    Transparency comes either from a mask file (one byte per pixel,
    non-zero = opaque) or from ``transparent_index``.
    """
    if width % 2:
        raise SpriteError("binary sprites need an even pixel width")
    data = Path(path).read_bytes()
    stride = width // 2
    if len(data) < stride * height:
        raise SpriteError(
            f"{path}: {len(data)} bytes is short of {stride * height} for {width}x{height}"
        )
    mask: bytes | None = None
    if mask_path is not None:
        mask = Path(mask_path).read_bytes()
        if len(mask) < width * height:
            raise SpriteError(f"{mask_path}: mask is shorter than {width * height} bytes")
    rows: list[list[int | None]] = []
    for y in range(height):
        row: list[int | None] = []
        for x in range(width):
            byte = data[y * stride + x // 2]
            value = (byte >> 4) if x % 2 == 0 else (byte & 0x0F)
            if mask is not None:
                opaque = mask[y * width + x] != 0
            else:
                opaque = transparent_index is None or value != transparent_index
            row.append(value if opaque else None)
        rows.append(row)
    return Sprite(rows, Path(path).stem)


def _nearest_index(rgb: tuple[int, int, int], palette: list[tuple[int, int, int]]) -> int:
    r, g, b = rgb
    best, best_d = 0, None
    for i, (pr, pg, pb) in enumerate(palette):
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if best_d is None or d < best_d:
            best, best_d = i, d
    return best


def load_palette(path: str | Path) -> list[tuple[int, int, int]]:
    """Load up to 16 ``R G B`` triples (decimal or ``#rrggbb``) from a file."""
    entries: list[tuple[int, int, int]] = []
    for lineno, raw in enumerate(Path(path).read_text().splitlines(), 1):
        line = raw.split("#", 1)[0].strip() if not raw.strip().startswith("#") else raw.strip()
        if line.startswith("#") and len(line) in (7, 9):
            entries.append(
                (int(line[1:3], 16), int(line[3:5], 16), int(line[5:7], 16))
            )
            continue
        if not line:
            continue
        parts = line.replace(",", " ").split()
        if len(parts) < 3:
            raise SpriteError(f"{path}:{lineno}: expected 'R G B', got {raw!r}")
        entries.append(tuple(int(p, 0) for p in parts[:3]))  # type: ignore[arg-type]
    if not 1 <= len(entries) <= 16:
        raise SpriteError(f"{path}: expected 1..16 palette entries, got {len(entries)}")
    return entries


def load_png(
    path: str | Path,
    palette: list[tuple[int, int, int]] | None = None,
    transparent_index: int | None = None,
    mask_path: str | Path | None = None,
    nearest: bool = False,
) -> tuple[Sprite, list[tuple[int, int, int]] | None]:
    """Load a PNG into a sprite, returning it with its palette if it had one.

    Indexed PNGs keep their indices (which must all be < 16).  Truecolour
    PNGs need ``palette``; colours must match exactly unless ``nearest``.
    Transparency is taken from the alpha channel, ``transparent_index``,
    or a mask image (non-zero/non-black = opaque).
    """
    from PIL import Image  # imported lazily so the txt path needs no Pillow

    image = Image.open(path)
    width, height = image.size
    alpha: list[list[int]] | None = None
    if image.mode in ("P", "PA"):
        png_palette = image.getpalette() or []
        entries = [
            (png_palette[i * 3], png_palette[i * 3 + 1], png_palette[i * 3 + 2])
            for i in range(min(16, len(png_palette) // 3))
        ]
        if "transparency" in image.info and isinstance(image.info["transparency"], bytes):
            tinfo = image.info["transparency"]
            alpha = [
                [tinfo[image.getpixel((x, y))] if image.getpixel((x, y)) < len(tinfo) else 255
                 for x in range(width)]
                for y in range(height)
            ]
        indexed = image.convert("P")
        rows: list[list[int | None]] = []
        for y in range(height):
            row: list[int | None] = []
            for x in range(width):
                value = indexed.getpixel((x, y))
                if value > 15:
                    raise SpriteError(
                        f"{path}: palette index {value} at ({x},{y}) exceeds 15"
                    )
                row.append(value)
            rows.append(row)
        found_palette: list[tuple[int, int, int]] | None = entries or None
    else:
        rgba = image.convert("RGBA")
        if palette is None:
            raise SpriteError(
                f"{path} is not an indexed PNG; supply --palette to map colours"
            )
        alpha = [[rgba.getpixel((x, y))[3] for x in range(width)] for y in range(height)]
        rows = []
        for y in range(height):
            row = []
            for x in range(width):
                r, g, b, _a = rgba.getpixel((x, y))
                if (r, g, b) in palette:
                    row.append(palette.index((r, g, b)))
                elif nearest:
                    row.append(_nearest_index((r, g, b), palette))
                else:
                    raise SpriteError(
                        f"{path}: colour #{r:02x}{g:02x}{b:02x} at ({x},{y}) is not in "
                        "the palette (use --nearest to snap)"
                    )
            rows.append(row)
        found_palette = palette

    # Apply transparency.
    mask_pixels = None
    if mask_path is not None:
        from PIL import Image as _Image

        mask_image = _Image.open(mask_path).convert("L")
        if mask_image.size != (width, height):
            raise SpriteError(f"{mask_path}: mask size {mask_image.size} != {(width, height)}")
        mask_pixels = [
            [mask_image.getpixel((x, y)) for x in range(width)] for y in range(height)
        ]
    for y in range(height):
        for x in range(width):
            transparent = False
            if mask_pixels is not None:
                transparent = mask_pixels[y][x] == 0
            elif transparent_index is not None:
                transparent = rows[y][x] == transparent_index
            elif alpha is not None:
                transparent = alpha[y][x] < 128
            if transparent:
                rows[y][x] = None
    return Sprite(rows, Path(path).stem), found_palette


def load_sprite(
    path: str | Path,
    *,
    width: int | None = None,
    height: int | None = None,
    palette_path: str | Path | None = None,
    transparent_index: int | None = None,
    mask_path: str | Path | None = None,
    nearest: bool = False,
    rect: tuple[int, int, int, int] | None = None,
) -> tuple[Sprite, list[tuple[int, int, int]] | None]:
    """Load a sprite from .txt, .png or raw .bin, honouring an optional crop."""
    path = Path(path)
    suffix = path.suffix.lower()
    palette = load_palette(palette_path) if palette_path else None
    if suffix == ".txt":
        sprite, found = load_txt(path), None
    elif suffix in (".png", ".gif", ".bmp"):
        sprite, found = load_png(
            path,
            palette=palette,
            transparent_index=transparent_index,
            mask_path=mask_path,
            nearest=nearest,
        )
    elif suffix in (".bin", ".raw", ".dat"):
        if width is None or height is None:
            raise SpriteError("binary sprites need --width and --height")
        sprite, found = (
            load_bin(path, width, height, mask_path, transparent_index),
            palette,
        )
    else:
        raise SpriteError(f"{path}: unknown sprite format {suffix!r}")
    if rect is not None:
        sprite = sprite.crop(*rect)
    return sprite, found or palette
