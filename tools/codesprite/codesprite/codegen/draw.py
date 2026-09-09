"""Turn a :class:`~codesprite.ir.Plan` into draw instructions.

M3 implements the HL mode: navigate the pointer, then write each cell
with ``LD (HL),n`` when the sprite owns both pixels of the byte, or a
read-modify-write when it owns only one nibble:

    LD A,(HL) : AND keep : OR value : LD (HL),A      28T

``keep`` is the complement of the cell's mask, so the background nibble
survives.  Register caching, stack mode and IX mode arrive in M4.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..ir import Mode, Plan, Program, Reloc
from ..screen import Screen
from ..sprite import Cell, MASK_BOTH
from ..z80 import isa
from .navigate import Navigator


@dataclass
class DrawContext:
    """Where the sprite is being drawn and how the code finds it."""

    screen: Screen
    x: int = 0
    y: int = 0
    reloc: Reloc = Reloc.NONE

    def address(self, cell: Cell) -> int:
        """Absolute address of ``cell`` for this draw position."""
        return self.screen.addr_byte(self.y + cell.row, self.x // 2 + cell.col)


def write_cell(cell: Cell) -> list[isa.Op]:
    """Instructions writing one cell, assuming HL already points at it."""
    if cell.mask == MASK_BOTH:
        return [isa.LdHlImm(cell.value)]
    keep = (~cell.mask) & 0xFF
    ops: list[isa.Op] = [isa.LdRegHl("A"), isa.AluImm("AND", keep)]
    if cell.value:
        ops.append(isa.AluImm("OR", cell.value))
    ops.append(isa.LdHlReg("A"))
    return ops


def generate_draw(
    plan: Plan,
    context: DrawContext,
    *,
    patch_weight: float | None = None,
    entry_pointer: bool | None = None,
) -> Program:
    """Generate the body of a draw routine for ``plan``.

    ``entry_pointer`` says HL already holds the sprite's top-left address
    on entry (the register relocation and list-form contract); it defaults
    to true exactly when relocation is by register.
    """
    navigator = Navigator(
        context.reloc,
        **({"patch_weight": patch_weight} if patch_weight is not None else {}),
    )
    if entry_pointer is None:
        entry_pointer = context.reloc is Reloc.REGISTER

    program = Program()
    # With an entry pointer the generator knows HL's value symbolically: it
    # is the top-left address, which for code generation purposes is the
    # same arithmetic as the absolute address of cell (0, 0).
    current: int | None = context.screen.addr_byte(context.y, context.x // 2) if entry_pointer else None

    for piece in plan.pieces:
        if piece.mode is not Mode.HL:
            raise NotImplementedError(f"mode {piece.mode} arrives in M4")
        for cell in piece.ordered():
            target = context.address(cell)
            moves = navigator.move(current, target, cell.row, cell.col)
            program.extend(moves, (cell.row, cell.col))
            program.extend(write_cell(cell), (cell.row, cell.col))
            current = target
    return program
