"""Emulator-driven test bench for float16.z80s.

Assembles the library with sjasmplus, runs each routine on a real Z80
emulator, and compares the result against numpy's float16 arithmetic
(which is IEEE 754 round-to-nearest-even, the same thing the assembly
claims to implement).
"""
import os
import subprocess
import sys

import numpy as np
import z80

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SJASM = os.environ.get("SJASMPLUS", "sjasmplus")
ORG = 0x8000
RETADDR = 0x0000        # a HALT lives here, so RET ends the run
MEMOFF = 44             # where memory starts in the emulator state view
DRV_IN = 0xA000
DRV_OUT = 0xC000
BATCH = 2048            # pairs per emulator entry
FRAME = 100000          # the emulator's tick counter wraps at this


def zeus_shim(builddir):
    """Rewrite the Zeus-syntax multiply so sjasmplus can assemble it.

    8x8multiply_r16.z80s is written for Zeus, which spells modulo "\\"
    and accepts "SUB A,(HL)" for the one-operand SUB (sjasmplus reads
    that as two instructions). murmur3.z80s calls into the file, so the
    tests need a copy sjasmplus will take; nothing else changes.
    """
    src = open(os.path.join(ROOT, "8x8multiply_r16.z80s"),
               encoding="utf-8-sig").read()
    src = src.replace(" \\ 256", " % 256").replace("SUB  A,(HL)", "SUB  (HL)")
    os.makedirs(builddir, exist_ok=True)
    out = os.path.join(builddir, "mult8x8_sjasm.z80s")
    open(out, "w").write(src)
    return builddir


def assemble(harness="harness.asm", incdirs=(), here=None, root=None):
    """Assemble a harness. `here` is where the harness lives and `root`
    where its INCLUDEs are, both defaulting to this file's own directory
    and its parent - which is right for tests/ beside the sources.

    soundchip/tests/ passes its own pair: the sound routines moved with
    their tests, so their root is soundchip/ rather than the repository's.
    """
    here = here or HERE
    root = root or ROOT
    binf = "/tmp/%s.bin" % harness.replace(".asm", "")
    symf = "/tmp/%s.sym" % harness.replace(".asm", "")
    cmd = [SJASM, "--sym=" + symf, "--raw=" + binf, "-I" + root]
    cmd += ["-I" + d for d in incdirs]
    r = subprocess.run(cmd + [os.path.join(here, harness)],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stdout + r.stderr)
    syms = {}
    for line in open(symf):
        name, _, val = line.partition(":")
        if val.strip().startswith("EQU"):
            syms[name.strip()] = int(val.strip().split()[1], 16)
    return open(binf, "rb").read(), syms


class Bench:
    def __init__(self, harness="harness.asm", opsize=2, incdirs=(), org=ORG,
                 here=None, root=None):
        self.opsize = opsize            # bytes per operand (2 or 4)
        self.batchsize = BATCH if opsize == 2 else BATCH // 2
        code, self.syms = assemble(harness, incdirs, here, root)
        self.m = z80.Z80Machine()
        self.m.set_memory_block(org, code)
        self.m.set_memory_block(RETADDR, bytes([0x76]))     # HALT
        self.m.set_memory_block(0xFEFE, bytes([RETADDR & 0xFF, RETADDR >> 8]))
        self.view = self.m.get_state_view()
        self.m.set_breakpoint(RETADDR)      # so timing runs stop on return

    def call(self, entry, hl, de):
        m = self.m
        m.sp = 0xFEFE
        m.hl = hl
        m.de = de
        m.pc = entry
        m.halted = False
        for _ in range(400):       # generous: a long CRC run is millions of T
            m.ticks_to_stop = FRAME // 2   # so a run never spans a full wrap
            m.run()
            if m.pc == RETADDR:
                break
        else:
            raise RuntimeError("routine did not return (runaway loop?)")
        return m.hl

    def call_regs(self, entry, hl=0, de=0, bc=0):
        """Call a routine with HL/DE/BC set; returns (DE:HL, T-states)."""
        m = self.m
        m.bc = bc
        return self.fast_timed_call(entry, hl, de)[1], (m.de << 16) | m.hl

    def poke(self, addr, data):
        self.m.set_memory_block(addr, bytes(data))

    def peek(self, addr, n):
        return bytes(self.view[MEMOFF + addr:MEMOFF + addr + n])

    def poke32(self, a, b):
        """Put a pair of float32 operands in memory; returns their addresses."""
        self.m.set_memory_block(0x9800, a.to_bytes(4, "little")
                                        + b.to_bytes(4, "little"))
        return 0x9800, 0x9804

    def call32(self, entry, a, b):
        pa, pb = self.poke32(a, b)
        self.call(entry, pa, pb)
        return (self.m.de << 16) | self.m.hl

    def fast_timed_call32(self, entry, a, b):
        pa, pb = self.poke32(a, b)
        _, t = self.fast_timed_call(entry, pa, pb)
        return (self.m.de << 16) | self.m.hl, t

    def fast_timed_call(self, entry, hl, de):
        """T-states for one call, using a breakpoint on the return address.

        Same answer as timed_call, roughly forty times quicker, because
        the emulator is entered once instead of once per instruction.
        The tick counter wraps every FRAME ticks, hence the fixup.
        """
        m = self.m
        m.sp = 0xFEFE
        m.hl = hl
        m.de = de
        m.pc = entry
        m.halted = False
        total = 0
        prev = m.frame_tick
        for _ in range(400):       # generous: a long CRC run is millions of T
            m.ticks_to_stop = FRAME // 2   # so a run never spans a full wrap
            m.run()
            step = m.frame_tick - prev      # the counter wraps every FRAME,
            total += step + FRAME if step < 0 else step   # but a single run
            prev = m.frame_tick             # never spans more than one wrap
            if m.pc == RETADDR:
                break
        else:
            raise RuntimeError("routine did not return (runaway loop?)")
        return m.hl, total

    def timed_call(self, entry, hl, de):
        """Same, but single-stepped so the T-states can be totalled.

        The count runs from the first instruction of the routine to the
        RET inclusive: what the routine costs the caller, less the
        caller's own CALL. Stepping stops when control reaches the HALT
        rather than executing it, because executing a HALT resets the
        emulator's tick counter.
        """
        m = self.m
        m.sp = 0xFEFE
        m.hl = hl
        m.de = de
        m.pc = entry
        m.halted = False
        total = 0
        while m.pc != RETADDR:
            before = m.frame_tick
            m.ticks_to_stop = 1
            m.run()
            step = m.frame_tick - before
            total += step + FRAME if step < 0 else step
            if total > 100000:
                raise RuntimeError("routine did not return (runaway loop?)")
        return m.hl, total

    def batch(self, entry, pairs):
        """Run a whole list of (a, b) pairs through one routine.

        The driver in harness.asm walks an input buffer and writes the
        results out, so the emulator is entered once per BATCH pairs
        instead of once per operation.
        """
        m = self.m
        out = []
        n = self.opsize
        for base in range(0, len(pairs), self.batchsize):
            chunk = pairs[base:base + self.batchsize]
            buf = bytearray()
            for a, b in chunk:
                buf += a.to_bytes(n, "little") + b.to_bytes(n, "little")
            m.set_memory_block(DRV_IN, bytes(buf))
            m.set_memory_block(self.syms["drv_count"],
                               bytes([len(chunk) & 0xFF, len(chunk) >> 8]))
            m.set_memory_block(self.syms["drv_call"] + 1,
                               bytes([entry & 0xFF, entry >> 8]))
            m.sp = 0xFEFE
            m.pc = self.syms["drv_run"]
            m.halted = False
            for _ in range(1000):
                m.ticks_to_stop = 1000000
                m.run()
                if m.halted:
                    break
            else:
                raise RuntimeError("batch did not finish (runaway loop?)")
            raw = bytes(self.view[MEMOFF + DRV_OUT:
                                  MEMOFF + DRV_OUT + n * len(chunk)])
            out += [int.from_bytes(raw[i:i + n], "little")
                    for i in range(0, len(raw), n)]
        return out


OPS = {
    "add": ("f16_add", lambda a, b: a + b),
    "sub": ("f16_sub", lambda a, b: a - b),
    "mul": ("f16_mul", lambda a, b: a * b),
    "div": ("f16_div", lambda a, b: a / b),
}


# per width: exponent mask, fraction mask, numpy view type
MASKS = {16: (0x7C00, 0x03FF, np.uint16, np.float16),
         32: (0x7F800000, 0x007FFFFF, np.uint32, np.float32)}


def bits(x, width=16):
    _, _, uint, flt = MASKS[width]
    return int(flt(x).view(uint))


def as_f16(u):
    return np.uint16(u).view(np.float16)


def as_f32(u):
    return np.uint32(u).view(np.float32)


def as_float(u, width=16):
    _, _, uint, flt = MASKS[width]
    return uint(u).view(flt)


def reference(op, a, b, width=16):
    with np.errstate(all="ignore"):
        return bits(OPS[op][1](as_float(a, width), as_float(b, width)), width)


def isnan(u, width=16):
    expmask, fracmask, _, _ = MASKS[width]
    return (u & expmask) == expmask and (u & fracmask) != 0


def check(bench, op, pairs, label, width=16):
    entry = bench.syms[("f%d_" % width) + op]
    results = bench.batch(entry, pairs)
    bad = 0
    digits = width // 4
    for (a, b), got in zip(pairs, results):
        want = reference(op, a, b, width)
        # IEEE leaves the NaN payload to the implementation, so any NaN
        # answers for a NaN answer; everything else must match bit for bit.
        if got == want or (isnan(got, width) and isnan(want, width)):
            continue
        bad += 1
        if bad <= 10:
            print("  MISMATCH %s(%0*X,%0*X) = %0*X, want %0*X   (%r %s %r = %r)"
                  % (op, digits, a, digits, b, digits, got, digits, want,
                     as_float(a, width), op, as_float(b, width),
                     as_float(want, width)))
    print("  %-28s %8d cases, %d mismatches" % (label, len(pairs), bad))
    return bad
