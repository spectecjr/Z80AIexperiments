"""Every emitted line must parse back to the instruction that wrote it.

The emulator checks the bytes; this checks the text those bytes are
shipped as, which is what sjasmplus will actually read.
"""

import pytest

from codesprite.cli import main
from codesprite.emit.parse import ParseError, parse_instruction, parse_module
from codesprite.z80 import isa

EVERY_OP = [
    isa.LdRegImm("A", 0x12),
    isa.LdRegImm("L", 0x80),
    isa.LdPairImm("HL", 0x8123),
    isa.LdPairImm("IX", 0x4000),
    isa.LdRegReg("A", "L"),
    isa.LdHlImm(0xAB),
    isa.LdHlReg("C"),
    isa.LdRegHl("A"),
    isa.LdIndexImm("IX", 5, 0x99),
    isa.LdIndexImm("IY", -3, 0x01),
    isa.LdIndexReg("IX", 2, "B"),
    isa.LdRegIndex("A", "IX", -1),
    isa.IncDec8("L"),
    isa.IncDec8("H", down=True),
    isa.IncDec16("HL"),
    isa.IncDec16("SP", down=True),
    isa.BitOp(7, "L"),
    isa.BitOp(7, "L", set_=False),
    isa.AluImm("AND", 0x0F),
    isa.AluImm("OR", 0xF0),
    isa.AluImm("ADD", 0x40),
    isa.AluReg("OR", "C"),
    isa.AluReg("ADD", "B"),
    isa.AluHl("AND"),
    isa.Push("HL"),
    isa.Push("IX"),
    isa.Pop("DE"),
    isa.Pop("AF"),
    isa.LdSpImm(0x8080),
    isa.LdSpPair("HL"),
    isa.LdSpPair("IX"),
    isa.Simple("EXX"),
    isa.Simple("EX DE,HL"),
    isa.Simple("LDI"),
    isa.Simple("DI"),
    isa.Simple("EI"),
    isa.Simple("RET"),
    isa.Simple("NOP"),
]


@pytest.mark.parametrize("op", EVERY_OP, ids=lambda op: op.text())
def test_text_parses_back_to_the_same_bytes(op):
    reparsed = parse_instruction(op.text())
    assert reparsed.encode() == op.encode(), (op.text(), reparsed)
    assert reparsed.tstates == op.tstates


def test_label_operands_survive_the_round_trip():
    for op in (
        isa.LdMemA(0, label=".p3+1"),
        isa.LdMemSp(0, label="spr_sprestore+1"),
        isa.LdAMem(0, label="counter"),
        isa.Djnz("loop"),
        isa.JumpCond("NZ", "loop"),
        isa.Jump("done"),
        isa.Call("draw"),
    ):
        reparsed = parse_instruction(op.text())
        assert reparsed.text() == op.text()


def test_unknown_syntax_is_rejected_not_guessed():
    for line in ("LD A,(BC)", "RLD", "OUTI", "LD IXH,3"):
        with pytest.raises(ParseError):
            parse_instruction(line)


SHIP = "..ff..\n.f11f.\nf1991f\n.f11f.\n"


@pytest.mark.parametrize("reloc", ["none", "patch", "register"])
@pytest.mark.parametrize("mode", ["best", "stack", "hl", "ix"])
def test_generated_modules_parse_back_exactly(tmp_path, reloc, mode):
    source = tmp_path / "ship.txt"
    source.write_text(SHIP)
    out = tmp_path / "out"
    main([
        "compile", str(source), "--name", "spr", "--out-dir", str(out),
        "--reloc", reloc, "--mode", mode,
        "--routines", "draw,erase,save,restore",
    ])
    files = list(out.glob("spr_*.z80s"))
    assert files
    for path in files:
        if path.name.endswith("manifest.z80s"):
            continue
        for number, line, op in parse_module(path.read_text()):
            # Re-encoding must agree with what the parser read back.
            assert op.encode() == parse_instruction(line).encode(), (
                f"{path.name}:{number}: {line}"
            )


def test_runtime_macros_file_is_syntactically_plausible():
    """The hand-written runtime is not generated, but its instruction lines
    should still be instructions we know how to encode."""
    from pathlib import Path

    runtime = Path(__file__).resolve().parents[1] / "runtime" / "sprite_rt.z80s"
    text = runtime.read_text()
    skipped = ("MACRO", "ENDM", "EQU", "SPR_", "CALL", "JP ", "LD B,A")
    for raw in text.splitlines():
        line = raw.split(";", 1)[0].strip()
        if not line or line.endswith(":") or line.startswith(skipped):
            continue
        if "SPR_" in line or "?" in line:
            continue  # symbolic constants and macro parameters
        parse_instruction(line)  # raises if we cannot encode it
