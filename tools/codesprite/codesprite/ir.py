"""Intermediate representation between a packed sprite and Z80 code.

A :class:`Plan` says *in what order* and *by what means* the sprite's byte
cells are written; the code generator turns a plan into a :class:`Program`
of concrete instructions.  The optimiser only ever rearranges plans - it
never touches instructions - so any plan is correct by construction and
correctness is independent of the search.

Every emitted :class:`Op` keeps its ``(row, col)`` provenance in the
program's ``origins`` list, which is what later lets clipping schemes NOP
out or jump around individual rows and columns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .sprite import Cell, PackedSprite
from .z80 import isa


class Mode(str, Enum):
    """How a run of cells is written."""

    HL = "hl"  # LD (HL),n / LD (HL),r with pointer navigation
    STACK = "stack"  # PUSH rr, two bytes at a time, right to left
    IX = "ix"  # LD (IX+d),n for scattered cells


class Reloc(str, Enum):
    """How the draw position reaches the code."""

    NONE = "none"  # addresses baked in; sprite draws at one fixed place
    PATCH = "patch"  # self-modifying: setpos rewrites the immediates
    REGISTER = "register"  # caller passes the top-left address in HL


@dataclass(frozen=True)
class Piece:
    """A run of cells in one sprite row, written by one mode.

    ``cells`` is ordered left to right; ``reverse`` asks the generator to
    walk it right to left instead.  A piece may contain gaps (transparent
    bytes): crossing them costs pointer moves but no writes.
    """

    row: int
    cells: tuple[Cell, ...]
    mode: Mode = Mode.HL
    reverse: bool = False

    def __post_init__(self) -> None:
        if not self.cells:
            raise ValueError("a piece must contain at least one cell")
        if any(c.row != self.row for c in self.cells):
            raise ValueError("all cells in a piece must share a row")

    @property
    def first_col(self) -> int:
        return self.cells[0].col

    @property
    def last_col(self) -> int:
        return self.cells[-1].col

    def ordered(self) -> tuple[Cell, ...]:
        return tuple(reversed(self.cells)) if self.reverse else self.cells

    def with_mode(self, mode: Mode) -> "Piece":
        return Piece(self.row, self.cells, mode, self.reverse)

    def with_reverse(self, reverse: bool) -> "Piece":
        return Piece(self.row, self.cells, self.mode, reverse)


@dataclass(frozen=True)
class Plan:
    """An ordered list of pieces covering every cell of a packed sprite."""

    pieces: tuple[Piece, ...]

    def cells(self) -> tuple[Cell, ...]:
        return tuple(cell for piece in self.pieces for cell in piece.cells)

    def validate(self, packed: PackedSprite) -> None:
        """Check the plan writes every cell of ``packed`` exactly once."""
        planned = sorted((c.row, c.col) for c in self.cells())
        expected = sorted((c.row, c.col) for c in packed.cells)
        if planned != expected:
            missing = set(expected) - set(planned)
            extra = set(planned) - set(expected)
            raise ValueError(
                f"plan does not match sprite: {len(missing)} missing, {len(extra)} extra"
            )

    def key(self) -> tuple:
        """A hashable identity for memoising evaluation results."""
        return tuple(
            (p.row, p.mode, p.reverse, tuple((c.col, c.value, c.mask) for c in p.cells))
            for p in self.pieces
        )


@dataclass
class Program:
    """Generated instructions plus the bookkeeping the emitter needs."""

    ops: list[isa.Op] = field(default_factory=list)
    origins: list[tuple[int, int] | None] = field(default_factory=list)
    labels: dict[str, int] = field(default_factory=dict)

    def add(self, op: isa.Op, origin: tuple[int, int] | None = None) -> None:
        self.ops.append(op)
        self.origins.append(origin)

    def extend(self, ops: list[isa.Op], origin: tuple[int, int] | None = None) -> None:
        for op in ops:
            self.add(op, origin)

    @property
    def tstates(self) -> int:
        return sum(op.tstates for op in self.ops)

    @property
    def size(self) -> int:
        return sum(op.size for op in self.ops)

    @property
    def patch_count(self) -> int:
        return sum(len(op.patches) for op in self.ops)

    def assemble(self, origin: int = 0) -> tuple[bytes, dict[str, int]]:
        return isa.assemble(self.ops, origin)
