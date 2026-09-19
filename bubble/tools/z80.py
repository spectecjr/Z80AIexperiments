#!/usr/bin/env python3
"""
z80.py - a Z80 CPU core, complete enough to run the Bubble Bobble
prototype in bubble/ and watch what it actually draws.

The bus is supplied by the caller: an object with rb/wb (memory) and
in_/out (ports). bubble/tools/sam.py provides the SAM Coupe one.

Register file follows the Z80's own encoding, r[0..7] = B C D E H L - A,
with index 6 standing for (HL) so the regular opcode blocks decode by
arithmetic rather than by a 256-way table.

Index prefixes are the fiddly part and are handled the way the hardware
does: DD/FD substitutes IX/IY for HL, but when the instruction ALSO has
an (IX+d) operand, its register operand means the REAL H or L. The
prototype relies on that - "LD H,(IX+O_CELLH)" loads the true H - so
this is modelled explicitly rather than by swapping registers.
"""

SF, ZF, YF, HF, XF, PF, NF, CF = 0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01

PARITY = [0] * 256
for _i in range(256):
    _p, _v = 0, _i
    while _v:
        _p ^= _v & 1
        _v >>= 1
    PARITY[_i] = PF if not _p else 0

SZ53 = [(_i & (SF | YF | XF)) | (ZF if _i == 0 else 0) for _i in range(256)]
SZ53P = [SZ53[_i] | PARITY[_i] for _i in range(256)]

B, C, D, E, H, L, M, A = range(8)


def s8(v):
    return v - 256 if v > 127 else v


class Z80:
    def __init__(self, bus):
        self.bus = bus
        self.r = [0] * 8
        self.f = 0
        self.r2 = [0] * 8
        self.f2 = 0
        self.ix = 0
        self.iy = 0
        self.sp = 0
        self.pc = 0
        self.i = 0
        self.rreg = 0
        self.iff1 = 0
        self.iff2 = 0
        self.im = 0
        self.halted = False
        self.t = 0

    # ---- bus -----------------------------------------------------
    def rb(self, a):
        return self.bus.rb(a & 0xFFFF)

    def wb(self, a, v):
        self.bus.wb(a & 0xFFFF, v & 0xFF)

    def rw(self, a):
        return self.rb(a) | (self.rb(a + 1) << 8)

    def ww(self, a, v):
        self.wb(a, v & 0xFF)
        self.wb(a + 1, v >> 8)

    def fetch(self):
        v = self.rb(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return v

    def fetchw(self):
        v = self.rw(self.pc)
        self.pc = (self.pc + 2) & 0xFFFF
        return v

    def push(self, v):
        self.sp = (self.sp - 2) & 0xFFFF
        self.ww(self.sp, v)

    def pop(self):
        v = self.rw(self.sp)
        self.sp = (self.sp + 2) & 0xFFFF
        return v

    # ---- register pairs -----------------------------------------
    def get_bc(self):
        return (self.r[B] << 8) | self.r[C]

    def set_bc(self, v):
        self.r[B] = (v >> 8) & 0xFF
        self.r[C] = v & 0xFF

    def get_de(self):
        return (self.r[D] << 8) | self.r[E]

    def set_de(self, v):
        self.r[D] = (v >> 8) & 0xFF
        self.r[E] = v & 0xFF

    def get_hl(self):
        return (self.r[H] << 8) | self.r[L]

    def set_hl(self, v):
        self.r[H] = (v >> 8) & 0xFF
        self.r[L] = v & 0xFF

    def get_af(self):
        return (self.r[A] << 8) | self.f

    def set_af(self, v):
        self.r[A] = (v >> 8) & 0xFF
        self.f = v & 0xFF

    # ---- 8-bit ALU ----------------------------------------------
    def add8(self, v, carry=0):
        a = self.r[A]
        res = a + v + carry
        self.f = (SZ53[res & 0xFF]
                  | (CF if res > 0xFF else 0)
                  | (HF if ((a & 15) + (v & 15) + carry) > 15 else 0)
                  | (PF if ((a ^ ~v) & (a ^ res) & 0x80) else 0))
        self.r[A] = res & 0xFF

    def sub8(self, v, carry=0, store=True):
        a = self.r[A]
        res = a - v - carry
        f = (SZ53[res & 0xFF] | NF
             | (CF if res < 0 else 0)
             | (HF if ((a & 15) - (v & 15) - carry) < 0 else 0)
             | (PF if ((a ^ v) & (a ^ res) & 0x80) else 0))
        if store:
            self.f = f
            self.r[A] = res & 0xFF
        else:
            # CP leaves the undocumented bits from the operand
            self.f = (f & ~(YF | XF)) | (v & (YF | XF))

    def and8(self, v):
        self.r[A] &= v
        self.f = SZ53P[self.r[A]] | HF

    def or8(self, v):
        self.r[A] |= v
        self.f = SZ53P[self.r[A]]

    def xor8(self, v):
        self.r[A] ^= v
        self.f = SZ53P[self.r[A]]

    def inc8(self, v):
        res = (v + 1) & 0xFF
        self.f = ((self.f & CF) | SZ53[res]
                  | (HF if (v & 15) == 15 else 0)
                  | (PF if v == 0x7F else 0))
        return res

    def dec8(self, v):
        res = (v - 1) & 0xFF
        self.f = ((self.f & CF) | SZ53[res] | NF
                  | (HF if (v & 15) == 0 else 0)
                  | (PF if v == 0x80 else 0))
        return res

    # ---- 16-bit ALU ---------------------------------------------
    def add16(self, x, y):
        res = x + y
        self.f = ((self.f & (SF | ZF | PF))
                  | ((res >> 8) & (YF | XF))
                  | (CF if res > 0xFFFF else 0)
                  | (HF if ((x & 0x0FFF) + (y & 0x0FFF)) > 0x0FFF else 0))
        return res & 0xFFFF

    def adc16(self, x, y):
        c = self.f & CF
        res = x + y + c
        r16 = res & 0xFFFF
        self.f = (((res >> 8) & (SF | YF | XF))
                  | (ZF if r16 == 0 else 0)
                  | (CF if res > 0xFFFF else 0)
                  | (HF if ((x & 0x0FFF) + (y & 0x0FFF) + c) > 0x0FFF else 0)
                  | (PF if ((x ^ ~y) & (x ^ res) & 0x8000) else 0))
        return r16

    def sbc16(self, x, y):
        c = self.f & CF
        res = x - y - c
        r16 = res & 0xFFFF
        self.f = (((res >> 8) & (SF | YF | XF))
                  | (ZF if r16 == 0 else 0) | NF
                  | (CF if res < 0 else 0)
                  | (HF if ((x & 0x0FFF) - (y & 0x0FFF) - c) < 0 else 0)
                  | (PF if ((x ^ y) & (x ^ res) & 0x8000) else 0))
        return r16

    # ---- rotates and shifts -------------------------------------
    def rlc(self, v):
        c = v >> 7
        v = ((v << 1) | c) & 0xFF
        self.f = SZ53P[v] | c
        return v

    def rrc(self, v):
        c = v & 1
        v = ((v >> 1) | (c << 7)) & 0xFF
        self.f = SZ53P[v] | c
        return v

    def rl(self, v):
        c = v >> 7
        v = ((v << 1) | (self.f & CF)) & 0xFF
        self.f = SZ53P[v] | c
        return v

    def rr(self, v):
        c = v & 1
        v = ((v >> 1) | ((self.f & CF) << 7)) & 0xFF
        self.f = SZ53P[v] | c
        return v

    def sla(self, v):
        c = v >> 7
        v = (v << 1) & 0xFF
        self.f = SZ53P[v] | c
        return v

    def sra(self, v):
        c = v & 1
        v = ((v >> 1) | (v & 0x80)) & 0xFF
        self.f = SZ53P[v] | c
        return v

    def sll(self, v):
        c = v >> 7
        v = ((v << 1) | 1) & 0xFF
        self.f = SZ53P[v] | c
        return v

    def srl(self, v):
        c = v & 1
        v = (v >> 1) & 0xFF
        self.f = SZ53P[v] | c
        return v

    # ---- conditions ---------------------------------------------
    def cond(self, i):
        f = self.f
        return (not f & ZF, f & ZF, not f & CF, f & CF,
                not f & PF, f & PF, not f & SF, f & SF)[i]

    # ---- interrupts ---------------------------------------------
    def interrupt(self):
        """Maskable interrupt. The prototype uses IM 1."""
        if not self.iff1:
            return False
        if self.halted:
            self.halted = False
            self.pc = (self.pc + 1) & 0xFFFF
        self.iff1 = self.iff2 = 0
        if self.im == 2:
            self.push(self.pc)
            self.pc = self.rw((self.i << 8) | 0xFF)
            self.t += 19
        else:
            self.push(self.pc)
            self.pc = 0x0038
            self.t += 13
        return True

    # ---- execution ----------------------------------------------
    def step(self):
        if self.halted:
            self.t += 4
            return
        self.rreg = (self.rreg + 1) & 0x7F
        op = self.fetch()
        if op == 0xDD:
            self.exec_indexed(False)
        elif op == 0xFD:
            self.exec_indexed(True)
        elif op == 0xED:
            self.exec_ed()
        elif op == 0xCB:
            self.exec_cb()
        else:
            self.exec_main(op, None)

    # Opcodes whose (HL) operand becomes (IX+d) under a DD/FD prefix.
    @staticmethod
    def touches_hl(op):
        if 0x40 <= op <= 0x7F:
            return (op & 7) == 6 or ((op >> 3) & 7) == 6
        if 0x80 <= op <= 0xBF:
            return (op & 7) == 6
        if op in (0x34, 0x35, 0x36):
            return True
        return False

    def exec_indexed(self, use_iy):
        self.rreg = (self.rreg + 1) & 0x7F
        op = self.fetch()
        idxval = self.iy if use_iy else self.ix
        if op == 0xCB:
            d = s8(self.fetch())
            sub = self.fetch()
            self.exec_ddcb(idxval, d, sub)
            return
        if op == 0xED:                         # DD ED behaves as plain ED
            self.exec_ed()
            return
        res = self.exec_main(op, idxval)
        if res is not None:
            if use_iy:
                self.iy = res
            else:
                self.ix = res

    def exec_ddcb(self, idxval, d, sub):
        addr = (idxval + d) & 0xFFFF
        v = self.rb(addr)
        kind = sub >> 6
        bit = (sub >> 3) & 7
        if kind == 1:                          # BIT
            self.f = ((self.f & CF) | HF
                      | (0 if v & (1 << bit) else (ZF | PF))
                      | (v & (YF | XF))
                      | (SF if bit == 7 and v & 0x80 else 0))
            self.t += 20
            return
        if kind == 2:
            v &= ~(1 << bit) & 0xFF
        elif kind == 3:
            v |= 1 << bit
        else:
            v = (self.rlc, self.rrc, self.rl, self.rr,
                 self.sla, self.sra, self.sll, self.srl)[bit](v)
        self.wb(addr, v)
        if (sub & 7) != 6:                     # undocumented: also to a reg
            self.r[(sub & 7)] = v
        self.t += 23

    def exec_cb(self):
        self.rreg = (self.rreg + 1) & 0x7F
        op = self.fetch()
        idx = op & 7
        kind = op >> 6
        bit = (op >> 3) & 7
        v = self.rb(self.get_hl()) if idx == M else self.r[idx]
        if kind == 1:
            self.f = ((self.f & CF) | HF
                      | (0 if v & (1 << bit) else (ZF | PF))
                      | (v & (YF | XF))
                      | (SF if bit == 7 and v & 0x80 else 0))
            self.t += 12 if idx == M else 8
            return
        if kind == 2:
            v &= ~(1 << bit) & 0xFF
        elif kind == 3:
            v |= 1 << bit
        else:
            v = (self.rlc, self.rrc, self.rl, self.rr,
                 self.sla, self.sra, self.sll, self.srl)[bit](v)
        if idx == M:
            self.wb(self.get_hl(), v)
            self.t += 15
        else:
            self.r[idx] = v
            self.t += 8

    def exec_ed(self):
        self.rreg = (self.rreg + 1) & 0x7F
        op = self.fetch()
        pair = (op >> 4) & 3
        getp = (self.get_bc, self.get_de, self.get_hl, lambda: self.sp)
        setp = (self.set_bc, self.set_de, self.set_hl,
                lambda v: setattr(self, "sp", v))

        if op & 0xCF == 0x4A:                  # ADC HL,rr
            self.set_hl(self.adc16(self.get_hl(), getp[pair]()))
            self.t += 15
        elif op & 0xCF == 0x42:                # SBC HL,rr
            self.set_hl(self.sbc16(self.get_hl(), getp[pair]()))
            self.t += 15
        elif op & 0xCF == 0x43:                # LD (nn),rr
            self.ww(self.fetchw(), getp[pair]())
            self.t += 20
        elif op & 0xCF == 0x4B:                # LD rr,(nn)
            setp[pair](self.rw(self.fetchw()))
            self.t += 20
        elif op & 0xC7 == 0x44:                # NEG
            v = self.r[A]
            self.r[A] = 0
            self.sub8(v)
            self.t += 8
        elif op & 0xC7 == 0x45:                # RETN / RETI
            self.iff1 = self.iff2
            self.pc = self.pop()
            self.t += 14
        elif op & 0xC7 == 0x46:                # IM n
            self.im = (0, 0, 1, 2)[((op >> 3) & 3)]
            self.t += 8
        elif op == 0x47:
            self.i = self.r[A]
            self.t += 9
        elif op == 0x4F:
            self.rreg = self.r[A] & 0x7F
            self.t += 9
        elif op == 0x57:
            self.r[A] = self.i
            self.f = (self.f & CF) | SZ53[self.i] | (PF if self.iff2 else 0)
            self.t += 9
        elif op == 0x5F:
            self.r[A] = self.rreg
            self.f = (self.f & CF) | SZ53[self.rreg] | (PF if self.iff2 else 0)
            self.t += 9
        elif op & 0xC7 == 0x40:                # IN r,(C)
            v = self.bus.in_(self.get_bc())
            self.f = (self.f & CF) | SZ53P[v]
            idx = (op >> 3) & 7
            if idx != M:
                self.r[idx] = v
            self.t += 12
        elif op & 0xC7 == 0x41:                # OUT (C),r
            idx = (op >> 3) & 7
            self.bus.out(self.get_bc(), 0 if idx == M else self.r[idx])
            self.t += 12
        elif op in (0xA0, 0xA8, 0xB0, 0xB8):   # LDI LDD LDIR LDDR
            self.block_ld(op)
        elif op in (0xA1, 0xA9, 0xB1, 0xB9):   # CPI CPD CPIR CPDR
            self.block_cp(op)
        elif op == 0x67:                       # RRD
            hl = self.get_hl()
            v = self.rb(hl)
            self.wb(hl, ((v >> 4) | (self.r[A] << 4)) & 0xFF)
            self.r[A] = (self.r[A] & 0xF0) | (v & 0x0F)
            self.f = (self.f & CF) | SZ53P[self.r[A]]
            self.t += 18
        elif op == 0x6F:                       # RLD
            hl = self.get_hl()
            v = self.rb(hl)
            self.wb(hl, ((v << 4) | (self.r[A] & 0x0F)) & 0xFF)
            self.r[A] = (self.r[A] & 0xF0) | (v >> 4)
            self.f = (self.f & CF) | SZ53P[self.r[A]]
            self.t += 18
        else:
            self.t += 8                        # documented no-ops

    def block_ld(self, op):
        dec = op & 0x08
        rep = op & 0x10
        hl, de, bc = self.get_hl(), self.get_de(), self.get_bc()
        v = self.rb(hl)
        self.wb(de, v)
        step = -1 if dec else 1
        self.set_hl((hl + step) & 0xFFFF)
        self.set_de((de + step) & 0xFFFF)
        bc = (bc - 1) & 0xFFFF
        self.set_bc(bc)
        n = (v + self.r[A]) & 0xFF
        self.f = ((self.f & (SF | ZF | CF))
                  | (YF if n & 0x02 else 0) | (XF if n & 0x08 else 0)
                  | (PF if bc else 0))
        if rep and bc:
            self.pc = (self.pc - 2) & 0xFFFF
            self.t += 21
        else:
            self.t += 16

    def block_cp(self, op):
        dec = op & 0x08
        rep = op & 0x10
        hl, bc = self.get_hl(), self.get_bc()
        v = self.rb(hl)
        res = (self.r[A] - v) & 0xFF
        half = HF if ((self.r[A] & 15) - (v & 15)) < 0 else 0
        self.set_hl((hl - 1 if dec else hl + 1) & 0xFFFF)
        bc = (bc - 1) & 0xFFFF
        self.set_bc(bc)
        n = (res - (1 if half else 0)) & 0xFF
        self.f = ((self.f & CF) | NF | half
                  | (SZ53[res] & (SF | ZF))
                  | (YF if n & 0x02 else 0) | (XF if n & 0x08 else 0)
                  | (PF if bc else 0))
        if rep and bc and res:
            self.pc = (self.pc - 2) & 0xFFFF
            self.t += 21
        else:
            self.t += 16

    # ---- the main opcode block ----------------------------------
    def exec_main(self, op, idxval):
        """Returns the new index-register value when idxval was supplied."""
        r = self.r
        indexed = idxval is not None
        # Under DD/FD, H and L mean IXH/IXL - unless the instruction also
        # has an (IX+d) operand, in which case they mean the real H and L.
        mem_operand = indexed and self.touches_hl(op)
        sub_hl = indexed and not mem_operand
        addr = None
        if mem_operand:
            addr = (idxval + s8(self.fetch())) & 0xFFFF

        def get(i):
            if i == M:
                return self.rb(addr if mem_operand else self.get_hl())
            if sub_hl and i == H:
                return (idxval >> 8) & 0xFF
            if sub_hl and i == L:
                return idxval & 0xFF
            return r[i]

        def put(i, v):
            nonlocal idxval
            if i == M:
                self.wb(addr if mem_operand else self.get_hl(), v)
            elif sub_hl and i == H:
                idxval = ((v & 0xFF) << 8) | (idxval & 0xFF)
            elif sub_hl and i == L:
                idxval = (idxval & 0xFF00) | (v & 0xFF)
            else:
                r[i] = v & 0xFF

        def get_hl16():
            return idxval if indexed else self.get_hl()

        def set_hl16(v):
            nonlocal idxval
            if indexed:
                idxval = v & 0xFFFF
            else:
                self.set_hl(v)

        extra = 8 if indexed else 0

        if op == 0x76:                                  # HALT
            self.halted = True
            self.t += 4
        elif 0x40 <= op <= 0x7F:                         # LD r,r'
            src, dst = op & 7, (op >> 3) & 7
            put(dst, get(src))
            self.t += (7 if (src == M or dst == M) else 4) + extra
            if mem_operand:
                self.t += 12
        elif 0x80 <= op <= 0xBF:                         # ALU A,r
            v = get(op & 7)
            kind = (op >> 3) & 7
            if kind == 0:
                self.add8(v)
            elif kind == 1:
                self.add8(v, self.f & CF)
            elif kind == 2:
                self.sub8(v)
            elif kind == 3:
                self.sub8(v, self.f & CF)
            elif kind == 4:
                self.and8(v)
            elif kind == 5:
                self.xor8(v)
            elif kind == 6:
                self.or8(v)
            else:
                self.sub8(v, 0, store=False)
            self.t += (7 if (op & 7) == M else 4) + extra
            if mem_operand:
                self.t += 12
        elif op & 0xC7 == 0x04:                          # INC r
            i = (op >> 3) & 7
            put(i, self.inc8(get(i)))
            self.t += (11 if i == M else 4) + extra
            if mem_operand:
                self.t += 12
        elif op & 0xC7 == 0x05:                          # DEC r
            i = (op >> 3) & 7
            put(i, self.dec8(get(i)))
            self.t += (11 if i == M else 4) + extra
            if mem_operand:
                self.t += 12
        elif op & 0xC7 == 0x06:                          # LD r,n
            i = (op >> 3) & 7
            put(i, self.fetch())
            self.t += (10 if i == M else 7) + extra
            if mem_operand:
                self.t += 9
        elif op & 0xCF == 0x01:                          # LD rr,nn
            v = self.fetchw()
            p = (op >> 4) & 3
            if p == 0:
                self.set_bc(v)
            elif p == 1:
                self.set_de(v)
            elif p == 2:
                set_hl16(v)
            else:
                self.sp = v
            self.t += 10 + extra
        elif op & 0xCF == 0x09:                          # ADD HL,rr
            p = (op >> 4) & 3
            v = (self.get_bc(), self.get_de(), get_hl16(), self.sp)[p]
            set_hl16(self.add16(get_hl16(), v))
            self.t += 11 + extra
        elif op & 0xCF == 0x03:                          # INC rr
            p = (op >> 4) & 3
            if p == 0:
                self.set_bc((self.get_bc() + 1) & 0xFFFF)
            elif p == 1:
                self.set_de((self.get_de() + 1) & 0xFFFF)
            elif p == 2:
                set_hl16((get_hl16() + 1) & 0xFFFF)
            else:
                self.sp = (self.sp + 1) & 0xFFFF
            self.t += 6 + extra
        elif op & 0xCF == 0x0B:                          # DEC rr
            p = (op >> 4) & 3
            if p == 0:
                self.set_bc((self.get_bc() - 1) & 0xFFFF)
            elif p == 1:
                self.set_de((self.get_de() - 1) & 0xFFFF)
            elif p == 2:
                set_hl16((get_hl16() - 1) & 0xFFFF)
            else:
                self.sp = (self.sp - 1) & 0xFFFF
            self.t += 6 + extra
        elif op == 0x02:
            self.wb(self.get_bc(), r[A]); self.t += 7
        elif op == 0x12:
            self.wb(self.get_de(), r[A]); self.t += 7
        elif op == 0x0A:
            r[A] = self.rb(self.get_bc()); self.t += 7
        elif op == 0x1A:
            r[A] = self.rb(self.get_de()); self.t += 7
        elif op == 0x22:                                 # LD (nn),HL
            self.ww(self.fetchw(), get_hl16()); self.t += 16 + extra
        elif op == 0x2A:                                 # LD HL,(nn)
            set_hl16(self.rw(self.fetchw())); self.t += 16 + extra
        elif op == 0x32:
            self.wb(self.fetchw(), r[A]); self.t += 13
        elif op == 0x3A:
            r[A] = self.rb(self.fetchw()); self.t += 13
        elif op == 0x00:
            self.t += 4
        elif op == 0x07:
            c = r[A] >> 7
            r[A] = ((r[A] << 1) | c) & 0xFF
            self.f = (self.f & (SF | ZF | PF)) | (r[A] & (YF | XF)) | c
            self.t += 4
        elif op == 0x0F:
            c = r[A] & 1
            r[A] = ((r[A] >> 1) | (c << 7)) & 0xFF
            self.f = (self.f & (SF | ZF | PF)) | (r[A] & (YF | XF)) | c
            self.t += 4
        elif op == 0x17:
            c = r[A] >> 7
            r[A] = ((r[A] << 1) | (self.f & CF)) & 0xFF
            self.f = (self.f & (SF | ZF | PF)) | (r[A] & (YF | XF)) | c
            self.t += 4
        elif op == 0x1F:
            c = r[A] & 1
            r[A] = ((r[A] >> 1) | ((self.f & CF) << 7)) & 0xFF
            self.f = (self.f & (SF | ZF | PF)) | (r[A] & (YF | XF)) | c
            self.t += 4
        elif op == 0x27:                                 # DAA
            a = r[A]
            corr = 0
            if (a & 15) > 9 or self.f & HF:
                corr |= 6
            if a > 0x99 or self.f & CF:
                corr |= 0x60
            carry = CF if (a > 0x99 or self.f & CF) else 0
            if self.f & NF:
                half = HF if (self.f & HF) and (a & 15) < 6 else 0
                a = (a - corr) & 0xFF
            else:
                half = HF if ((a & 15) + (corr & 15)) > 15 else 0
                a = (a + corr) & 0xFF
            r[A] = a
            self.f = (self.f & NF) | SZ53P[a] | carry | half
            self.t += 4
        elif op == 0x2F:
            r[A] ^= 0xFF
            self.f = (self.f & (SF | ZF | PF | CF)) | HF | NF | (r[A] & (YF | XF))
            self.t += 4
        elif op == 0x37:
            self.f = (self.f & (SF | ZF | PF)) | CF | (r[A] & (YF | XF))
            self.t += 4
        elif op == 0x3F:
            c = self.f & CF
            self.f = ((self.f & (SF | ZF | PF)) | (HF if c else 0)
                      | (0 if c else CF) | (r[A] & (YF | XF)))
            self.t += 4
        elif op == 0x08:                                 # EX AF,AF'
            self.r[A], self.r2[A] = self.r2[A], self.r[A]
            self.f, self.f2 = self.f2, self.f
            self.t += 4
        elif op == 0xD9:                                 # EXX
            for i in (B, C, D, E, H, L):
                r[i], self.r2[i] = self.r2[i], r[i]
            self.t += 4
        elif op == 0xEB:                                 # EX DE,HL
            d, e = r[D], r[E]
            r[D], r[E] = r[H], r[L]
            r[H], r[L] = d, e
            self.t += 4
        elif op == 0xE3:                                 # EX (SP),HL
            v = self.rw(self.sp)
            self.ww(self.sp, get_hl16())
            set_hl16(v)
            self.t += 19 + extra
        elif op == 0x18:                                 # JR d
            d = s8(self.fetch())
            self.pc = (self.pc + d) & 0xFFFF
            self.t += 12
        elif op & 0xE7 == 0x20:                          # JR cc,d
            d = s8(self.fetch())
            if self.cond((op >> 3) & 3):
                self.pc = (self.pc + d) & 0xFFFF
                self.t += 12
            else:
                self.t += 7
        elif op == 0x10:                                 # DJNZ
            d = s8(self.fetch())
            r[B] = (r[B] - 1) & 0xFF
            if r[B]:
                self.pc = (self.pc + d) & 0xFFFF
                self.t += 13
            else:
                self.t += 8
        elif op == 0xC3:
            self.pc = self.fetchw(); self.t += 10
        elif op & 0xC7 == 0xC2:                          # JP cc,nn
            v = self.fetchw()
            if self.cond((op >> 3) & 7):
                self.pc = v
            self.t += 10
        elif op == 0xE9:
            self.pc = get_hl16(); self.t += 4 + extra
        elif op == 0xCD:
            v = self.fetchw()
            self.push(self.pc)
            self.pc = v
            self.t += 17
        elif op & 0xC7 == 0xC4:                          # CALL cc,nn
            v = self.fetchw()
            if self.cond((op >> 3) & 7):
                self.push(self.pc)
                self.pc = v
                self.t += 17
            else:
                self.t += 10
        elif op == 0xC9:
            self.pc = self.pop(); self.t += 10
        elif op & 0xC7 == 0xC0:                          # RET cc
            if self.cond((op >> 3) & 7):
                self.pc = self.pop()
                self.t += 11
            else:
                self.t += 5
        elif op & 0xC7 == 0xC7:                          # RST
            self.push(self.pc)
            self.pc = op & 0x38
            self.t += 11
        elif op & 0xCF == 0xC5:                          # PUSH rr
            p = (op >> 4) & 3
            self.push((self.get_bc(), self.get_de(), get_hl16(), self.get_af())[p])
            self.t += 11 + extra
        elif op & 0xCF == 0xC1:                          # POP rr
            v = self.pop()
            p = (op >> 4) & 3
            if p == 0:
                self.set_bc(v)
            elif p == 1:
                self.set_de(v)
            elif p == 2:
                set_hl16(v)
            else:
                self.set_af(v)
            self.t += 10 + extra
        elif op == 0xF9:
            self.sp = get_hl16(); self.t += 6 + extra
        elif op & 0xC7 == 0xC6:                          # ALU A,n
            v = self.fetch()
            kind = (op >> 3) & 7
            if kind == 0:
                self.add8(v)
            elif kind == 1:
                self.add8(v, self.f & CF)
            elif kind == 2:
                self.sub8(v)
            elif kind == 3:
                self.sub8(v, self.f & CF)
            elif kind == 4:
                self.and8(v)
            elif kind == 5:
                self.xor8(v)
            elif kind == 6:
                self.or8(v)
            else:
                self.sub8(v, 0, store=False)
            self.t += 7
        elif op == 0xD3:
            self.bus.out((r[A] << 8) | self.fetch(), r[A]); self.t += 11
        elif op == 0xDB:
            r[A] = self.bus.in_((r[A] << 8) | self.fetch()); self.t += 11
        elif op == 0xF3:
            self.iff1 = self.iff2 = 0; self.t += 4
        elif op == 0xFB:
            self.iff1 = self.iff2 = 1; self.t += 4
        else:
            raise RuntimeError("unimplemented opcode %02X at %04X"
                               % (op, (self.pc - 1) & 0xFFFF))

        return idxval if indexed else None
