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

# A stack run pays a one-off SP seating (10T) and needs a pair loaded (10T)
# to save 3T per byte against a cached HL write, so it only wins on runs of
# a few bytes.  Four is the shortest run that is clearly ahead once the pair
# is reused across rows.
STACK_MIN_RUN = 4


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


def choose_mode(piece: Piece, minimum_run: int = STACK_MIN_RUN) -> Mode:
    """Pick a write mode for one piece from its longest opaque run."""
    longest = current = 0
    previous_col: int | None = None
    for cell in piece.cells:
        if cell.opaque and (previous_col is None or cell.col == previous_col + 1):
            current += 1
        else:
            current = 1 if cell.opaque else 0
        previous_col = cell.col
        longest = max(longest, current)
    return Mode.STACK if longest >= minimum_run else Mode.HL


def baseline_plan(
    packed: PackedSprite,
    *,
    max_gap: int = 1,
    serpentine: bool = True,
    mode: Mode | str = Mode.HL,
    minimum_run: int = STACK_MIN_RUN,
) -> Plan:
    """Row-major plan; alternate rows are walked right to left.

    ``mode`` may be a fixed :class:`Mode` or ``"auto"``, which puts long
    opaque runs into stack mode and leaves the rest on HL writes.
    """
    auto = mode == "auto"
    pieces = build_pieces(packed, max_gap=max_gap, mode=Mode.HL if auto else mode)
    if auto:
        pieces = [p.with_mode(choose_mode(p, minimum_run)) for p in pieces]
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
