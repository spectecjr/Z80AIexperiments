"""The Z80 instruction subset the sprite compiler emits.

Every operation knows how to encode itself, how to print itself for
sjasmplus, how many T-states it costs (nominal timing) and which of its
immediate bytes are *patch points* for run-time repositioning.

Patch kinds
-----------
``PatchKind.L`` marks an immediate that holds the LOW byte of a screen
address, ``PatchKind.H`` the HIGH byte.  ``row`` records which sprite row
the address belongs to, so the position patcher knows whether to source
the byte from the even-row or odd-row register.  Immediates that are pure
data (pixel values, masks) carry no patch kind and are never touched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# 8-bit registers addressable in the standard r field.
R8 = {"B": 0, "C": 1, "D": 2, "E": 3, "H": 4, "L": 5, "A": 7}
# 16-bit pairs in the standard dd field.
RP = {"BC": 0, "DE": 1, "HL": 2, "SP": 3}
# 16-bit pairs in the qq field used by PUSH/POP.
QQ = {"BC": 0, "DE": 1, "HL": 2, "AF": 3}

PUSHABLE = ("BC", "DE", "HL", "AF", "IX", "IY")


class PatchKind(Enum):
    """What a patchable immediate byte holds."""

    L = "L"  # low byte of a screen address
    H = "H"  # high byte of a screen address


@dataclass(frozen=True)
class Patch:
    """One patchable immediate byte inside an instruction."""

    kind: PatchKind
    row: int  # sprite row whose address this is
    col: int = 0  # byte column, for diagnostics
    offset: int = 0  # byte offset of the immediate within the instruction


class Op:
    """Base class for an emitted instruction."""

    mnemonic: str = "?"

    # -- interface ---------------------------------------------------------
    def encode(self) -> bytes:  # pragma: no cover - overridden
        raise NotImplementedError

    def text(self) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    @property
    def tstates(self) -> int:  # pragma: no cover - overridden
        raise NotImplementedError

    @property
    def patches(self) -> tuple[Patch, ...]:
        return ()

    # -- shared ------------------------------------------------------------
    @property
    def size(self) -> int:
        return len(self.encode())

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{self.text()}>"


def _u8(value: int) -> int:
    return value & 0xFF


def _u16(value: int) -> int:
    return value & 0xFFFF


def _hx(value: int, width: int = 2) -> str:
    return f"${value:0{width}X}"


@dataclass(frozen=True)
class LdRegImm(Op):
    """``LD r,n`` - 7T, 2 bytes."""

    reg: str
    imm: int
    patch: Patch | None = None

    mnemonic = "LD r,n"

    def encode(self) -> bytes:
        return bytes([0x06 | (R8[self.reg] << 3), _u8(self.imm)])

    def text(self) -> str:
        return f"LD {self.reg},{_hx(_u8(self.imm))}"

    @property
    def tstates(self) -> int:
        return 7

    @property
    def patches(self) -> tuple[Patch, ...]:
        if self.patch is None:
            return ()
        return (Patch(self.patch.kind, self.patch.row, self.patch.col, 1),)


@dataclass(frozen=True)
class LdPairImm(Op):
    """``LD dd,nn`` - 10T, 3 bytes."""

    pair: str
    imm: int
    patch_lo: Patch | None = None
    patch_hi: Patch | None = None

    mnemonic = "LD dd,nn"

    def encode(self) -> bytes:
        value = _u16(self.imm)
        if self.pair in ("IX", "IY"):
            prefix = 0xDD if self.pair == "IX" else 0xFD
            return bytes([prefix, 0x21, value & 0xFF, value >> 8])
        return bytes([0x01 | (RP[self.pair] << 4), value & 0xFF, value >> 8])

    def text(self) -> str:
        return f"LD {self.pair},{_hx(_u16(self.imm), 4)}"

    @property
    def tstates(self) -> int:
        return 14 if self.pair in ("IX", "IY") else 10

    @property
    def patches(self) -> tuple[Patch, ...]:
        base = 2 if self.pair in ("IX", "IY") else 1
        out = []
        if self.patch_lo is not None:
            out.append(Patch(self.patch_lo.kind, self.patch_lo.row, self.patch_lo.col, base))
        if self.patch_hi is not None:
            out.append(
                Patch(self.patch_hi.kind, self.patch_hi.row, self.patch_hi.col, base + 1)
            )
        return tuple(out)


@dataclass(frozen=True)
class LdRegReg(Op):
    """``LD r,r'`` - 4T, 1 byte."""

    dst: str
    src: str

    mnemonic = "LD r,r'"

    def encode(self) -> bytes:
        return bytes([0x40 | (R8[self.dst] << 3) | R8[self.src]])

    def text(self) -> str:
        return f"LD {self.dst},{self.src}"

    @property
    def tstates(self) -> int:
        return 4


@dataclass(frozen=True)
class LdHlImm(Op):
    """``LD (HL),n`` - 10T, 2 bytes.  The workhorse write."""

    imm: int

    mnemonic = "LD (HL),n"

    def encode(self) -> bytes:
        return bytes([0x36, _u8(self.imm)])

    def text(self) -> str:
        return f"LD (HL),{_hx(_u8(self.imm))}"

    @property
    def tstates(self) -> int:
        return 10


@dataclass(frozen=True)
class LdHlReg(Op):
    """``LD (HL),r`` - 7T, 1 byte.  Used when a value is register-cached."""

    reg: str

    mnemonic = "LD (HL),r"

    def encode(self) -> bytes:
        return bytes([0x70 | R8[self.reg]])

    def text(self) -> str:
        return f"LD (HL),{self.reg}"

    @property
    def tstates(self) -> int:
        return 7


@dataclass(frozen=True)
class LdRegHl(Op):
    """``LD r,(HL)`` - 7T, 1 byte."""

    reg: str

    mnemonic = "LD r,(HL)"

    def encode(self) -> bytes:
        return bytes([0x46 | (R8[self.reg] << 3)])

    def text(self) -> str:
        return f"LD {self.reg},(HL)"

    @property
    def tstates(self) -> int:
        return 7


@dataclass(frozen=True)
class LdIndexImm(Op):
    """``LD (IX+d),n`` - 19T, 4 bytes."""

    index: str  # IX or IY
    disp: int
    imm: int

    mnemonic = "LD (IX+d),n"

    def encode(self) -> bytes:
        prefix = 0xDD if self.index == "IX" else 0xFD
        return bytes([prefix, 0x36, _u8(self.disp), _u8(self.imm)])

    def text(self) -> str:
        return f"LD ({self.index}{self.disp:+d}),{_hx(_u8(self.imm))}"

    @property
    def tstates(self) -> int:
        return 19


@dataclass(frozen=True)
class LdIndexReg(Op):
    """``LD (IX+d),r`` - 19T, 3 bytes."""

    index: str
    disp: int
    reg: str

    mnemonic = "LD (IX+d),r"

    def encode(self) -> bytes:
        prefix = 0xDD if self.index == "IX" else 0xFD
        return bytes([prefix, 0x70 | R8[self.reg], _u8(self.disp)])

    def text(self) -> str:
        return f"LD ({self.index}{self.disp:+d}),{self.reg}"

    @property
    def tstates(self) -> int:
        return 19


@dataclass(frozen=True)
class IncDec8(Op):
    """``INC r`` / ``DEC r`` - 4T, 1 byte."""

    reg: str
    down: bool = False

    def encode(self) -> bytes:
        return bytes([(0x05 if self.down else 0x04) | (R8[self.reg] << 3)])

    def text(self) -> str:
        return f"{'DEC' if self.down else 'INC'} {self.reg}"

    @property
    def tstates(self) -> int:
        return 4

    @property
    def mnemonic(self) -> str:  # type: ignore[override]
        return "DEC r" if self.down else "INC r"


@dataclass(frozen=True)
class IncDec16(Op):
    """``INC dd`` / ``DEC dd`` - 6T, 1 byte."""

    pair: str
    down: bool = False

    def encode(self) -> bytes:
        if self.pair in ("IX", "IY"):
            prefix = 0xDD if self.pair == "IX" else 0xFD
            return bytes([prefix, 0x2B if self.down else 0x23])
        return bytes([(0x0B if self.down else 0x03) | (RP[self.pair] << 4)])

    def text(self) -> str:
        return f"{'DEC' if self.down else 'INC'} {self.pair}"

    @property
    def tstates(self) -> int:
        return 10 if self.pair in ("IX", "IY") else 6

    @property
    def mnemonic(self) -> str:  # type: ignore[override]
        return "DEC dd" if self.down else "INC dd"


@dataclass(frozen=True)
class BitOp(Op):
    """``SET b,r`` / ``RES b,r`` - 8T, 2 bytes.

    ``SET 7,L`` and ``RES 7,L`` are how the generator steps between the two
    rows that share a 256-byte page without touching an immediate.
    """

    bit: int
    reg: str
    set_: bool = True

    def encode(self) -> bytes:
        base = 0xC0 if self.set_ else 0x80
        return bytes([0xCB, base | (self.bit << 3) | R8[self.reg]])

    def text(self) -> str:
        return f"{'SET' if self.set_ else 'RES'} {self.bit},{self.reg}"

    @property
    def tstates(self) -> int:
        return 8

    @property
    def mnemonic(self) -> str:  # type: ignore[override]
        return "SET b,r" if self.set_ else "RES b,r"


@dataclass(frozen=True)
class AluImm(Op):
    """``AND n`` / ``OR n`` / ``ADD A,n`` / ``SUB n`` - 7T, 2 bytes."""

    op: str  # AND, OR, XOR, ADD, SUB, CP
    imm: int

    _OPCODES = {"ADD": 0xC6, "SUB": 0xD6, "AND": 0xE6, "XOR": 0xEE, "OR": 0xF6, "CP": 0xFE}

    def encode(self) -> bytes:
        return bytes([self._OPCODES[self.op], _u8(self.imm)])

    def text(self) -> str:
        arg = f"A,{_hx(_u8(self.imm))}" if self.op == "ADD" else _hx(_u8(self.imm))
        return f"{self.op} {arg}"

    @property
    def tstates(self) -> int:
        return 7

    @property
    def mnemonic(self) -> str:  # type: ignore[override]
        return f"{self.op} n"


@dataclass(frozen=True)
class AluReg(Op):
    """``AND r`` / ``OR r`` / ``ADD A,r`` - 4T, 1 byte."""

    op: str
    reg: str

    _BASE = {"ADD": 0x80, "SUB": 0x90, "AND": 0xA0, "XOR": 0xA8, "OR": 0xB0, "CP": 0xB8}

    def encode(self) -> bytes:
        return bytes([self._BASE[self.op] | R8[self.reg]])

    def text(self) -> str:
        arg = f"A,{self.reg}" if self.op == "ADD" else self.reg
        return f"{self.op} {arg}"

    @property
    def tstates(self) -> int:
        return 4

    @property
    def mnemonic(self) -> str:  # type: ignore[override]
        return f"{self.op} r"


@dataclass(frozen=True)
class AluHl(Op):
    """``AND (HL)`` / ``OR (HL)`` - 7T, 1 byte."""

    op: str

    _BASE = {"ADD": 0x86, "SUB": 0x96, "AND": 0xA6, "XOR": 0xAE, "OR": 0xB6, "CP": 0xBE}

    def encode(self) -> bytes:
        return bytes([self._BASE[self.op]])

    def text(self) -> str:
        return f"{self.op} (HL)"

    @property
    def tstates(self) -> int:
        return 7

    @property
    def mnemonic(self) -> str:  # type: ignore[override]
        return f"{self.op} (HL)"


@dataclass(frozen=True)
class Push(Op):
    """``PUSH qq`` - 11T (15T for IX/IY).  Two screen bytes per instruction."""

    pair: str

    mnemonic = "PUSH qq"

    def encode(self) -> bytes:
        if self.pair in ("IX", "IY"):
            return bytes([0xDD if self.pair == "IX" else 0xFD, 0xE5])
        return bytes([0xC5 | (QQ[self.pair] << 4)])

    def text(self) -> str:
        return f"PUSH {self.pair}"

    @property
    def tstates(self) -> int:
        return 15 if self.pair in ("IX", "IY") else 11


@dataclass(frozen=True)
class Pop(Op):
    """``POP qq`` - 10T (14T for IX/IY)."""

    pair: str

    mnemonic = "POP qq"

    def encode(self) -> bytes:
        if self.pair in ("IX", "IY"):
            return bytes([0xDD if self.pair == "IX" else 0xFD, 0xE1])
        return bytes([0xC1 | (QQ[self.pair] << 4)])

    def text(self) -> str:
        return f"POP {self.pair}"

    @property
    def tstates(self) -> int:
        return 14 if self.pair in ("IX", "IY") else 10


@dataclass(frozen=True)
class LdSpImm(Op):
    """``LD SP,nn`` - 10T, 3 bytes."""

    imm: int
    patch_lo: Patch | None = None
    patch_hi: Patch | None = None

    mnemonic = "LD SP,nn"

    def encode(self) -> bytes:
        value = _u16(self.imm)
        return bytes([0x31, value & 0xFF, value >> 8])

    def text(self) -> str:
        return f"LD SP,{_hx(_u16(self.imm), 4)}"

    @property
    def tstates(self) -> int:
        return 10

    @property
    def patches(self) -> tuple[Patch, ...]:
        out = []
        if self.patch_lo is not None:
            out.append(Patch(self.patch_lo.kind, self.patch_lo.row, self.patch_lo.col, 1))
        if self.patch_hi is not None:
            out.append(Patch(self.patch_hi.kind, self.patch_hi.row, self.patch_hi.col, 2))
        return tuple(out)


@dataclass(frozen=True)
class LdSpPair(Op):
    """``LD SP,HL`` - 6T (``LD SP,IX`` 10T)."""

    pair: str = "HL"

    mnemonic = "LD SP,rr"

    def encode(self) -> bytes:
        if self.pair in ("IX", "IY"):
            return bytes([0xDD if self.pair == "IX" else 0xFD, 0xF9])
        return bytes([0xF9])

    def text(self) -> str:
        return f"LD SP,{self.pair}"

    @property
    def tstates(self) -> int:
        return 10 if self.pair in ("IX", "IY") else 6


@dataclass(frozen=True)
class LdMemSp(Op):
    """``LD (nn),SP`` - 20T, 4 bytes.  Saves the caller's stack pointer."""

    addr: int
    label: str | None = None

    mnemonic = "LD (nn),SP"

    def encode(self) -> bytes:
        value = _u16(self.addr)
        return bytes([0xED, 0x73, value & 0xFF, value >> 8])

    def text(self) -> str:
        target = self.label if self.label else _hx(_u16(self.addr), 4)
        return f"LD ({target}),SP"

    @property
    def tstates(self) -> int:
        return 20


@dataclass(frozen=True)
class LdMemA(Op):
    """``LD (nn),A`` - 13T, 3 bytes.  The self-modifying store in setpos."""

    addr: int
    label: str | None = None

    mnemonic = "LD (nn),A"

    def encode(self) -> bytes:
        value = _u16(self.addr)
        return bytes([0x32, value & 0xFF, value >> 8])

    def text(self) -> str:
        target = self.label if self.label else _hx(_u16(self.addr), 4)
        return f"LD ({target}),A"

    @property
    def tstates(self) -> int:
        return 13


@dataclass(frozen=True)
class LdAMem(Op):
    """``LD A,(nn)`` - 13T, 3 bytes."""

    addr: int
    label: str | None = None

    mnemonic = "LD A,(nn)"

    def encode(self) -> bytes:
        value = _u16(self.addr)
        return bytes([0x3A, value & 0xFF, value >> 8])

    def text(self) -> str:
        target = self.label if self.label else _hx(_u16(self.addr), 4)
        return f"LD A,({target})"

    @property
    def tstates(self) -> int:
        return 13


@dataclass(frozen=True)
class LdMemPair(Op):
    """``LD (nn),HL`` - 16T (20T for other pairs / index registers)."""

    pair: str
    addr: int
    label: str | None = None

    mnemonic = "LD (nn),rr"

    def encode(self) -> bytes:
        value = _u16(self.addr)
        lo, hi = value & 0xFF, value >> 8
        if self.pair == "HL":
            return bytes([0x22, lo, hi])
        if self.pair in ("IX", "IY"):
            return bytes([0xDD if self.pair == "IX" else 0xFD, 0x22, lo, hi])
        return bytes([0xED, 0x43 | (RP[self.pair] << 4), lo, hi])

    def text(self) -> str:
        target = self.label if self.label else _hx(_u16(self.addr), 4)
        return f"LD ({target}),{self.pair}"

    @property
    def tstates(self) -> int:
        if self.pair == "HL":
            return 16
        return 20


@dataclass(frozen=True)
class LdPairMem(Op):
    """``LD HL,(nn)`` - 16T (20T for other pairs)."""

    pair: str
    addr: int
    label: str | None = None

    mnemonic = "LD rr,(nn)"

    def encode(self) -> bytes:
        value = _u16(self.addr)
        lo, hi = value & 0xFF, value >> 8
        if self.pair == "HL":
            return bytes([0x2A, lo, hi])
        if self.pair in ("IX", "IY"):
            return bytes([0xDD if self.pair == "IX" else 0xFD, 0x2A, lo, hi])
        return bytes([0xED, 0x4B | (RP[self.pair] << 4), lo, hi])

    def text(self) -> str:
        target = self.label if self.label else _hx(_u16(self.addr), 4)
        return f"LD {self.pair},({target})"

    @property
    def tstates(self) -> int:
        return 16 if self.pair == "HL" else 20


@dataclass(frozen=True)
class Simple(Op):
    """A no-operand instruction: EXX, EX DE,HL, DI, EI, RET, NOP, LDI, LDIR."""

    name: str

    _TABLE = {
        "NOP": (bytes([0x00]), 4),
        "EXX": (bytes([0xD9]), 4),
        "EX DE,HL": (bytes([0xEB]), 4),
        "EX AF,AF'": (bytes([0x08]), 4),
        "DI": (bytes([0xF3]), 4),
        "EI": (bytes([0xFB]), 4),
        "RET": (bytes([0xC9]), 10),
        "LDI": (bytes([0xED, 0xA0]), 16),
        "LDD": (bytes([0xED, 0xA8]), 16),
        "SCF": (bytes([0x37]), 4),
        "CCF": (bytes([0x3F]), 4),
        "CPL": (bytes([0x2F]), 4),
        "HALT": (bytes([0x76]), 4),
    }

    def encode(self) -> bytes:
        return self._TABLE[self.name][0]

    def text(self) -> str:
        return self.name

    @property
    def tstates(self) -> int:
        return self._TABLE[self.name][1]

    @property
    def mnemonic(self) -> str:  # type: ignore[override]
        return self.name


@dataclass(frozen=True)
class Djnz(Op):
    """``DJNZ e`` - 13T taken, 8T not taken.  Cost recorded as taken."""

    label: str
    target: int = 0

    mnemonic = "DJNZ"

    def encode(self) -> bytes:
        return bytes([0x10, 0x00])  # displacement filled in by the assembler pass

    def text(self) -> str:
        return f"DJNZ {self.label}"

    @property
    def tstates(self) -> int:
        return 13


@dataclass(frozen=True)
class Jump(Op):
    """``JP nn`` - 10T, 3 bytes."""

    label: str
    target: int = 0

    mnemonic = "JP"

    def encode(self) -> bytes:
        value = _u16(self.target)
        return bytes([0xC3, value & 0xFF, value >> 8])

    def text(self) -> str:
        return f"JP {self.label}"

    @property
    def tstates(self) -> int:
        return 10


@dataclass(frozen=True)
class Call(Op):
    """``CALL nn`` - 17T, 3 bytes."""

    label: str
    target: int = 0

    mnemonic = "CALL"

    def encode(self) -> bytes:
        value = _u16(self.target)
        return bytes([0xCD, value & 0xFF, value >> 8])

    def text(self) -> str:
        return f"CALL {self.label}"

    @property
    def tstates(self) -> int:
        return 17


@dataclass
class Label(Op):
    """A pseudo-op: emits no bytes, names the current address."""

    name: str

    mnemonic = "label"

    def encode(self) -> bytes:
        return b""

    def text(self) -> str:
        return f"{self.name}:"

    @property
    def tstates(self) -> int:
        return 0


@dataclass
class Comment(Op):
    """A pseudo-op carrying a comment line."""

    text_: str

    mnemonic = "comment"

    def encode(self) -> bytes:
        return b""

    def text(self) -> str:
        return f"; {self.text_}"

    @property
    def tstates(self) -> int:
        return 0


def program_size(ops: list[Op]) -> int:
    return sum(op.size for op in ops)


def program_tstates(ops: list[Op]) -> int:
    return sum(op.tstates for op in ops)


def assemble(ops: list[Op], origin: int = 0) -> tuple[bytes, dict[str, int]]:
    """Encode ``ops`` at ``origin``, resolving labels for jumps.

    Two passes: the first records label addresses, the second encodes with
    branch targets filled in.  Only the forms the generator emits (JP, CALL,
    DJNZ) are resolved.
    """
    labels: dict[str, int] = {}
    address = origin
    for op in ops:
        if isinstance(op, Label):
            labels[op.name] = address
        address += op.size

    out = bytearray()
    address = origin
    for op in ops:
        if isinstance(op, (Jump, Call)):
            target = labels.get(op.label)
            if target is None:
                raise KeyError(f"unresolved label {op.label!r}")
            encoded = bytes([op.encode()[0], target & 0xFF, target >> 8])
        elif isinstance(op, Djnz):
            target = labels.get(op.label)
            if target is None:
                raise KeyError(f"unresolved label {op.label!r}")
            disp = target - (address + 2)
            if not -128 <= disp <= 127:
                raise ValueError(f"DJNZ to {op.label} out of range ({disp})")
            encoded = bytes([0x10, disp & 0xFF])
        else:
            encoded = op.encode()
        out += encoded
        address += len(encoded)
    return bytes(out), labels
