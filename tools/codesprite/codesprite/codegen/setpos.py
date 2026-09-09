"""The position patcher for ``--reloc patch`` builds.

A patched draw routine has the sprite's addresses baked into its
immediates; ``setpos`` rewrites them for a new (x, y) before the routine
runs.  Only three runtime values are needed, because of how a mode 4
address decomposes for a sprite drawn at (x, y) with ``p = y & 1``:

    sprite row r sits on screen row y + r
    low  byte = ((y + r) & 1) * 128 + x/2 + col
    high byte = baseH + ((y + r) >> 1)

Each variant is generated for one y parity, so ``p`` is a compile-time
constant and both parts split into "a register the caller loads" plus "a
constant this site adds":

    C = p * 128 + x/2          low byte source for even sprite rows
    B = (1 - p) * 128 + x/2    low byte source for odd sprite rows
    D = baseH + (y >> 1)       high byte source for every row

    low  byte at (r, col) = (C if r even else B) + col
    high byte at (r, col) = D + (r + p) // 2

A sprite row spans at most 128 bytes, so adding ``col`` never carries out
of the low byte, and the two low-byte registers differ only in bit 7 -
which is exactly the row-parity bit the address layout puts there.

Sites are emitted sorted by (source register, constant) so consecutive
patches sharing both cost a bare ``LD (nn),A`` (13T) with no reload.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..ir import Program
from ..z80 import isa

PATCH_LABEL_PREFIX = ".p"


@dataclass(frozen=True)
class PatchSite:
    """One immediate byte that setpos has to rewrite."""

    label: str  # label of the instruction carrying the immediate
    offset: int  # byte offset of the immediate within that instruction
    kind: isa.PatchKind
    row: int  # sprite row whose address this is
    col: int  # byte column within the sprite

    def source(self, parity: int) -> str:
        """Which register the caller loads this byte's base value into."""
        if self.kind is isa.PatchKind.H:
            return "D"
        return "C" if self.row % 2 == 0 else "B"

    def constant(self, parity: int) -> int:
        """What this site adds to its source register."""
        if self.kind is isa.PatchKind.H:
            return (self.row + parity) // 2
        return self.col


def collect_sites(program: Program) -> list[PatchSite]:
    """Find every patchable immediate, naming its instruction ``.pN``.

    The numbering matches the labels the emitter writes, so the patcher
    and the emitted source always agree.
    """
    sites: list[PatchSite] = []
    index = 0
    for op in program.ops:
        if not op.patches:
            continue
        label = f"{PATCH_LABEL_PREFIX}{index}"
        index += 1
        for patch in op.patches:
            sites.append(
                PatchSite(label, patch.offset, patch.kind, patch.row, patch.col)
            )
    return sites


def label_patch_sites(program: Program) -> Program:
    """Return a copy of ``program`` with a label before each patched op."""
    out = Program()
    index = 0
    for op, origin in zip(program.ops, program.origins):
        if op.patches:
            out.add(isa.Label(f"{PATCH_LABEL_PREFIX}{index}"), origin)
            index += 1
        out.add(op, origin)
    return out


def generate_setpos(sites: list[PatchSite], parity: int = 0) -> Program:
    """Emit the unrolled patcher for ``sites``.

    Entry: B, C and D hold the values described in the module docstring
    for the wanted position; the y parity must match the variant this
    routine was generated for.
    Exit : every patch site holds the byte for that position.
    """
    program = Program()
    if not sites:
        return program

    ordered = sorted(
        sites, key=lambda s: (s.source(parity), s.constant(parity), s.label)
    )
    current: tuple[str, int] | None = None

    for site in ordered:
        source, constant = site.source(parity), site.constant(parity)
        if current != (source, constant):
            program.add(isa.LdRegReg("A", source), (site.row, site.col))
            if constant:
                program.add(isa.AluImm("ADD", constant), (site.row, site.col))
            current = (source, constant)
        program.add(
            isa.LdMemA(0, label=f"{site.label}+{site.offset}"), (site.row, site.col)
        )
    return program


def setpos_registers(x: int, y: int, screen_base: int) -> dict[str, int]:
    """The B, C, D values a caller must load to draw at (x, y)."""
    parity = y & 1
    return {
        "c": parity * 0x80 + x // 2,
        "b": (1 - parity) * 0x80 + x // 2,
        "d": ((screen_base >> 8) + (y >> 1)) & 0xFF,
    }
