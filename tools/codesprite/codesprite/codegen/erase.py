"""Erasing a sprite: draw it again in a single colour.

Erase is the draw generator applied to a recoloured copy of the sprite,
so it inherits stack mode, register caching and every relocation mode for
free.  Three shapes are available:

``cells``
    Exactly the bytes the sprite touches, with half-owned bytes still
    read-modify-written so the background nibble survives.  Leaves the
    least damage but costs the most on ragged sprites.

``rows``
    The full span from the sprite's leftmost to its rightmost byte in each
    row, all opaque.  Usually the fastest, because whole rows become long
    opaque runs that stack mode eats in pairs.

``bbox``
    The sprite's bounding box, every row from the top to the bottom of the
    sprite, all opaque.  Simplest to reason about when sprites overlap.
"""

from __future__ import annotations

from ..sprite import MASK_BOTH, Cell, PackedSprite

SHAPES = ("cells", "rows", "bbox")


def erase_sprite(packed: PackedSprite, colour: int, shape: str = "rows") -> PackedSprite:
    """Build the monochrome sprite whose draw erases ``packed``."""
    if shape not in SHAPES:
        raise ValueError(f"erase shape must be one of {SHAPES}, not {shape!r}")
    if not 0 <= colour <= 15:
        raise ValueError(f"erase colour {colour} is not a 4-bit index")
    both = (colour << 4) | colour

    cells: list[Cell] = []
    if shape == "cells":
        for cell in packed.cells:
            value = both & cell.mask
            cells.append(Cell(cell.row, cell.col, value, cell.mask))
    else:
        rows = packed.rows()
        if shape == "bbox":
            columns = [c.col for c in packed.cells]
            low, high = min(columns), max(columns)
            spans = {row: (low, high) for row in range(packed.height)}
        else:
            spans = {}
            for row, row_cells in rows.items():
                spans[row] = (row_cells[0].col, row_cells[-1].col)
        for row in sorted(spans):
            low, high = spans[row]
            for col in range(low, high + 1):
                cells.append(Cell(row, col, both, MASK_BOTH))

    return PackedSprite(
        phase=packed.phase,
        byte_width=packed.byte_width,
        height=packed.height,
        cells=tuple(cells),
    )
