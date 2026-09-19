"""Single and list forms of a compiled routine.

The *single* form is a plain subroutine: set the position, call it once.

The *list* form draws the same sprite at many places - tiles, repeated
enemies, a status bar - paying the register setup once.  The addresses
travel on the stack, which is the cheapest list the Z80 has:

    caller pushes the return address, then the item addresses last-first,
    sets B to the item count and jumps to the routine

    loop:   POP HL              ; 10T - next screen address
            [LD (.sp+1),SP]     ; 20T - only if the body writes via SP
            <body>
    .sp:    [LD SP,0]           ; 10T - back to the item list
            DJNZ loop           ; 13T (or DEC B : JP NZ for a long body)
            RET                 ; lands on the caller's return address

so an HL-only body costs 23T per item and a stack-writing body 53T.

Loop-invariant loads are hoisted by generating the body repeatedly until
the machine state it starts from equals the state it ends in.  At that
fixed point the body neither needs nor destroys anything the previous
iteration left, so identical tiles load their push pairs exactly once and
``T(item)`` in the size table is the true marginal cost of one more item.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..ir import Plan, Program, Reloc
from ..z80 import isa
from .draw import DrawContext, DrawGenerator
from .state import BYTE_REGISTERS, PAIR_HALVES, MachineState

# DJNZ reaches -126 bytes; leave room for the loop's own tail.
DJNZ_REACH = 120
MAX_FIXED_POINT_PASSES = 4


@dataclass
class ListProgram:
    """A list-form routine, split so the size table can report both parts."""

    program: Program
    prologue_tstates: int
    item_tstates: int
    body_tstates: int

    @property
    def tstates(self) -> int:
        return self.program.tstates

    @property
    def size(self) -> int:
        return self.program.size


def _state_loads(state: MachineState) -> list[isa.Op]:
    """Instructions that establish ``state`` from an unknown machine.

    Pairs are loaded whole where both halves are known, so a push value
    costs one ``LD rr,nn`` rather than two byte loads.
    """
    ops: list[isa.Op] = []
    for bank, exx in ((state.main, False), (state.alt, True)):
        bank_ops: list[isa.Op] = []
        done: set[str] = set()
        for pair in ("BC", "DE", "HL"):
            high, low = PAIR_HALVES[pair]
            if bank.get(high) is not None and bank.get(low) is not None:
                bank_ops.append(
                    isa.LdPairImm(pair, (bank[high] << 8) | bank[low])
                )
                done.update((high, low))
        for reg in BYTE_REGISTERS:
            if reg in done or reg in ("A", "B"):
                continue
            value = bank.get(reg) if reg in bank else None
            if value is not None:
                bank_ops.append(isa.LdRegImm(reg, value))
        if bank_ops and exx:
            ops.append(isa.Simple("EXX"))
            ops.extend(bank_ops)
            ops.append(isa.Simple("EXX"))
        else:
            ops.extend(bank_ops)
    return ops


def _entry_state(final: MachineState) -> MachineState:
    """The state to start an iteration in, given where the last one ended.

    HL is excluded: the loop reloads it from the list every time, so a
    belief about it must not be carried across iterations.
    """
    state = final.copy()
    state.exx = False
    for bank in (state.main, state.alt):
        bank["H"] = None
        bank["L"] = None
        bank["A"] = None
    state.pointer = None
    state.sp = None
    return state


def generate_list(
    plan: Plan,
    context: DrawContext,
    *,
    label: str,
    use_alternate: bool = True,
    **kwargs,
) -> ListProgram:
    """Build the list form of ``plan``.

    The body is generated with register relocation, since every item has a
    different address and there is nothing to patch.
    """
    if context.reloc is not Reloc.REGISTER:
        raise ValueError("the list form needs --reloc register")

    # Fixed point: keep feeding the body the state the previous pass ended
    # in until the code stops changing.
    entry = MachineState()
    body = None
    for _pass in range(MAX_FIXED_POINT_PASSES):
        generator = DrawGenerator(
            plan,
            context,
            entry_pointer=True,
            use_alternate=use_alternate,
            initial_state=entry,
            manage_sp=False,
            reserved=frozenset({"B"}),
            **kwargs,
        )
        candidate = generator.generate()
        next_entry = _entry_state(generator.state)
        if body is not None and [op.text() for op in candidate.ops] == [
            op.text() for op in body.ops
        ]:
            break
        body, entry = candidate, next_entry
    assert body is not None

    uses_stack = any(isinstance(op, isa.Push) for op in body.ops)
    loop_label = f"{label}_loop"
    sp_label = f"{label}_splist"

    program = Program()
    if uses_stack and context.interrupts == "di":
        program.add(isa.Simple("DI"))
    prologue_loads = _state_loads(entry)
    program.extend(prologue_loads)
    prologue_tstates = program.tstates

    program.add(isa.Label(loop_label))
    item_start = program.tstates
    program.add(isa.Pop("HL"))
    if uses_stack:
        program.add(isa.LdMemSp(0, label=f"{sp_label}+1"))
    program.ops.extend(body.ops)
    program.origins.extend(body.origins)
    if uses_stack:
        program.add(isa.Label(sp_label))
        program.add(isa.LdSpImm(0))

    # DJNZ only reaches a short body; a longer one counts down explicitly.
    body_bytes = sum(op.size for op in program.ops) - sum(
        op.size for op in prologue_loads
    )
    if body_bytes <= DJNZ_REACH:
        program.add(isa.Djnz(loop_label))
    else:
        program.add(isa.IncDec8("B", down=True))
        program.add(isa.JumpCond("NZ", loop_label))
    item_tstates = program.tstates - item_start

    if uses_stack and context.interrupts == "di":
        program.add(isa.Simple("EI"))
    return ListProgram(
        program=program,
        prologue_tstates=prologue_tstates,
        item_tstates=item_tstates,
        body_tstates=body.tstates,
    )
