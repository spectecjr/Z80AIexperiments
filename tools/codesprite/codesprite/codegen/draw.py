"""Turn a :class:`~codesprite.ir.Plan` into draw instructions.

Three ways of writing a cell are available, and the plan says which one a
run of cells uses:

``Mode.HL``
    Navigate the pointer and write with ``LD (HL),n`` (10T) or
    ``LD (HL),r`` (7T) when the byte is register-cached.  Cells the sprite
    only half owns get a read-modify-write.

``Mode.STACK``
    Point SP just past the run and ``PUSH`` pairs into it, right to left:
    two bytes for 11T, the fastest write the Z80 has.  Runs must be
    adjacent and fully opaque; anything else in the piece falls back to
    HL writes.  SP is saved and restored around the routine, and the
    section needs interrupts off; by default the caller is assumed to have
    seen to that, since a batch of sprites wants one DI/EI around the lot.
    ``DrawContext.allow_stack = False`` forbids this mode outright, and the
    routine then never touches SP.

``Mode.IX``
    ``LD (IX+d),n`` (19T) for scattered cells, since one IX seating
    covers two whole rows without disturbing HL or SP.

Register policy (M4): when a plan contains stack runs the pairs BC/DE
(plus HL when it is not the anchor pointer) and their alternates hold
push values; otherwise B/C/D/E cache repeated pixel bytes.  A is always
scratch for read-modify-write.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..ir import Mode, Piece, Plan, Program, Reloc
from ..screen import Screen
from ..sprite import Cell, MASK_BOTH
from ..z80 import isa
from .navigate import Navigator
from .regalloc import EXX_COST, LOAD_PAIR_COST, ByteCache, PairCache
from .state import PAIR_HALVES, MachineState


@dataclass
class DrawContext:
    """Where the sprite is drawn and how the code finds the address."""

    screen: Screen
    x: int = 0
    y: int = 0
    reloc: Reloc = Reloc.NONE
    # Who guards a stack-writing section against interrupts:
    #   "caller" - nothing is emitted; the caller has interrupts off already
    #              (the usual case, where a whole batch of sprites is drawn
    #              between one DI and one EI)
    #   "di"     - the routine disables and re-enables them itself
    interrupts: str = "caller"
    # False forbids writing through SP entirely, so the routine leaves SP
    # untouched and is safe to run with interrupts enabled.
    allow_stack: bool = True
    label: str = "sprite"  # label stem, for self-modifying operands

    def address(self, cell: Cell) -> int:
        return self.screen.addr_byte(self.y + cell.row, self.x // 2 + cell.col)

    def address_at(self, row: int, col: int) -> int:
        return self.screen.addr_byte(self.y + row, self.x // 2 + col)


def _runs(cells: tuple[Cell, ...]) -> list[list[Cell]]:
    """Split cells (left to right) into maximal adjacent opaque runs.

    Non-opaque cells and column gaps break a run; they are returned as
    single-cell runs so the caller can write them another way.
    """
    out: list[list[Cell]] = []
    current: list[Cell] = []
    for cell in cells:
        if not cell.opaque:
            if current:
                out.append(current)
                current = []
            out.append([cell])
            continue
        if current and cell.col == current[-1].col + 1:
            current.append(cell)
        else:
            if current:
                out.append(current)
            current = [cell]
    if current:
        out.append(current)
    return out


def write_cell(cell: Cell, state: MachineState, cache: ByteCache | None) -> list[isa.Op]:
    """Write one cell through HL, using a cached register when possible."""
    if cell.mask == MASK_BOTH:
        if cache is not None:
            reg = cache.find(state, cell.value)
            if reg is not None:
                return [isa.LdHlReg(reg)]
        return [isa.LdHlImm(cell.value)]
    keep = (~cell.mask) & 0xFF
    ops: list[isa.Op] = [isa.LdRegHl("A"), isa.AluImm("AND", keep)]
    if cell.value:
        ops.append(isa.AluImm("OR", cell.value))
    ops.append(isa.LdHlReg("A"))
    return ops


class DrawGenerator:
    """Generates the body of a draw routine from a plan."""

    def __init__(
        self,
        plan: Plan,
        context: DrawContext,
        *,
        patch_weight: float | None = None,
        entry_pointer: bool | None = None,
        use_alternate: bool = True,
        initial_state: MachineState | None = None,
        manage_sp: bool = True,
        reserved: frozenset[str] = frozenset(),
    ) -> None:
        self.plan = plan
        self.context = context
        self.navigator = Navigator(
            context.reloc,
            **({"patch_weight": patch_weight} if patch_weight is not None else {}),
        )
        self.entry_pointer = (
            context.reloc is Reloc.REGISTER if entry_pointer is None else entry_pointer
        )
        self.state = initial_state.copy() if initial_state else MachineState()
        self.manage_sp = manage_sp
        self.program = Program()
        wants_stack = any(p.mode is Mode.STACK for p in plan.pieces)
        if wants_stack and not context.allow_stack:
            raise ValueError(
                "this plan writes through SP but the context forbids it; "
                "generate with a non-stack mode instead"
            )
        self.uses_stack = wants_stack
        # HL doubles as a data pair only when addresses are baked in.  With
        # register or patch relocation it is the anchor the code navigates
        # from, and seating SP through it is what keeps row steps patch-free.
        hl_is_data = context.reloc is Reloc.NONE and not self.entry_pointer
        pairs = ("BC", "DE", "HL") if hl_is_data else ("BC", "DE")
        # A register the caller owns - the list form's loop counter in B -
        # must not be handed to a cache, and neither must the pair it sits in.
        self.reserved = reserved
        if reserved:
            pairs = tuple(
                pair
                for pair in pairs
                if not set(PAIR_HALVES[pair]) & reserved
            )
        # EXX swaps HL as well as BC and DE, so a routine that navigates from
        # a caller-supplied anchor cannot reach the alternate bank without
        # losing that anchor.  Register relocation therefore gives up the
        # alternate pairs.  (Keeping a copy of the anchor in HL' would buy
        # them back; that is a later refinement, not a correctness issue.)
        if self.entry_pointer:
            use_alternate = False
        if not pairs:
            raise ValueError("no register pair is free for stack writes")
        self.pair_cache = PairCache(pairs=pairs, use_alternate=use_alternate)
        byte_pool = tuple(r for r in ("B", "C", "D", "E") if r not in reserved)
        self.byte_cache = (
            None if self.uses_stack or not byte_pool else ByteCache(registers=byte_pool)
        )
        self.sp_label = f"{context.label}_sprestore"

    # -- helpers -----------------------------------------------------------
    def emit(self, ops: list[isa.Op], origin: tuple[int, int] | None = None) -> None:
        self.program.extend(ops, origin)

    def move_pointer(self, target: int, row: int, col: int) -> None:
        ops = self.navigator.move(self.state.pointer, target, row, col)
        self.emit(ops, (row, col))
        self.state.set_pointer(target)

    # -- planning ----------------------------------------------------------
    def _pair_values(self) -> list[int]:
        """Every 16-bit push value, in the order the pushes will happen."""
        values: list[int] = []
        for piece in self.plan.pieces:
            if piece.mode is not Mode.STACK:
                continue
            for run in _runs(piece.cells):
                if len(run) < 2 or not all(c.opaque for c in run):
                    continue
                pairs = len(run) // 2
                for index in range(pairs):
                    high = run[len(run) - 1 - index * 2]
                    low = run[len(run) - 2 - index * 2]
                    values.append((high.value << 8) | low.value)
        return values

    def _byte_values(self) -> list[int]:
        values: list[int] = []
        for piece in self.plan.pieces:
            if piece.mode is Mode.STACK:
                continue
            for cell in piece.ordered():
                if cell.opaque:
                    values.append(cell.value)
        return values

    # -- generation --------------------------------------------------------
    def generate(self) -> Program:
        if self.byte_cache is not None:
            self.byte_cache.future = self._byte_values()
        self.pair_cache.future = self._pair_values()

        if self.entry_pointer:
            self.state.set_pointer(self.context.address_at(0, 0))

        if self.uses_stack and self.manage_sp:
            self.emit_stack_prologue()

        if self.context.reloc is Reloc.PATCH and self.state.pointer is None:
            # Anchor HL once, with the routine's only two patch points, so
            # every later move - including seating SP for a stack run - is
            # relative and needs no patching at all.
            anchor = self.context.address_at(0, 0)
            self.emit(
                [
                    isa.LdPairImm(
                        "HL",
                        anchor,
                        patch_lo=isa.Patch(isa.PatchKind.L, 0, 0),
                        patch_hi=isa.Patch(isa.PatchKind.H, 0, 0),
                    )
                ],
                (0, 0),
            )
            self.state.set_pointer(anchor)

        for piece in self.plan.pieces:
            if piece.mode is Mode.HL:
                self.generate_hl(piece)
            elif piece.mode is Mode.STACK:
                self.generate_stack(piece)
            elif piece.mode is Mode.IX:
                self.generate_ix(piece)
            else:  # pragma: no cover - Mode is exhaustive
                raise NotImplementedError(piece.mode)

        if self.uses_stack and self.manage_sp:
            self.emit_stack_epilogue()
        return self.program

    def emit_stack_prologue(self) -> None:
        if self.context.interrupts == "di":
            self.emit([isa.Simple("DI")])
        # Save the caller's SP into the operand of the restoring LD SP,nn.
        self.emit([isa.LdMemSp(0, label=f"{self.sp_label}+1")])

    def emit_stack_epilogue(self) -> None:
        self.program.add(isa.Label(self.sp_label))
        self.emit([isa.LdSpImm(0)])
        if self.context.interrupts == "di":
            self.emit([isa.Simple("EI")])
        self.state.sp = None

    def generate_hl(self, piece: Piece) -> None:
        for cell in piece.ordered():
            target = self.context.address(cell)
            self.move_pointer(target, cell.row, cell.col)
            self.emit_byte_write(cell)

    def emit_byte_write(self, cell: Cell) -> None:
        cache = self.byte_cache
        if cache is not None and cell.opaque:
            position = cache.position
            reg = cache.find(self.state, cell.value)
            if reg is None and cache.should_admit(self.state, cell.value, position):
                victim = cache.choose_victim(self.state, position)
                self.emit([isa.LdRegImm(victim, cell.value)], (cell.row, cell.col))
                self.state.set(victim, cell.value)
            cache.position = position + 1
        ops = write_cell(cell, self.state, cache)
        self.emit(ops, (cell.row, cell.col))
        if not cell.opaque:
            self.state.set("A", None)

    def generate_stack(self, piece: Piece) -> None:
        """Write a piece with PUSH, falling back to HL for what cannot be."""
        for run in _runs(piece.cells):
            if len(run) >= 2 and all(c.opaque for c in run):
                self.emit_stack_run(run)
                if len(run) % 2:
                    # The leftmost byte of an odd run has no partner.
                    self.emit_hl_cell(run[0])
            else:
                for cell in run:
                    self.emit_hl_cell(cell)

    def emit_hl_cell(self, cell: Cell) -> None:
        target = self.context.address(cell)
        self.move_pointer(target, cell.row, cell.col)
        self.emit_byte_write(cell)

    def emit_stack_run(self, run: list[Cell]) -> None:
        """PUSH pairs into ``run``, right to left."""
        pairs = len(run) // 2
        last = run[-1]
        # SP must point one byte past the last cell: PUSH writes below SP.
        # That byte belongs to the next column, or to column 0 of the next
        # screen row when the run ends at the right-hand edge - and the patcher
        # decomposes an address by (row parity, column), so say which it is.
        seat_row, seat_col = last.row, last.col + 1
        if self.context.x // 2 + seat_col > 127:
            seat_row, seat_col = seat_row + 1, 0
        seat = self.context.address_at(last.row, last.col) + 1
        self.seat_sp(seat, seat_row, seat_col)

        for index in range(pairs):
            high = run[len(run) - 1 - index * 2]
            low = run[len(run) - 2 - index * 2]
            value = (high.value << 8) | low.value
            slot = self.acquire_pair(value)
            self.emit([isa.Push(slot)], (high.row, high.col))
            self.pair_cache.position += 1
            self.state.sp = (self.state.sp - 2) & 0xFFFF if self.state.sp is not None else None

    def seat_sp(self, address: int, row: int, col: int) -> None:
        """Point SP at ``address`` as cheaply as the relocation mode allows.

        Two routes exist: an absolute ``LD SP,nn`` (10T but two patch
        points), or walking HL there and copying it (``LD SP,HL``, 6T, and
        HL navigation is patch-free).  With addresses baked in the absolute
        form wins; under patching the HL route is far cheaper, which is why
        HL stops being a data pair in that mode.
        """
        if self.state.sp == address:
            return
        via_hl = None
        if self.state.pointer is not None:
            moves = self.navigator.move(self.state.pointer, address, row, col)
            via_hl = sum(op.tstates for op in moves) + isa.LdSpPair("HL").tstates
            via_hl += self.navigator.patch_weight * sum(len(m.patches) for m in moves)

        if self.context.reloc is Reloc.REGISTER:
            self.move_pointer(address, row, col)
            self.emit([isa.LdSpPair("HL")], (row, col))
            self.state.sp = address
            return

        patching = self.context.reloc is Reloc.PATCH
        absolute = isa.LdSpImm(
            address,
            patch_lo=isa.Patch(isa.PatchKind.L, row, col) if patching else None,
            patch_hi=isa.Patch(isa.PatchKind.H, row, col) if patching else None,
        )
        absolute_cost = absolute.tstates + self.navigator.patch_weight * len(
            absolute.patches
        )
        if via_hl is not None and via_hl < absolute_cost:
            self.move_pointer(address, row, col)
            self.emit([isa.LdSpPair("HL")], (row, col))
        else:
            self.emit([absolute], (row, col))
        self.state.sp = address

    def acquire_pair(self, value: int) -> str:
        """Ensure some pair holds ``value``, emitting loads/EXX as needed.

        Four ways to get there are costed against each other: it is already
        in this bank (free); it is in the other bank (one EXX, 4T); load it
        here; or switch banks and load it there.  Evicting a value that is
        needed again is charged the reload it will cost (10T), which is what
        makes the six pairs across both banks worth using: with four live
        push values, an EXX beats a reload every time.
        """
        cache = self.pair_cache
        position = cache.position

        for pair in cache.pairs:  # already here
            if self.state.get_pair(pair) == value:
                return pair

        options: list[tuple[float, bool, str]] = []  # (cost, switch bank, pair)

        victim = cache.choose_victim(self.state, position)
        here_cost = sum(op.tstates for op in cache.load_ops(victim, value, self.state))
        held = self.state.get_pair(victim)
        if held is not None and cache.next_use(held, position) <= len(cache.future):
            here_cost += LOAD_PAIR_COST  # it will have to come back
        options.append((here_cost, False, victim))

        if cache.use_alternate:
            probe = self.state.copy()
            probe.toggle_exx()
            for pair in cache.pairs:
                if probe.get_pair(pair) == value:
                    options.append((EXX_COST, True, pair))
                    break
            else:
                other = cache.choose_victim(probe, position)
                cost = EXX_COST + sum(
                    op.tstates for op in cache.load_ops(other, value, probe)
                )
                other_held = probe.get_pair(other)
                if other_held is not None and cache.next_use(
                    other_held, position
                ) <= len(cache.future):
                    cost += LOAD_PAIR_COST
                options.append((cost, True, other))

        _cost, switch, pair = min(options, key=lambda option: option[0])
        if switch:
            self.emit([isa.Simple("EXX")])
            self.state.toggle_exx()
        if self.state.get_pair(pair) != value:
            self.emit(cache.load_ops(pair, value, self.state))
            self.state.set_pair(pair, value)
            if pair == "HL":
                self.state.pointer = value  # HL now holds data, not a pointer
        return pair

    def generate_ix(self, piece: Piece) -> None:
        """Write scattered cells through IX, which spans two rows at a time."""
        for cell in piece.ordered():
            target = self.context.address(cell)
            base = self.state.index["IX"]
            if base is None or not -128 <= target - base <= 127:
                base = self.context.address_at(cell.row, 0)
                # The seat holds a screen address, so it needs patch points
                # like any other; the displacements stay valid because they
                # are relative to it.
                patching = self.context.reloc is Reloc.PATCH
                self.emit(
                    [
                        isa.LdPairImm(
                            "IX",
                            base,
                            patch_lo=isa.Patch(isa.PatchKind.L, cell.row, 0)
                            if patching
                            else None,
                            patch_hi=isa.Patch(isa.PatchKind.H, cell.row, 0)
                            if patching
                            else None,
                        )
                    ],
                    (cell.row, cell.col),
                )
                self.state.index["IX"] = base
            if cell.opaque:
                self.emit(
                    [isa.LdIndexImm("IX", target - base, cell.value)],
                    (cell.row, cell.col),
                )
            else:
                # Read-modify-write without disturbing HL: both halves of the
                # access go through (IX+d).
                keep = (~cell.mask) & 0xFF
                ops: list[isa.Op] = [
                    isa.LdRegIndex("A", "IX", target - base),
                    isa.AluImm("AND", keep),
                ]
                if cell.value:
                    ops.append(isa.AluImm("OR", cell.value))
                ops.append(isa.LdIndexReg("IX", target - base, "A"))
                self.emit(ops, (cell.row, cell.col))
                self.state.set("A", None)


def generate_draw(
    plan: Plan,
    context: DrawContext,
    *,
    patch_weight: float | None = None,
    entry_pointer: bool | None = None,
    use_alternate: bool = True,
    initial_state: MachineState | None = None,
    manage_sp: bool = True,
    reserved: frozenset[str] = frozenset(),
) -> Program:
    """Generate the body of a draw routine for ``plan``."""
    return DrawGenerator(
        plan,
        context,
        patch_weight=patch_weight,
        entry_pointer=entry_pointer,
        use_alternate=use_alternate,
        initial_state=initial_state,
        manage_sp=manage_sp,
        reserved=reserved,
    ).generate()


def generate_draw_state(
    plan: Plan, context: DrawContext, **kwargs
) -> tuple[Program, MachineState]:
    """Generate a draw body and report the machine state it leaves behind."""
    generator = DrawGenerator(plan, context, **kwargs)
    program = generator.generate()
    return program, generator.state
