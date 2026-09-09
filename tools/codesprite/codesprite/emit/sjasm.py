"""Render generated programs as an sjasmplus source file.

One file per variant, self-contained, so a project can ``INCLUDE`` exactly
the variants it uses.  A file holds one or more routines - a draw body and,
for patched builds, its position patcher - sharing the file's local labels,
so a patch site is named symbolically (``.p0+1`` is the immediate byte of
the instruction labelled ``.p0``) rather than by address.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field

from ..ir import Program
from ..z80 import isa

# Instructions that read or write through the stack pointer.  A routine
# containing none of these leaves SP alone and is safe to run with
# interrupts enabled.
STACK_OPS = (isa.Push, isa.Pop, isa.LdSpImm, isa.LdSpPair, isa.LdMemSp)


def uses_stack(program: Program) -> bool:
    """Does this routine write through SP (and so need interrupts off)?"""
    return any(isinstance(op, STACK_OPS) for op in program.ops)

INDENT = " " * 16


@dataclass
class ModuleInfo:
    """Everything the file header and metadata EQUs need."""

    name: str
    routine: str
    width: int
    height: int
    cells: int
    phase: int
    parity: int | None = None
    form: str = "single"
    reloc: str = "none"
    clip: str = "none"
    command_line: str = ""
    source: str = ""
    source_hash: str = ""
    palette: list[tuple[int, int, int]] | None = None
    lower_bound: int | None = None
    compiled_at: tuple[int, int] | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        """Fully qualified label stem, e.g. ``spr_ship_draw_single_xe_ye``."""
        bits = [self.name, self.routine, self.form, "xo" if self.phase else "xe"]
        if self.parity is not None:
            bits.append("yo" if self.parity else "ye")
        return "_".join(bits)


def _entry_contract(info: ModuleInfo) -> list[str]:
    """The register contract a caller has to honour, as comment lines."""
    if info.reloc == "register":
        return [
            "Entry: HL = address of the sprite's top-left screen byte.",
            f"       The routine assumes x is {'odd' if info.phase else 'even'}"
            + (
                f" and y is {'odd' if info.parity else 'even'}."
                if info.parity is not None
                else "."
            ),
        ]
    if info.reloc == "patch":
        return [
            "Call setpos first, then the draw routine.",
            "Entry to setpos: C = (y&1)*128 + x/2      (even sprite rows)",
            "                 B = ((y&1)^1)*128 + x/2  (odd sprite rows)",
            "                 D = screen_high + (y>>1)",
            f"       Valid for x {'odd' if info.phase else 'even'}"
            + (
                f" and y {'odd' if info.parity else 'even'} only."
                if info.parity is not None
                else "."
            ),
        ]
    at = info.compiled_at or (0, 0)
    return [f"Fixed position: draws at x={at[0]}, y={at[1]}.  No entry values."]


def render(
    program: Program,
    info: ModuleInfo,
    *,
    setpos: Program | None = None,
    setpos_tstates: int | None = None,
) -> str:
    """Produce the text of one sjasmplus module."""
    lines: list[str] = []
    add = lines.append

    add(";" + "-" * 71)
    add(f"; {info.label}")
    add(";")
    for line in textwrap.wrap(
        f"Compiled sprite for SAM Coupe mode 4: {info.width}x{info.height} pixels, "
        f"{info.cells} screen bytes touched, x phase {info.phase}"
        + (f", y parity {info.parity}" if info.parity is not None else "")
        + f", form {info.form}, relocation {info.reloc}, clipping {info.clip}.",
        72,
    ):
        add(f"; {line}")
    add(";")
    for line in _entry_contract(info):
        add(f"; {line}")
    add(";")
    add(f"; Cost   : {program.tstates}T (nominal Z80 timing)")
    if setpos is not None:
        add(f"; Setpos : {setpos.tstates}T, {setpos.size} bytes")
    add(f"; Size   : {program.size} bytes")
    add(f"; Patches: {program.patch_count}")
    if info.lower_bound:
        gap = 100.0 * (program.tstates - info.lower_bound) / info.lower_bound
        add(f"; Bound  : {info.lower_bound}T lower bound ({gap:+.0f}%)")
    if uses_stack(program):
        guarded = any(op.text() == "DI" for op in program.ops)
        add("; Stack  : WRITES THROUGH SP.  Interrupts must be off for the")
        if guarded:
            add(";          duration; this routine disables them itself and")
            add(";          restores SP before returning.")
        else:
            add(";          duration - the CALLER must have done DI already.")
            add(";          SP is saved and restored by the routine itself.")
    else:
        add("; Stack  : does not touch SP; safe with interrupts enabled.")
    for note in info.notes:
        add(f"; Note   : {note}")
    if info.source:
        add(
            f"; Source : {info.source}"
            + (f" ({info.source_hash})" if info.source_hash else "")
        )
    if info.command_line:
        for line in textwrap.wrap(f"Command: {info.command_line}", 70):
            add(f"; {line}")
    add("; Generated by codesprite - do not edit by hand.")
    add(";" + "-" * 71)
    add("")

    if info.palette:
        add(f"{info.label}_palette_rgb:")
        for index, (r, g, b) in enumerate(info.palette):
            add(f"{INDENT}DEFB {r},{g},{b}{' ' * 8}; index {index}")
        add("")

    add(_render_routine(info.label, program))
    if setpos is not None and setpos.ops:
        add(_render_routine(f"{info.label}_setpos", setpos))

    add(f"{info.label}_w{' ' * 8}EQU {info.width}")
    add(f"{info.label}_h{' ' * 8}EQU {info.height}")
    add(f"{info.label}_bytes{' ' * 4}EQU {info.cells}")
    add(f"{info.label}_tstates  EQU {program.tstates}")
    add(f"{info.label}_size{' ' * 5}EQU {program.size}")
    add(f"{info.label}_patches  EQU {program.patch_count}")
    add(
        f"{info.label}_uses_stack EQU {1 if uses_stack(program) else 0}"
        "   ; 1 = needs interrupts off"
    )
    if setpos is not None and setpos.ops:
        add(f"{info.label}_setpos_tstates EQU {setpos.tstates}")
    add("")
    return "\n".join(lines)


def _render_routine(label: str, program: Program) -> str:
    lines = [f"{label}:"]
    for op, origin in zip(program.ops, program.origins):
        if isinstance(op, isa.Comment):
            lines.append(f"{INDENT}{op.text()}")
            continue
        if isinstance(op, isa.Label):
            lines.append(f"{op.name}:")
            continue
        comment = f"; ({origin[0]},{origin[1]})" if origin is not None else ""
        lines.append(f"{INDENT}{op.text():<24}{comment}".rstrip())
    lines.append(f"{INDENT}RET")
    lines.append("")
    return "\n".join(lines)
