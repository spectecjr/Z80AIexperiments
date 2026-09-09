"""The always-available reference plan: row major, serpentine optional.

The baseline is instant, always correct, and is what the annealer starts
from and is measured against.  It groups each row's cells into runs of
adjacent byte columns (a gap of more than ``max_gap`` starts a new piece)
and walks rows top to bottom, reversing alternate rows when
``serpentine`` is set so the pointer does not have to jump back to the
left edge on every row.
"""

from __future__ import annotations

from ..ir import Mode, Piece, Plan
from ..sprite import PackedSprite


def build_pieces(
    packed: PackedSprite, *, max_gap: int = 1, mode: Mode = Mode.HL
) -> list[Piece]:
    """Split each row into runs of cells separated by at most ``max_gap``."""
    pieces: list[Piece] = []
    for row in sorted(packed.rows()):
        run: list = []
        previous_col: int | None = None
        for cell in packed.rows()[row]:
            if previous_col is not None and cell.col - previous_col - 1 > max_gap:
                pieces.append(Piece(row, tuple(run), mode))
                run = []
            run.append(cell)
            previous_col = cell.col
        if run:
            pieces.append(Piece(row, tuple(run), mode))
    return pieces


def baseline_plan(
    packed: PackedSprite,
    *,
    max_gap: int = 1,
    serpentine: bool = True,
    mode: Mode = Mode.HL,
) -> Plan:
    """Row-major plan; alternate rows are walked right to left."""
    pieces = build_pieces(packed, max_gap=max_gap, mode=mode)
    if serpentine:
        out = []
        for piece in pieces:
            reverse = piece.row % 2 == 1
            out.append(piece.with_reverse(reverse) if reverse else piece)
        # Within a reversed row the pieces themselves must also come in
        # right-to-left order.
        pieces = []
        by_row: dict[int, list] = {}
        for piece in out:
            by_row.setdefault(piece.row, []).append(piece)
        for row in sorted(by_row):
            row_pieces = by_row[row]
            if row % 2 == 1:
                row_pieces = list(reversed(row_pieces))
            pieces.extend(row_pieces)
    return Plan(tuple(pieces))
