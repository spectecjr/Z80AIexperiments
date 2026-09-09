"""A small Z80 emulator covering the instructions the compiler emits.

This is the correctness oracle: generated code is executed against a 64K
memory image and compared with a reference composite.  It runs *encoded
bytes*, not the IR, so it also validates the encoder.  Anything outside
the emitted subset raises :class:`UnsupportedOpcode` rather than silently
doing the wrong thing.

Only the flags the compiler can observe are modelled (S, Z, H, P/V, N, C
for the ALU ops used); undocumented behaviour is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MEM_SIZE = 0x1_0000

FLAG_C = 0x01
FLAG_N = 0x02
FLAG_PV = 0x04
FLAG_H = 0x10
FLAG_Z = 0x40
FLAG_S = 0x80


class UnsupportedOpcode(NotImplementedError):
    """Raised when the emulator meets an instruction outside the subset."""

    def __init__(self, pc: int, opcode: int, prefix: int | None = None) -> None:
        where = f"{prefix:02X} {opcode:02X}" if prefix is not None else f"{opcode:02X}"
        super().__init__(f"unsupported opcode {where} at {pc:#06x}")
        self.pc = pc
        self.opcode = opcode
        self.prefix = prefix


class ExecutionLimit(RuntimeError):
    """Raised when a run exceeds its instruction budget (runaway code)."""


@dataclass
class Z80:
    """Registers plus 64K of RAM, with a T-state counter."""

    memory: bytearray = field(default_factory=lambda: bytearray(MEM_SIZE))
    a: int = 0
    f: int = 0
    b: int = 0
    c: int = 0
    d: int = 0
    e: int = 0
    h: int = 0
    l: int = 0
    a_: int = 0
    f_: int = 0
    b_: int = 0
    c_: int = 0
    d_: int = 0
    e_: int = 0
    h_: int = 0
    l_: int = 0
    ix: int = 0
    iy: int = 0
    sp: int = 0
    pc: int = 0
    iff: bool = True
    tstates: int = 0
    writes: list[int] = field(default_factory=list)
    track_writes: bool = False

    # -- register pair helpers --------------------------------------------
    @property
    def bc(self) -> int:
        return (self.b << 8) | self.c

    @bc.setter
    def bc(self, value: int) -> None:
        self.b, self.c = (value >> 8) & 0xFF, value & 0xFF

    @property
    def de(self) -> int:
        return (self.d << 8) | self.e

    @de.setter
    def de(self, value: int) -> None:
        self.d, self.e = (value >> 8) & 0xFF, value & 0xFF

    @property
    def hl(self) -> int:
        return (self.h << 8) | self.l

    @hl.setter
    def hl(self, value: int) -> None:
        self.h, self.l = (value >> 8) & 0xFF, value & 0xFF

    @property
    def af(self) -> int:
        return (self.a << 8) | self.f

    @af.setter
    def af(self, value: int) -> None:
        self.a, self.f = (value >> 8) & 0xFF, value & 0xFF

    # -- memory ------------------------------------------------------------
    def read(self, addr: int) -> int:
        return self.memory[addr & 0xFFFF]

    def write(self, addr: int, value: int) -> None:
        addr &= 0xFFFF
        self.memory[addr] = value & 0xFF
        if self.track_writes:
            self.writes.append(addr)

    def _fetch(self) -> int:
        value = self.memory[self.pc]
        self.pc = (self.pc + 1) & 0xFFFF
        return value

    def _fetch16(self) -> int:
        lo = self._fetch()
        return lo | (self._fetch() << 8)

    def _push16(self, value: int) -> None:
        self.sp = (self.sp - 1) & 0xFFFF
        self.write(self.sp, (value >> 8) & 0xFF)
        self.sp = (self.sp - 1) & 0xFFFF
        self.write(self.sp, value & 0xFF)

    def _pop16(self) -> int:
        lo = self.read(self.sp)
        self.sp = (self.sp + 1) & 0xFFFF
        hi = self.read(self.sp)
        self.sp = (self.sp + 1) & 0xFFFF
        return lo | (hi << 8)

    # -- register file access by index ------------------------------------
    _R8_NAMES = {0: "b", 1: "c", 2: "d", 3: "e", 4: "h", 5: "l", 7: "a"}

    def _get_r(self, index: int) -> int:
        if index == 6:
            return self.read(self.hl)
        return getattr(self, self._R8_NAMES[index])

    def _set_r(self, index: int, value: int) -> None:
        if index == 6:
            self.write(self.hl, value)
        else:
            setattr(self, self._R8_NAMES[index], value & 0xFF)

    _RP_NAMES = {0: "bc", 1: "de", 2: "hl", 3: "sp"}

    def _get_rp(self, index: int) -> int:
        return getattr(self, self._RP_NAMES[index])

    def _set_rp(self, index: int, value: int) -> None:
        setattr(self, self._RP_NAMES[index], value & 0xFFFF)

    # -- flags -------------------------------------------------------------
    @staticmethod
    def _parity(value: int) -> int:
        return FLAG_PV if bin(value & 0xFF).count("1") % 2 == 0 else 0

    def _logic_flags(self, result: int, half: int) -> None:
        result &= 0xFF
        self.f = (
            (FLAG_S if result & 0x80 else 0)
            | (FLAG_Z if result == 0 else 0)
            | half
            | self._parity(result)
        )

    def _add_flags(self, before: int, operand: int, result: int, carry_in: int = 0) -> None:
        value = result & 0xFF
        half = ((before & 0x0F) + (operand & 0x0F) + carry_in) > 0x0F
        overflow = (~(before ^ operand) & (before ^ value) & 0x80) != 0
        self.f = (
            (FLAG_S if value & 0x80 else 0)
            | (FLAG_Z if value == 0 else 0)
            | (FLAG_H if half else 0)
            | (FLAG_PV if overflow else 0)
            | (FLAG_C if result > 0xFF else 0)
        )

    def _sub_flags(self, before: int, operand: int, result: int, carry_in: int = 0) -> None:
        value = result & 0xFF
        half = ((before & 0x0F) - (operand & 0x0F) - carry_in) < 0
        overflow = ((before ^ operand) & (before ^ value) & 0x80) != 0
        self.f = (
            (FLAG_S if value & 0x80 else 0)
            | (FLAG_Z if value == 0 else 0)
            | (FLAG_H if half else 0)
            | (FLAG_PV if overflow else 0)
            | FLAG_N
            | (FLAG_C if result < 0 else 0)
        )

    def _alu(self, op: int, operand: int) -> None:
        """ALU operation ``op`` (0..7) between A and ``operand``."""
        if op == 0:  # ADD
            result = self.a + operand
            self._add_flags(self.a, operand, result)
            self.a = result & 0xFF
        elif op == 1:  # ADC
            carry = 1 if self.f & FLAG_C else 0
            result = self.a + operand + carry
            self._add_flags(self.a, operand, result, carry)
            self.a = result & 0xFF
        elif op == 2:  # SUB
            result = self.a - operand
            self._sub_flags(self.a, operand, result)
            self.a = result & 0xFF
        elif op == 3:  # SBC
            carry = 1 if self.f & FLAG_C else 0
            result = self.a - operand - carry
            self._sub_flags(self.a, operand, result, carry)
            self.a = result & 0xFF
        elif op == 4:  # AND
            self.a &= operand
            self._logic_flags(self.a, FLAG_H)
        elif op == 5:  # XOR
            self.a ^= operand
            self._logic_flags(self.a, 0)
        elif op == 6:  # OR
            self.a |= operand
            self._logic_flags(self.a, 0)
        else:  # CP
            result = self.a - operand
            self._sub_flags(self.a, operand, result)

    # -- execution ---------------------------------------------------------
    def step(self) -> None:
        """Execute one instruction, advancing ``tstates``."""
        pc = self.pc
        opcode = self._fetch()

        if opcode == 0x00:  # NOP
            self.tstates += 4
        elif opcode == 0x08:  # EX AF,AF'
            self.a, self.a_ = self.a_, self.a
            self.f, self.f_ = self.f_, self.f
            self.tstates += 4
        elif opcode == 0xD9:  # EXX
            self.b, self.b_ = self.b_, self.b
            self.c, self.c_ = self.c_, self.c
            self.d, self.d_ = self.d_, self.d
            self.e, self.e_ = self.e_, self.e
            self.h, self.h_ = self.h_, self.h
            self.l, self.l_ = self.l_, self.l
            self.tstates += 4
        elif opcode == 0xEB:  # EX DE,HL
            self.de, self.hl = self.hl, self.de
            self.tstates += 4
        elif opcode == 0xF3:  # DI
            self.iff = False
            self.tstates += 4
        elif opcode == 0xFB:  # EI
            self.iff = True
            self.tstates += 4
        elif opcode == 0x2F:  # CPL
            self.a = (~self.a) & 0xFF
            self.f |= FLAG_H | FLAG_N
            self.tstates += 4
        elif opcode == 0x37:  # SCF
            self.f = (self.f & ~(FLAG_H | FLAG_N)) | FLAG_C
            self.tstates += 4
        elif opcode == 0x3F:  # CCF
            self.f = (self.f & ~FLAG_N) ^ FLAG_C
            self.tstates += 4
        elif opcode == 0x76:  # HALT - used as a stop marker
            self.pc = pc  # stay put
            self.tstates += 4
            raise Halt()
        elif opcode == 0xC9:  # RET
            self.pc = self._pop16()
            self.tstates += 10
        elif opcode == 0xC3:  # JP nn
            self.pc = self._fetch16()
            self.tstates += 10
        elif opcode == 0xCD:  # CALL nn
            target = self._fetch16()
            self._push16(self.pc)
            self.pc = target
            self.tstates += 17
        elif opcode == 0x10:  # DJNZ
            disp = self._fetch()
            self.b = (self.b - 1) & 0xFF
            if self.b:
                self.pc = (self.pc + ((disp ^ 0x80) - 0x80)) & 0xFFFF
                self.tstates += 13
            else:
                self.tstates += 8
        elif opcode == 0x18:  # JR
            disp = self._fetch()
            self.pc = (self.pc + ((disp ^ 0x80) - 0x80)) & 0xFFFF
            self.tstates += 12
        elif opcode == 0x36:  # LD (HL),n
            self.write(self.hl, self._fetch())
            self.tstates += 10
        elif opcode == 0x32:  # LD (nn),A
            self.write(self._fetch16(), self.a)
            self.tstates += 13
        elif opcode == 0x3A:  # LD A,(nn)
            self.a = self.read(self._fetch16())
            self.tstates += 13
        elif opcode == 0x22:  # LD (nn),HL
            addr = self._fetch16()
            self.write(addr, self.l)
            self.write(addr + 1, self.h)
            self.tstates += 16
        elif opcode == 0x2A:  # LD HL,(nn)
            addr = self._fetch16()
            self.l = self.read(addr)
            self.h = self.read(addr + 1)
            self.tstates += 16
        elif opcode == 0x31:  # LD SP,nn
            self.sp = self._fetch16()
            self.tstates += 10
        elif opcode == 0xF9:  # LD SP,HL
            self.sp = self.hl
            self.tstates += 6
        elif opcode & 0xCF == 0x01:  # LD dd,nn
            self._set_rp((opcode >> 4) & 3, self._fetch16())
            self.tstates += 10
        elif opcode & 0xCF == 0x03:  # INC dd
            index = (opcode >> 4) & 3
            self._set_rp(index, (self._get_rp(index) + 1) & 0xFFFF)
            self.tstates += 6
        elif opcode & 0xCF == 0x0B:  # DEC dd
            index = (opcode >> 4) & 3
            self._set_rp(index, (self._get_rp(index) - 1) & 0xFFFF)
            self.tstates += 6
        elif opcode & 0xC7 == 0x04:  # INC r
            index = (opcode >> 3) & 7
            before = self._get_r(index)
            value = (before + 1) & 0xFF
            self._set_r(index, value)
            self.f = (
                (self.f & FLAG_C)
                | (FLAG_S if value & 0x80 else 0)
                | (FLAG_Z if value == 0 else 0)
                | (FLAG_H if (before & 0x0F) == 0x0F else 0)
                | (FLAG_PV if before == 0x7F else 0)
            )
            self.tstates += 11 if index == 6 else 4
        elif opcode & 0xC7 == 0x05:  # DEC r
            index = (opcode >> 3) & 7
            before = self._get_r(index)
            value = (before - 1) & 0xFF
            self._set_r(index, value)
            self.f = (
                (self.f & FLAG_C)
                | FLAG_N
                | (FLAG_S if value & 0x80 else 0)
                | (FLAG_Z if value == 0 else 0)
                | (FLAG_H if (before & 0x0F) == 0 else 0)
                | (FLAG_PV if before == 0x80 else 0)
            )
            self.tstates += 11 if index == 6 else 4
        elif opcode & 0xC7 == 0x06:  # LD r,n
            index = (opcode >> 3) & 7
            self._set_r(index, self._fetch())
            self.tstates += 10 if index == 6 else 7
        elif 0x40 <= opcode <= 0x7F:  # LD r,r'
            dst, src = (opcode >> 3) & 7, opcode & 7
            self._set_r(dst, self._get_r(src))
            self.tstates += 7 if (dst == 6 or src == 6) else 4
        elif 0x80 <= opcode <= 0xBF:  # ALU A,r
            op, src = (opcode >> 3) & 7, opcode & 7
            self._alu(op, self._get_r(src))
            self.tstates += 7 if src == 6 else 4
        elif opcode & 0xC7 == 0xC6:  # ALU A,n
            self._alu((opcode >> 3) & 7, self._fetch())
            self.tstates += 7
        elif opcode & 0xCF == 0xC5:  # PUSH qq
            index = (opcode >> 4) & 3
            self._push16(self.af if index == 3 else self._get_rp(index))
            self.tstates += 11
        elif opcode & 0xCF == 0xC1:  # POP qq
            index = (opcode >> 4) & 3
            value = self._pop16()
            if index == 3:
                self.af = value
            else:
                self._set_rp(index, value)
            self.tstates += 10
        elif opcode == 0xCB:
            self._exec_cb(pc)
        elif opcode == 0xED:
            self._exec_ed(pc)
        elif opcode in (0xDD, 0xFD):
            self._exec_index(pc, opcode)
        else:
            raise UnsupportedOpcode(pc, opcode)

    def _exec_cb(self, pc: int) -> None:
        opcode = self._fetch()
        index = opcode & 7
        bit = (opcode >> 3) & 7
        if opcode < 0x40:
            raise UnsupportedOpcode(pc, opcode, 0xCB)
        if opcode < 0x80:  # BIT
            value = self._get_r(index)
            self.f = (
                (self.f & FLAG_C)
                | FLAG_H
                | (FLAG_Z | FLAG_PV if not value & (1 << bit) else 0)
                | (FLAG_S if bit == 7 and value & 0x80 else 0)
            )
            self.tstates += 12 if index == 6 else 8
        elif opcode < 0xC0:  # RES
            self._set_r(index, self._get_r(index) & ~(1 << bit))
            self.tstates += 15 if index == 6 else 8
        else:  # SET
            self._set_r(index, self._get_r(index) | (1 << bit))
            self.tstates += 15 if index == 6 else 8

    def _exec_ed(self, pc: int) -> None:
        opcode = self._fetch()
        if opcode == 0x73:  # LD (nn),SP
            addr = self._fetch16()
            self.write(addr, self.sp & 0xFF)
            self.write(addr + 1, self.sp >> 8)
            self.tstates += 20
        elif opcode == 0x7B:  # LD SP,(nn)
            addr = self._fetch16()
            self.sp = self.read(addr) | (self.read(addr + 1) << 8)
            self.tstates += 20
        elif opcode & 0xCF == 0x43:  # LD (nn),dd
            addr = self._fetch16()
            value = self._get_rp((opcode >> 4) & 3)
            self.write(addr, value & 0xFF)
            self.write(addr + 1, value >> 8)
            self.tstates += 20
        elif opcode & 0xCF == 0x4B:  # LD dd,(nn)
            addr = self._fetch16()
            self._set_rp((opcode >> 4) & 3, self.read(addr) | (self.read(addr + 1) << 8))
            self.tstates += 20
        elif opcode == 0x44:  # NEG
            result = -self.a
            self._sub_flags(0, self.a, result)
            self.a = result & 0xFF
            self.tstates += 8
        elif opcode in (0xA0, 0xA8, 0xB0, 0xB8):  # LDI / LDD / LDIR / LDDR
            step = 1 if opcode in (0xA0, 0xB0) else -1
            self.write(self.de, self.read(self.hl))
            self.hl = (self.hl + step) & 0xFFFF
            self.de = (self.de + step) & 0xFFFF
            self.bc = (self.bc - 1) & 0xFFFF
            self.f = (self.f & (FLAG_C | FLAG_Z | FLAG_S)) | (
                FLAG_PV if self.bc else 0
            )
            repeating = opcode in (0xB0, 0xB8) and self.bc != 0
            if repeating:
                self.pc = (self.pc - 2) & 0xFFFF
                self.tstates += 21
            else:
                self.tstates += 16
        else:
            raise UnsupportedOpcode(pc, opcode, 0xED)

    def _exec_index(self, pc: int, prefix: int) -> None:
        opcode = self._fetch()
        name = "ix" if prefix == 0xDD else "iy"
        value = getattr(self, name)
        if opcode == 0x21:  # LD IX,nn
            setattr(self, name, self._fetch16())
            self.tstates += 14
        elif opcode == 0x22:  # LD (nn),IX
            addr = self._fetch16()
            self.write(addr, value & 0xFF)
            self.write(addr + 1, value >> 8)
            self.tstates += 20
        elif opcode == 0x2A:  # LD IX,(nn)
            addr = self._fetch16()
            setattr(self, name, self.read(addr) | (self.read(addr + 1) << 8))
            self.tstates += 20
        elif opcode == 0x23:  # INC IX
            setattr(self, name, (value + 1) & 0xFFFF)
            self.tstates += 10
        elif opcode == 0x2B:  # DEC IX
            setattr(self, name, (value - 1) & 0xFFFF)
            self.tstates += 10
        elif opcode == 0x24:  # INC IXH
            setattr(self, name, ((value + 0x100) & 0xFF00) | (value & 0xFF))
            self.tstates += 8
        elif opcode == 0x2C:  # INC IXL
            setattr(self, name, (value & 0xFF00) | ((value + 1) & 0xFF))
            self.tstates += 8
        elif opcode == 0xE5:  # PUSH IX
            self._push16(value)
            self.tstates += 15
        elif opcode == 0xE1:  # POP IX
            setattr(self, name, self._pop16())
            self.tstates += 14
        elif opcode == 0xF9:  # LD SP,IX
            self.sp = value
            self.tstates += 10
        elif opcode == 0x36:  # LD (IX+d),n
            disp = self._fetch()
            imm = self._fetch()
            self.write(value + ((disp ^ 0x80) - 0x80), imm)
            self.tstates += 19
        elif 0x70 <= opcode <= 0x77 and opcode != 0x76:  # LD (IX+d),r
            disp = self._fetch()
            self.write(value + ((disp ^ 0x80) - 0x80), self._get_r(opcode & 7))
            self.tstates += 19
        elif opcode & 0xC7 == 0x46:  # LD r,(IX+d)
            disp = self._fetch()
            self._set_r((opcode >> 3) & 7, self.read(value + ((disp ^ 0x80) - 0x80)))
            self.tstates += 19
        else:
            raise UnsupportedOpcode(pc, opcode, prefix)


class Halt(Exception):
    """Raised internally when HALT is executed (used as a run terminator)."""


def run(
    cpu: Z80,
    start: int,
    *,
    stop: int | None = None,
    max_steps: int = 2_000_000,
    push_return: bool = True,
) -> int:
    """Run from ``start`` until control reaches ``stop`` (a sentinel address).

    By default the routine is entered as if by ``CALL``: the return address
    is pushed first, so a plain ``RET`` ends the run.  Callers that build
    their own stack frame (the list form, whose items sit above the return
    address) pass ``push_return=False``.  Returns the T-states consumed.
    """
    sentinel = 0xFFFE if stop is None else stop
    cpu.pc = start
    if push_return:
        cpu._push16(sentinel)
    before = cpu.tstates
    steps = 0
    try:
        while cpu.pc != sentinel:
            cpu.step()
            steps += 1
            if steps > max_steps:
                raise ExecutionLimit(f"exceeded {max_steps} instructions at {cpu.pc:#06x}")
    except Halt:
        pass
    return cpu.tstates - before


def run_steps(cpu: Z80, start: int, count: int) -> int:
    """Execute exactly ``count`` instructions from ``start``.

    Used for fragments that deliberately leave SP pointing into the screen
    (stack-mode writes), where a RET-terminated run makes no sense.
    """
    cpu.pc = start
    before = cpu.tstates
    for _ in range(count):
        cpu.step()
    return cpu.tstates - before
