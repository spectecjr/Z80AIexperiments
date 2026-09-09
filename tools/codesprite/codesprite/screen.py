"""SAM Coupe mode 4 screen address model.

Mode 4: 256x192 pixels, 4 bits per pixel, two pixels per byte with the
LEFT pixel in the HIGH nibble.  Rows are 128 bytes and strictly linear:

    addr(y, x) = base + y * 128 + x // 2

The whole display file is 24576 bytes.  With the conventional base of
0x8000 the screen occupies 0x8000..0xDFFF, which leaves 0xE000..0xFFFF
(8 KiB) inside the same paged-in 32K half for scratch use.

Two consequences of the 128-byte stride are used all over the code
generator:

  * one 256-byte page holds exactly two display rows, so bit 7 of L is
    the row parity and bits 0..6 are x//2;
  * stepping down one row therefore never needs an address immediate:
    from an even row it is ``SET 7,L`` (8T), from an odd row it is
    ``INC H : RES 7,L`` (12T).
"""

from __future__ import annotations

from dataclasses import dataclass

WIDTH = 256
HEIGHT = 192
BPP = 4
PIXELS_PER_BYTE = 2
BYTES_PER_ROW = WIDTH // PIXELS_PER_BYTE  # 128
SCREEN_BYTES = BYTES_PER_ROW * HEIGHT  # 24576


class ScreenError(ValueError):
    """Raised for an impossible screen/scratch memory layout."""


@dataclass(frozen=True)
class Screen:
    """Address maths for one mode 4 display file.

    ``base`` must be 256-byte aligned so that row parity lives in bit 7 of
    L and the high byte advances exactly once per two rows.
    """

    base: int = 0x8000

    def __post_init__(self) -> None:
        if not 0 <= self.base <= 0xFFFF:
            raise ScreenError(f"screen base {self.base:#06x} outside 16-bit address space")
        if self.base & 0xFF:
            raise ScreenError(f"screen base {self.base:#06x} is not 256-byte aligned")

    @property
    def end(self) -> int:
        """First address past the display file (may exceed 0xFFFF)."""
        return self.base + SCREEN_BYTES

    def addr(self, y: int, x: int) -> int:
        """Address of the byte containing pixel (x, y), wrapped to 16 bits.

        Wrapping is deliberate: vertical spill clipping relies on rows
        above/below the screen resolving to whatever the memory map has
        there.
        """
        return (self.base + y * BYTES_PER_ROW + x // PIXELS_PER_BYTE) & 0xFFFF

    def addr_byte(self, y: int, col: int) -> int:
        """Address of byte column ``col`` (0..127) of row ``y``."""
        return (self.base + y * BYTES_PER_ROW + col) & 0xFFFF

    @staticmethod
    def parity(y: int) -> int:
        """Row parity: 0 = even row (low half of a page), 1 = odd row."""
        return y & 1

    def page_h(self, y: int) -> int:
        """High byte of the address of byte column 0 of row ``y``."""
        return ((self.base >> 8) + (y >> 1)) & 0xFF

    @staticmethod
    def low_l(y: int, col: int) -> int:
        """Low byte of the address of byte column ``col`` of row ``y``."""
        return ((y & 1) * 0x80 + col) & 0xFF

    def contains(self, address: int) -> bool:
        return self.base <= address < self.base + SCREEN_BYTES

    def row_of(self, address: int) -> int:
        if not self.contains(address):
            raise ScreenError(f"address {address:#06x} is not inside the display file")
        return (address - self.base) // BYTES_PER_ROW

    def col_of(self, address: int) -> int:
        if not self.contains(address):
            raise ScreenError(f"address {address:#06x} is not inside the display file")
        return (address - self.base) % BYTES_PER_ROW


@dataclass(frozen=True)
class MemoryLayout:
    """Screen plus the scratch / back-buffer regions used by save-restore."""

    screen: Screen = Screen()
    scratch_base: int = 0xE000
    backbuffer_base: int | None = None

    def check_scratch(self, size: int) -> None:
        """Validate that ``size`` bytes of scratch do not overlap the screen."""
        if size <= 0:
            return
        lo, hi = self.scratch_base, self.scratch_base + size
        if hi > 0x1_0000:
            raise ScreenError(
                f"scratch {lo:#06x}+{size} runs past the top of memory"
            )
        s_lo, s_hi = self.screen.base, self.screen.base + SCREEN_BYTES
        if lo < s_hi and s_lo < hi:
            raise ScreenError(
                f"scratch {lo:#06x}..{hi - 1:#06x} overlaps the display file "
                f"{s_lo:#06x}..{s_hi - 1:#06x}"
            )

    def check_backbuffer(self) -> None:
        if self.backbuffer_base is None:
            return
        lo, hi = self.backbuffer_base, self.backbuffer_base + SCREEN_BYTES
        if hi > 0x1_0000:
            raise ScreenError(
                f"back buffer {lo:#06x} does not fit below the top of memory"
            )
        s_lo, s_hi = self.screen.base, self.screen.base + SCREEN_BYTES
        if lo < s_hi and s_lo < hi:
            raise ScreenError("back buffer overlaps the display file")

    @property
    def backbuffer_delta(self) -> int:
        """Signed 16-bit delta from a screen address to its back-buffer twin."""
        if self.backbuffer_base is None:
            raise ScreenError("no back buffer configured")
        return (self.backbuffer_base - self.screen.base) & 0xFFFF
