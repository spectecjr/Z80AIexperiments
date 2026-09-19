"""Encoder + emulator agreement tests for the emitted instruction subset."""

import pytest

from codesprite.z80 import isa
from codesprite.z80.emu import Z80, UnsupportedOpcode, run, run_steps


def make(ops, origin=0x4000, **regs):
    """Assemble ops at origin into a CPU, apply register presets."""
    code, labels = isa.assemble(list(ops) + [isa.Simple("RET")], origin)
    cpu = Z80()
    cpu.memory[origin : origin + len(code)] = code
    cpu.sp = 0x7000
    for name, value in regs.items():
        setattr(cpu, name, value)
    return cpu, labels


def exec_ops(ops, origin=0x4000, **regs):
    cpu, _ = make(ops, origin, **regs)
    taken = run(cpu, origin)
    # The trailing RET costs 10T; report the body cost.
    return cpu, taken - 10


# -- encoding ---------------------------------------------------------------


@pytest.mark.parametrize(
    "op, expected",
    [
        (isa.LdRegImm("A", 0x12), b"\x3e\x12"),
        (isa.LdRegImm("B", 0x34), b"\x06\x34"),
        (isa.LdRegImm("L", 0x80), b"\x2e\x80"),
        (isa.LdPairImm("HL", 0x8123), b"\x21\x23\x81"),
        (isa.LdPairImm("DE", 0x1234), b"\x11\x34\x12"),
        (isa.LdPairImm("IX", 0x8000), b"\xdd\x21\x00\x80"),
        (isa.LdRegReg("A", "L"), b"\x7d"),
        (isa.LdHlImm(0xAB), b"\x36\xab"),
        (isa.LdHlReg("C"), b"\x71"),
        (isa.LdRegHl("A"), b"\x7e"),
        (isa.LdIndexImm("IX", 5, 0x99), b"\xdd\x36\x05\x99"),
        (isa.LdIndexReg("IY", -2, "B"), b"\xfd\x70\xfe"),
        (isa.IncDec8("L"), b"\x2c"),
        (isa.IncDec8("L", down=True), b"\x2d"),
        (isa.IncDec8("H"), b"\x24"),
        (isa.IncDec16("HL"), b"\x23"),
        (isa.BitOp(7, "L"), b"\xcb\xfd"),
        (isa.BitOp(7, "L", set_=False), b"\xcb\xbd"),
        (isa.AluImm("AND", 0x0F), b"\xe6\x0f"),
        (isa.AluImm("OR", 0xF0), b"\xf6\xf0"),
        (isa.AluImm("ADD", 0x40), b"\xc6\x40"),
        (isa.AluReg("OR", "C"), b"\xb1"),
        (isa.AluHl("AND"), b"\xa6"),
        (isa.Push("HL"), b"\xe5"),
        (isa.Push("IX"), b"\xdd\xe5"),
        (isa.Pop("DE"), b"\xd1"),
        (isa.LdSpImm(0x8080), b"\x31\x80\x80"),
        (isa.LdSpPair("HL"), b"\xf9"),
        (isa.LdMemSp(0x9000), b"\xed\x73\x00\x90"),
        (isa.LdMemA(0x9000), b"\x32\x00\x90"),
        (isa.LdAMem(0x9000), b"\x3a\x00\x90"),
        (isa.LdMemPair("HL", 0x9000), b"\x22\x00\x90"),
        (isa.LdPairMem("HL", 0x9000), b"\x2a\x00\x90"),
        (isa.LdPairMem("DE", 0x9000), b"\xed\x5b\x00\x90"),
        (isa.Simple("EXX"), b"\xd9"),
        (isa.Simple("LDI"), b"\xed\xa0"),
        (isa.Simple("DI"), b"\xf3"),
        (isa.Simple("RET"), b"\xc9"),
    ],
)
def test_encoding(op, expected):
    assert op.encode() == expected
    assert op.size == len(expected)


@pytest.mark.parametrize(
    "op, expected_t",
    [
        (isa.LdHlImm(0), 10),
        (isa.LdHlReg("A"), 7),
        (isa.LdRegImm("A", 0), 7),
        (isa.LdPairImm("HL", 0), 10),
        (isa.LdPairImm("IX", 0), 14),
        (isa.IncDec8("L"), 4),
        (isa.BitOp(7, "L"), 8),
        (isa.Push("HL"), 11),
        (isa.Push("IX"), 15),
        (isa.Pop("HL"), 10),
        (isa.LdSpPair("HL"), 6),
        (isa.LdSpImm(0), 10),
        (isa.LdMemSp(0), 20),
        (isa.LdMemA(0), 13),
        (isa.LdIndexImm("IX", 0, 0), 19),
        (isa.Simple("LDI"), 16),
        (isa.Simple("RET"), 10),
    ],
)
def test_nominal_timing(op, expected_t):
    assert op.tstates == expected_t


def test_text_output():
    assert isa.LdHlImm(0xAB).text() == "LD (HL),$AB"
    assert isa.LdPairImm("HL", 0x8123).text() == "LD HL,$8123"
    assert isa.BitOp(7, "L", set_=False).text() == "RES 7,L"
    assert isa.LdIndexImm("IX", -3, 1).text() == "LD (IX-3),$01"
    assert isa.LdMemA(0, label="patch12").text() == "LD (patch12),A"


# -- emulation --------------------------------------------------------------


def test_write_via_hl_immediate():
    cpu, t = exec_ops([isa.LdPairImm("HL", 0x8000), isa.LdHlImm(0x5A)])
    assert cpu.memory[0x8000] == 0x5A
    assert t == 10 + 10


def test_write_via_register_and_inc_l():
    cpu, t = exec_ops(
        [
            isa.LdPairImm("HL", 0x8000),
            isa.LdRegImm("C", 0x77),
            isa.LdHlReg("C"),
            isa.IncDec8("L"),
            isa.LdHlReg("C"),
        ]
    )
    assert cpu.memory[0x8000] == 0x77
    assert cpu.memory[0x8001] == 0x77
    assert t == 10 + 7 + 7 + 4 + 7


def test_row_step_set_bit7_matches_screen_maths():
    # From row 0 col 0 (0x8000), SET 7,L reaches row 1 col 0 (0x8080).
    cpu, _ = exec_ops(
        [isa.LdPairImm("HL", 0x8000), isa.BitOp(7, "L"), isa.LdHlImm(0x11)]
    )
    assert cpu.memory[0x8080] == 0x11


def test_row_step_from_odd_row():
    # From row 1 (0x8080), INC H : RES 7,L reaches row 2 (0x8100).
    cpu, _ = exec_ops(
        [
            isa.LdPairImm("HL", 0x8080),
            isa.IncDec8("H"),
            isa.BitOp(7, "L", set_=False),
            isa.LdHlImm(0x22),
        ]
    )
    assert cpu.memory[0x8100] == 0x22


def test_stack_writes_go_downwards_two_bytes_at_a_time():
    ops = [
        isa.LdSpImm(0x8010),
        isa.LdPairImm("DE", 0x1234),
        isa.Push("DE"),
        isa.Push("DE"),
    ]
    code, _ = isa.assemble(ops, 0x4000)
    cpu = Z80()
    cpu.memory[0x4000 : 0x4000 + len(code)] = code
    t = run_steps(cpu, 0x4000, len(ops))
    # PUSH writes high byte at SP-1 then low byte at SP-2.
    assert cpu.memory[0x800F] == 0x12
    assert cpu.memory[0x800E] == 0x34
    assert cpu.memory[0x800D] == 0x12
    assert cpu.memory[0x800C] == 0x34
    assert cpu.sp == 0x800C
    assert t == 10 + 10 + 11 + 11


def test_read_modify_write_half_byte():
    # Keep the high nibble of the background, replace the low nibble with 7.
    cpu, t = exec_ops(
        [
            isa.LdPairImm("HL", 0x8000),
            isa.LdRegHl("A"),
            isa.AluImm("AND", 0xF0),
            isa.AluImm("OR", 0x07),
            isa.LdHlReg("A"),
        ]
    )
    assert t == 10 + 7 + 7 + 7 + 7
    cpu2, _ = make([], 0x4000)
    # run again with a background value
    cpu3, _ = exec_ops(
        [
            isa.LdPairImm("HL", 0x8000),
            isa.LdRegHl("A"),
            isa.AluImm("AND", 0xF0),
            isa.AluImm("OR", 0x07),
            isa.LdHlReg("A"),
        ]
    )
    cpu3.memory[0x8000] = 0x00
    # deterministic check with an explicit background:
    cpu4 = Z80()
    code, _ = isa.assemble(
        [
            isa.LdPairImm("HL", 0x8000),
            isa.LdRegHl("A"),
            isa.AluImm("AND", 0xF0),
            isa.AluImm("OR", 0x07),
            isa.LdHlReg("A"),
            isa.Simple("RET"),
        ],
        0x4000,
    )
    cpu4.memory[0x4000 : 0x4000 + len(code)] = code
    cpu4.memory[0x8000] = 0xC3
    cpu4.sp = 0x7000
    run(cpu4, 0x4000)
    assert cpu4.memory[0x8000] == 0xC7


def test_exx_swaps_banks():
    cpu, _ = exec_ops(
        [
            isa.LdPairImm("DE", 0x1111),
            isa.Simple("EXX"),
            isa.LdPairImm("DE", 0x2222),
            isa.Simple("EXX"),
        ]
    )
    assert cpu.de == 0x1111
    cpu.b, cpu.c = 0, 0
    assert cpu.d_ == 0x22 and cpu.e_ == 0x22


def test_ldi_copies_and_advances():
    cpu, _ = make([], 0x4000)
    cpu.memory[0x9000] = 0x42
    code, _ = isa.assemble(
        [
            isa.LdPairImm("HL", 0x9000),
            isa.LdPairImm("DE", 0x8000),
            isa.LdPairImm("BC", 1),
            isa.Simple("LDI"),
            isa.Simple("RET"),
        ],
        0x4000,
    )
    cpu.memory[0x4000 : 0x4000 + len(code)] = code
    run(cpu, 0x4000)
    assert cpu.memory[0x8000] == 0x42
    assert cpu.hl == 0x9001 and cpu.de == 0x8001


def test_self_modifying_store_patches_an_immediate():
    """The setpos mechanism: LD (label+1),A rewrites an LD L,n operand."""
    ops = [
        isa.LdRegImm("A", 0x40),
        isa.LdMemA(0x4000 + 5 + 1),  # patch the LD L,n immediate below
        isa.LdPairImm("HL", 0x8000),
        isa.LdRegImm("L", 0x00),  # <- immediate patched to 0x40
        isa.LdHlImm(0x99),
    ]
    # layout: LD A,n (2) + LD (nn),A (3) = 5, then LD HL,nn (3) at 5..7,
    # so LD L,n sits at 8 and its immediate at 9.
    ops[1] = isa.LdMemA(0x4000 + 9)
    cpu, _ = exec_ops(ops)
    assert cpu.memory[0x8040] == 0x99


def test_djnz_loop_runs_b_times():
    ops = [
        isa.LdPairImm("HL", 0x8000),
        isa.LdRegImm("B", 4),
        isa.Label("loop"),
        isa.LdHlImm(0xEE),
        isa.IncDec8("L"),
        isa.Djnz("loop"),
    ]
    cpu, _ = exec_ops(ops)
    assert list(cpu.memory[0x8000:0x8005]) == [0xEE, 0xEE, 0xEE, 0xEE, 0x00]


def test_pop_list_protocol():
    """The list form: addresses are popped off the caller's stack."""
    cpu = Z80()
    code, labels = isa.assemble(
        [
            isa.Label("body"),
            isa.Pop("HL"),
            isa.LdHlImm(0x5C),
            isa.Djnz("body"),
            isa.Simple("RET"),
        ],
        0x4000,
    )
    cpu.memory[0x4000 : 0x4000 + len(code)] = code
    # Caller pushes the return address, then the items last-first, so the
    # first POP yields the first item and the final RET finds the sentinel.
    cpu.sp = 0x7000
    cpu.b = 3
    for address in (0xFFFE, 0x8200, 0x8100, 0x8000):
        cpu.sp = (cpu.sp - 2) & 0xFFFF
        cpu.memory[cpu.sp] = address & 0xFF
        cpu.memory[cpu.sp + 1] = address >> 8
    run(cpu, 0x4000, push_return=False)
    assert cpu.memory[0x8000] == 0x5C
    assert cpu.memory[0x8100] == 0x5C
    assert cpu.memory[0x8200] == 0x5C


def test_write_tracking_catches_stray_writes():
    cpu, _ = make([isa.LdPairImm("HL", 0x9000), isa.LdHlImm(1)], 0x4000)
    cpu.track_writes = True
    run(cpu, 0x4000)
    assert 0x9000 in cpu.writes


def test_unsupported_opcode_raises():
    cpu = Z80()
    cpu.memory[0x4000] = 0xDB  # IN A,(n) - outside the subset
    cpu.memory[0x4001] = 0xFE
    cpu.pc = 0x4000
    with pytest.raises(UnsupportedOpcode):
        cpu.step()


def test_assemble_resolves_labels():
    code, labels = isa.assemble(
        [isa.Label("start"), isa.Simple("NOP"), isa.Jump("start")], 0x8000
    )
    assert labels["start"] == 0x8000
    assert code == b"\x00\xc3\x00\x80"


def test_assemble_djnz_displacement():
    code, _ = isa.assemble(
        [isa.Label("l"), isa.Simple("NOP"), isa.Djnz("l")], 0x8000
    )
    assert code == b"\x00\x10\xfd"


def test_patch_offsets_reported():
    op = isa.LdPairImm(
        "HL",
        0x8000,
        patch_lo=isa.Patch(isa.PatchKind.L, row=3),
        patch_hi=isa.Patch(isa.PatchKind.H, row=3),
    )
    kinds = [(p.kind, p.offset) for p in op.patches]
    assert kinds == [(isa.PatchKind.L, 1), (isa.PatchKind.H, 2)]
    op2 = isa.LdRegImm("L", 0, patch=isa.Patch(isa.PatchKind.L, row=1))
    assert [(p.kind, p.offset) for p in op2.patches] == [(isa.PatchKind.L, 1)]
