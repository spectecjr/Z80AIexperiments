"""Parse emitted assembly text back into instructions.

The generator verifies *bytes* in the emulator, but what ships is *text*
for sjasmplus.  This module closes that gap: it reads the emitted mnemonics
back and re-encodes them, so a mistake in how an instruction prints itself
is caught even when no real assembler is available.

It understands only the syntax codesprite emits - a deliberately small
subset - and raises on anything else rather than guessing.
"""

from __future__ import annotations

import re

from ..z80 import isa

_SIMPLE = {
    "NOP", "EXX", "EX DE,HL", "EX AF,AF'", "DI", "EI", "RET", "LDI", "LDD",
    "SCF", "CCF", "CPL", "HALT", "RLCA", "RRCA", "RLA", "RRA",
}

# Anything that names a register cannot be a memory operand label.
_NOT_A_LABEL = re.compile(r"^(A|B|C|D|E|H|L|BC|DE|HL|SP|AF|I[XY][HL]?)$", re.I)
_ALU = ("ADD", "ADC", "SUB", "SBC", "AND", "XOR", "OR", "CP")


class ParseError(ValueError):
    """Raised for a line outside the emitted subset."""


def parse_number(text: str) -> int:
    text = text.strip()
    if text.startswith("$"):
        return int(text[1:], 16)
    if text.startswith("%"):
        return int(text[1:], 2)
    return int(text, 0)


def strip_line(line: str) -> str:
    """Remove a trailing comment, and collapse the mnemonic's padding."""
    body = line.split(";", 1)[0].strip()
    return re.sub(r"\s+", " ", body)


def parse_instruction(text: str) -> isa.Op:
    """Turn one emitted mnemonic into the op that would produce it."""
    text = strip_line(text)
    if not text:
        raise ParseError("empty line")
    upper = text.upper()

    if upper in _SIMPLE:
        return isa.Simple(upper)

    match = re.fullmatch(r"LD \(HL\),(\$[0-9A-F]+|\d+)", upper)
    if match:
        return isa.LdHlImm(parse_number(match.group(1)))
    match = re.fullmatch(r"LD \(HL\),([ABCDEHL])", upper)
    if match:
        return isa.LdHlReg(match.group(1))
    match = re.fullmatch(r"LD ([ABCDEHL]),\(HL\)", upper)
    if match:
        return isa.LdRegHl(match.group(1))
    match = re.fullmatch(r"LD (BC|DE|HL|IX|IY|SP),(\$[0-9A-F]+|\d+)", upper)
    if match:
        pair, value = match.group(1), parse_number(match.group(2))
        return isa.LdSpImm(value) if pair == "SP" else isa.LdPairImm(pair, value)
    match = re.fullmatch(r"LD ([ABCDEHL]),(\$[0-9A-F]+|\d+)", upper)
    if match:
        return isa.LdRegImm(match.group(1), parse_number(match.group(2)))
    match = re.fullmatch(r"LD ([ABCDEHL]),([ABCDEHL])", upper)
    if match:
        return isa.LdRegReg(match.group(1), match.group(2))
    match = re.fullmatch(r"LD SP,(HL|IX|IY)", upper)
    if match:
        return isa.LdSpPair(match.group(1))
    match = re.fullmatch(r"LD \((I[XY])([+-]\d+)\),([ABCDEHL])", upper)
    if match:
        return isa.LdIndexReg(match.group(1), int(match.group(2)), match.group(3))
    match = re.fullmatch(r"LD \((I[XY])([+-]\d+)\),(\$[0-9A-F]+|\d+)", upper)
    if match:
        return isa.LdIndexImm(
            match.group(1), int(match.group(2)), parse_number(match.group(3))
        )
    match = re.fullmatch(r"LD \((I[XY])([+-]\d+)\),([ABCDEHL])", upper)
    if match:
        return isa.LdIndexReg(match.group(1), int(match.group(2)), match.group(3))
    match = re.fullmatch(r"LD ([ABCDEHL]),\((I[XY])([+-]\d+)\)", upper)
    if match:
        return isa.LdRegIndex(match.group(1), match.group(2), int(match.group(3)))
    match = re.fullmatch(r"LD \(([^)]+)\),SP", text)
    if match and not _NOT_A_LABEL.match(match.group(1)):
        return isa.LdMemSp(0, label=match.group(1))
    match = re.fullmatch(r"LD \(([^)]+)\),A", text)
    if match and not _NOT_A_LABEL.match(match.group(1)):
        return isa.LdMemA(0, label=match.group(1))
    match = re.fullmatch(r"LD A,\(([^)]+)\)", text)
    if match and not _NOT_A_LABEL.match(match.group(1)):
        return isa.LdAMem(0, label=match.group(1))
    match = re.fullmatch(r"(INC|DEC) ([ABCDEHL])", upper)
    if match:
        return isa.IncDec8(match.group(2), down=match.group(1) == "DEC")
    match = re.fullmatch(r"(INC|DEC) (BC|DE|HL|IX|IY|SP)", upper)
    if match:
        return isa.IncDec16(match.group(2), down=match.group(1) == "DEC")
    match = re.fullmatch(r"(SET|RES) (\d),([ABCDEHL])", upper)
    if match:
        return isa.BitOp(
            int(match.group(2)), match.group(3), set_=match.group(1) == "SET"
        )
    match = re.fullmatch(r"(PUSH|POP) (BC|DE|HL|AF|IX|IY)", upper)
    if match:
        return (isa.Push if match.group(1) == "PUSH" else isa.Pop)(match.group(2))
    match = re.fullmatch(r"(ADD|ADC|SBC) A,(\$[0-9A-F]+|\d+)", upper)
    if match:
        return isa.AluImm(match.group(1), parse_number(match.group(2)))
    match = re.fullmatch(r"(ADD|ADC|SBC) A,([ABCDEHL])", upper)
    if match:
        return isa.AluReg(match.group(1), match.group(2))
    match = re.fullmatch(r"(SUB|AND|XOR|OR|CP) (\$[0-9A-F]+|\d+)", upper)
    if match:
        return isa.AluImm(match.group(1), parse_number(match.group(2)))
    match = re.fullmatch(r"(SUB|AND|XOR|OR|CP) ([ABCDEHL])", upper)
    if match:
        return isa.AluReg(match.group(1), match.group(2))
    match = re.fullmatch(r"(SUB|AND|XOR|OR|CP) \(HL\)", upper)
    if match:
        return isa.AluHl(match.group(1))
    match = re.fullmatch(r"DJNZ (\S+)", text)
    if match:
        return isa.Djnz(match.group(1))
    match = re.fullmatch(r"JP (NZ|Z|NC|C|PO|PE|P|M),(\S+)", text, re.I)
    if match:
        return isa.JumpCond(match.group(1).upper(), match.group(2))
    match = re.fullmatch(r"JP (\S+)", text)
    if match:
        return isa.Jump(match.group(1))
    match = re.fullmatch(r"CALL (\S+)", text)
    if match:
        return isa.Call(match.group(1))
    raise ParseError(f"cannot parse {text!r}")


def parse_module(text: str) -> list[tuple[int, str, isa.Op]]:
    """Parse every instruction line of an emitted module.

    Returns (line number, original text, op).  Labels, EQUs, DEFBs and
    comments are skipped: this checks instruction spelling, not layout.
    """
    out: list[tuple[int, str, isa.Op]] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = strip_line(raw)
        if not line or line.endswith(":"):
            continue
        if re.match(r"^\S+\s+(EQU|DEFB|DEFW|DEFS)\b", line, re.I):
            continue
        if re.match(r"^(EQU|DEFB|DEFW|DEFS|ORG|MODULE|ENDMODULE|INCLUDE)\b", line, re.I):
            continue
        out.append((number, line, parse_instruction(line)))
    return out
