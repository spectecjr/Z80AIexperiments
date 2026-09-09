"""Saving and restoring what a sprite covers.

Three routines share one shape - the byte span each sprite row touches:

``save``       screen span  -> scratch, packed densely
``restore``    scratch      -> screen span
``restore_bb`` back buffer  -> screen span, at a fixed offset from the screen

The scratchpad is normally passed in DE, so each sprite instance owns its
own save area and one compiled routine serves them all; ``--scratch
fixed`` bakes a single address in instead.

The scratch layout is dense: row spans are concatenated in row order, so
the scratch pointer only ever runs forwards and never needs re-seating.
That is what makes ``LDI`` chains a good fit - 16T a byte with both
pointers auto-advancing.

The alternative is a stack bounce (``LD SP,src : POP × n : LD SP,dst :
PUSH × n``), which moves two bytes per 21T but pays two SP seatings per
group and needs interrupts off.  Both are generated and the cheaper is
kept; the bounce wins on long spans, the LDI chain on short ones.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..ir import Program, Reloc
from ..screen import Screen
from ..sprite import PackedSprite
from ..z80 import isa
from .draw import DrawContext
from .navigate import Navigator

# Pairs the bounce can carry two bytes in, cheapest first.
BOUNCE_PAIRS = ("BC", "DE", "HL", "AF", "IX", "IY")


@dataclass(frozen=True)
class Span:
    """One row's contiguous byte range, and where it lives in scratch."""

    row: int
    first_col: int
    length: int
    offset: int  # byte offset within the scratch area


def spans_of(packed: PackedSprite) -> list[Span]:
    """The byte span of each non-empty row, with dense scratch offsets."""
    out: list[Span] = []
    offset = 0
    for row in sorted(packed.rows()):
        cells = packed.rows()[row]
        first, last = cells[0].col, cells[-1].col
        length = last - first + 1
        out.append(Span(row, first, length, offset))
        offset += length
    return out


def scratch_size(packed: PackedSprite) -> int:
    """Bytes of scratch a save needs."""
    return sum(span.length for span in spans_of(packed))


def _ldi_chain(
    spans: list[Span],
    context: DrawContext,
    scratch_base: int,
    *,
    to_screen: bool,
    source_delta: int | None = None,
    scratch_in_de: bool = False,
) -> Program:
    """Copy each span with an unrolled LDI chain.

    ``LDI`` moves (HL) to (DE) and advances both, so the pointer that runs
    over dense scratch is seated once and the screen pointer is re-seated
    per row.  The screen side lives in HL (where the cheap row steps work)
    and is swapped into DE with ``EX DE,HL`` when the screen is the
    destination.
    """
    program = Program()
    navigator = Navigator(context.reloc)
    anchor = context.address_at(0, 0)
    screen_pointer: int | None = anchor if context.reloc is Reloc.REGISTER else None

    # Establish the non-screen pointer.  Its address is a fixed scratch
    # location, never a screen address, so loading it absolutely is allowed
    # even under register relocation - but with the anchor in HL it has to be
    # parked in DE first.
    if to_screen:
        screen_in_de = True
        if scratch_in_de:
            # Caller passed the scratchpad in DE (and, under register
            # relocation, the screen anchor in HL): one exchange puts the
            # source in HL and the destination in DE, which is what LDI wants.
            program.add(isa.Simple("EX DE,HL"))
        else:
            if context.reloc is Reloc.REGISTER:
                program.add(isa.Simple("EX DE,HL"))  # DE = anchor, HL free
            if source_delta is None:
                program.add(isa.LdPairImm("HL", scratch_base))
    else:
        screen_in_de = False
        if not scratch_in_de:
            program.add(isa.LdPairImm("DE", scratch_base))

    for span in spans:
        target = context.address_at(span.row, span.first_col)
        if screen_in_de:
            program.add(isa.Simple("EX DE,HL"), (span.row, span.first_col))
        moves = navigator.move(screen_pointer, target, span.row, span.first_col)
        program.extend(moves, (span.row, span.first_col))
        if screen_in_de:
            program.add(isa.Simple("EX DE,HL"), (span.row, span.first_col))
        if source_delta is not None:
            # restore_bb reads a clean copy of the screen a fixed distance
            # away, so the source is re-seated per row.
            source = (target + source_delta) & 0xFFFF
            program.add(
                isa.LdPairImm(
                    "HL",
                    source,
                    patch_lo=isa.Patch(isa.PatchKind.L, span.row, span.first_col)
                    if context.reloc is Reloc.PATCH
                    else None,
                    patch_hi=isa.Patch(isa.PatchKind.H, span.row, span.first_col)
                    if context.reloc is Reloc.PATCH
                    else None,
                ),
                (span.row, span.first_col),
            )
        program.extend([isa.Simple("LDI")] * span.length, (span.row, span.first_col))
        # LDI advances both pointers, so the screen side now sits just past
        # the span it copied - which is where the next row's move starts.
        screen_pointer = (target + span.length) & 0xFFFF

    return program


def _bounce(
    spans: list[Span],
    context: DrawContext,
    scratch_base: int,
    *,
    to_screen: bool,
    source_delta: int | None = None,
) -> Program:
    """Copy by popping from the source and pushing to the destination.

    Only whole pairs move this way, so an odd trailing byte is left to an
    LDI.  Interrupts must be off, since SP spends the routine pointing at
    the screen and the scratch area in turn.
    """
    program = Program()
    if context.interrupts == "di":
        program.add(isa.Simple("DI"))
    program.add(isa.LdMemSp(0, label=f"{context.label}_bounce_sp+1"))

    for span in spans:
        screen = context.address_at(span.row, span.first_col)
        scratch = scratch_base + span.offset
        if source_delta is not None:
            scratch = (screen + source_delta) & 0xFFFF
        source, destination = (
            (scratch, screen) if to_screen else (screen, scratch)
        )
        remaining = span.length
        while remaining >= 2:
            group = min(remaining // 2, len(BOUNCE_PAIRS))
            pairs = BOUNCE_PAIRS[:group]
            program.add(isa.LdSpImm(source), (span.row, span.first_col))
            for pair in pairs:
                program.add(isa.Pop(pair), (span.row, span.first_col))
            program.add(isa.LdSpImm(destination + group * 2), (span.row, span.first_col))
            for pair in reversed(pairs):
                program.add(isa.Push(pair), (span.row, span.first_col))
            source += group * 2
            destination += group * 2
            remaining -= group * 2
        if remaining:
            program.add(isa.LdPairImm("HL", source), (span.row, span.first_col))
            program.add(isa.LdRegHl("A"), (span.row, span.first_col))
            program.add(isa.LdPairImm("HL", destination), (span.row, span.first_col))
            program.add(isa.LdHlReg("A"), (span.row, span.first_col))

    program.add(isa.Label(f"{context.label}_bounce_sp"))
    program.add(isa.LdSpImm(0))
    if context.interrupts == "di":
        program.add(isa.Simple("EI"))
    return program


def generate_copy(
    packed: PackedSprite,
    context: DrawContext,
    scratch_base: int,
    *,
    to_screen: bool,
    source_delta: int | None = None,
    allow_bounce: bool = True,
    scratch_in_de: bool = False,
) -> Program:
    """Generate the cheaper of the two copy strategies.

    ``scratch_in_de`` takes the scratchpad address from DE at run time
    instead of baking one in, so every sprite instance can own its own
    save area.  It costs nothing - the pointer had to be loaded either
    way - and is what lets one compiled routine serve many instances.
    """
    spans = spans_of(packed)
    ldi = _ldi_chain(
        spans,
        context,
        scratch_base,
        to_screen=to_screen,
        source_delta=source_delta,
        scratch_in_de=scratch_in_de,
    )
    if scratch_in_de:
        # The bounce needs the scratch address as an immediate in LD SP,nn.
        return ldi
    if not context.allow_stack:
        return ldi  # the bounce moves data through SP
    if source_delta is not None and context.reloc is Reloc.REGISTER:
        raise ValueError(
            "restoring from a back buffer needs absolute source addresses; "
            "use --reloc none or patch"
        )
    if not allow_bounce or context.reloc is not Reloc.NONE:
        # The bounce needs absolute addresses for both sides at once, so it
        # is only available to fixed-position builds for now.
        return ldi
    bounce = _bounce(
        spans, context, scratch_base, to_screen=to_screen, source_delta=source_delta
    )
    return bounce if bounce.tstates < ldi.tstates else ldi
