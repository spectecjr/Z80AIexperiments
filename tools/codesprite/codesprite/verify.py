"""Execute generated code and compare it with a reference composite.

Nothing is written out that has not been run.  A verification does four
things:

  1. builds a 64K image whose display file is pseudo-random noise, so a
     missed read-modify-write or an off-by-one shows up immediately;
  2. runs the *assembled bytes* of the routine in the emulator, which
     also exercises the encoder;
  3. compares every byte of the display file against a reference drawn in
     Python from the packed sprite;
  4. checks the routine touched nothing outside the region it is allowed
     to write, and left SP where it found it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .ir import Program
from .screen import SCREEN_BYTES, Screen
from .sprite import MASK_BOTH, PackedSprite
from .z80.emu import Z80, run

CODE_ORIGIN = 0x4000
STACK_TOP = 0x7F00


class VerificationError(AssertionError):
    """Raised when generated code does not match the reference."""


@dataclass
class VerifyResult:
    tstates: int
    writes: list[int] = field(default_factory=list)
    self_modified: list[int] = field(default_factory=list)


def reference_screen(
    memory: bytearray, packed: PackedSprite, screen: Screen, x: int, y: int
) -> bytearray:
    """Apply ``packed`` to a copy of ``memory`` the slow, obvious way."""
    out = bytearray(memory)
    for cell in packed.cells:
        address = screen.addr_byte(y + cell.row, x // 2 + cell.col)
        if cell.mask == MASK_BOTH:
            out[address] = cell.value
        else:
            keep = (~cell.mask) & 0xFF
            out[address] = (out[address] & keep) | cell.value
    return out


def noise_image(seed: int = 0, screen: Screen | None = None) -> bytearray:
    """A 64K image with random bytes in the display file, zero elsewhere."""
    memory = bytearray(0x1_0000)
    screen = screen or Screen()
    rng = random.Random(seed)
    for offset in range(SCREEN_BYTES):
        memory[(screen.base + offset) & 0xFFFF] = rng.randrange(256)
    return memory


def run_program(
    program: Program,
    memory: bytearray,
    *,
    origin: int = CODE_ORIGIN,
    registers: dict[str, int] | None = None,
    stack_top: int = STACK_TOP,
    track_writes: bool = False,
) -> tuple[Z80, int]:
    """Assemble ``program`` at ``origin`` into ``memory`` and call it."""
    from .z80 import isa

    code, _labels = program.assemble(origin)
    ops = list(program.ops)
    appended_ret = not ops or not isinstance(ops[-1], isa.Simple) or ops[-1].name != "RET"
    if appended_ret:
        code = code + b"\xc9"
    if origin <= 0 or origin + len(code) > 0x1_0000:
        raise VerificationError("generated code does not fit at the chosen origin")
    cpu = Z80(memory=memory)
    cpu.memory[origin : origin + len(code)] = code
    cpu.sp = stack_top
    for name, value in (registers or {}).items():
        setattr(cpu, name, value)
    # Push the sentinel return address before write tracking starts, so the
    # harness's own call frame is not reported as a stray write.
    cpu._push16(0xFFFE)
    cpu.track_writes = track_writes
    taken = run(cpu, origin, push_return=False)
    if appended_ret:
        taken -= 10  # the RET the harness added is not part of the program
    return cpu, taken, (origin, origin + len(code))


def verify_draw(
    program: Program,
    packed: PackedSprite,
    screen: Screen,
    x: int,
    y: int,
    *,
    seed: int = 0,
    registers: dict[str, int] | None = None,
    expected_tstates: int | None = None,
    origin: int = CODE_ORIGIN,
) -> VerifyResult:
    """Check ``program`` draws ``packed`` at (x, y) over random background."""
    memory = noise_image(seed, screen)
    expected = reference_screen(memory, packed, screen, x, y)
    cpu, taken, code_range = run_program(
        program, memory, origin=origin, registers=registers, track_writes=True
    )

    lo, hi = screen.base, screen.base + SCREEN_BYTES
    for address in range(lo, hi):
        if cpu.memory[address] != expected[address]:
            row = (address - lo) // 128
            col = (address - lo) % 128
            raise VerificationError(
                f"screen mismatch at {address:#06x} (row {row}, col {col}): "
                f"got {cpu.memory[address]:#04x}, expected {expected[address]:#04x}"
            )

    # Writes into the routine's own code are self-modification, which is how
    # the SP restore and the position patcher work; anything else is a bug.
    code_lo, code_hi = code_range
    stray = [
        a
        for a in cpu.writes
        if not (lo <= a < hi or code_lo <= a < code_hi)
    ]
    if stray:
        raise VerificationError(
            f"{len(stray)} write(s) outside the display file and code, "
            f"first at {stray[0]:#06x}"
        )
    if cpu.sp != STACK_TOP:
        raise VerificationError(
            f"stack pointer not restored: {cpu.sp:#06x} != {STACK_TOP:#06x}"
        )
    if expected_tstates is not None and taken != expected_tstates:
        raise VerificationError(
            f"cost model says {expected_tstates}T, emulator measured {taken}T"
        )
    return VerifyResult(
        tstates=taken,
        writes=[a for a in cpu.writes if lo <= a < hi],
        self_modified=[a for a in cpu.writes if code_lo <= a < code_hi],
    )


def verify_patched(
    draw: Program,
    setpos: Program,
    packed: PackedSprite,
    screen: Screen,
    compiled_at: tuple[int, int],
    target: tuple[int, int],
    *,
    seed: int = 0,
    origin: int = CODE_ORIGIN,
) -> VerifyResult:
    """Run setpos then draw, and check the sprite lands at ``target``.

    A patched routine is compiled for one position and moved by rewriting
    its address immediates.  The x parity and the y parity must match the
    variant, since those decide the pre-shift and the row-step encoding;
    everything else is free to move.
    """
    from .codegen.setpos import setpos_registers
    from .z80 import isa

    (x0, y0), (x1, y1) = compiled_at, target
    if (x0 % 2) != (x1 % 2) or (y0 % 2) != (y1 % 2):
        raise VerificationError(
            "a patched variant only moves within its own x and y parity"
        )

    combined = Program()
    combined.add(isa.Label("setpos"))
    combined.ops.extend(setpos.ops)
    combined.origins.extend(setpos.origins)
    combined.add(isa.Simple("RET"))
    combined.add(isa.Label("draw"))
    combined.ops.extend(draw.ops)
    combined.origins.extend(draw.origins)
    combined.add(isa.Simple("RET"))

    code, labels = combined.assemble(origin)
    memory = noise_image(seed, screen)
    expected = reference_screen(memory, packed, screen, x1, y1)

    cpu = Z80(memory=memory)
    cpu.memory[origin : origin + len(code)] = code
    cpu.sp = STACK_TOP
    for name, value in setpos_registers(x1, y1, screen.base).items():
        setattr(cpu, name, value)
    cpu._push16(0xFFFE)
    cpu.track_writes = True
    setpos_cost = run(cpu, labels["setpos"], push_return=False)

    cpu.track_writes = False  # the harness's own call frame is not a write
    cpu.sp = STACK_TOP
    cpu._push16(0xFFFE)
    cpu.track_writes = True
    draw_cost = run(cpu, labels["draw"], push_return=False)

    lo, hi = screen.base, screen.base + SCREEN_BYTES
    code_lo, code_hi = origin, origin + len(code)
    for address in range(lo, hi):
        if cpu.memory[address] != expected[address]:
            row, col = (address - lo) // 128, (address - lo) % 128
            raise VerificationError(
                f"patched draw at {target} wrong at {address:#06x} "
                f"(row {row}, col {col}): got {cpu.memory[address]:#04x}, "
                f"expected {expected[address]:#04x}"
            )
    stray = [a for a in cpu.writes if not (lo <= a < hi or code_lo <= a < code_hi)]
    if stray:
        raise VerificationError(
            f"{len(stray)} write(s) outside screen and code, first at {stray[0]:#06x}"
        )
    if cpu.sp != STACK_TOP:
        raise VerificationError(f"stack pointer not restored: {cpu.sp:#06x}")
    return VerifyResult(
        tstates=draw_cost - 10,
        writes=[a for a in cpu.writes if lo <= a < hi],
        self_modified=[a for a in cpu.writes if code_lo <= a < code_hi],
    )
