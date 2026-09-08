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


def assemble():
    binf = "/tmp/f16_bench.bin"
    symf = "/tmp/f16_bench.sym"
    r = subprocess.run([SJASM, "--sym=" + symf, "--raw=" + binf, "-I" + ROOT,
                        os.path.join(HERE, "harness.asm")],
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
    def __init__(self):
        code, self.syms = assemble()
        self.m = z80.Z80Machine()
        self.m.set_memory_block(ORG, code)
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
        m.ticks_to_stop = 100000
        m.run()
        if not m.halted:
            raise RuntimeError("routine did not return (runaway loop?)")
        return m.hl

    def fast_timed_call(self, entry, hl, de):
        """T-states for one call, using a breakpoint on the return address.

        Same answer as timed_call, roughly forty times quicker, because
        the emulator is entered once instead of once per instruction.
        The tick counter wraps every FRAME ticks, hence the fixup.
        """
        m = self.m
        before = m.frame_tick
        m.sp = 0xFEFE
        m.hl = hl
        m.de = de
        m.pc = entry
        m.halted = False
        for _ in range(10):
            m.ticks_to_stop = FRAME
            m.run()
            if m.pc == RETADDR:
                break
        else:
            raise RuntimeError("routine did not return (runaway loop?)")
        used = m.frame_tick - before
        return m.hl, used + FRAME if used < 0 else used

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
        for base in range(0, len(pairs), BATCH):
            chunk = pairs[base:base + BATCH]
            buf = bytearray()
            for a, b in chunk:
                buf += bytes([a & 0xFF, a >> 8, b & 0xFF, b >> 8])
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
                                  MEMOFF + DRV_OUT + 2 * len(chunk)])
            out += [raw[i] | (raw[i + 1] << 8) for i in range(0, len(raw), 2)]
        return out


OPS = {
    "add": ("f16_add", lambda a, b: a + b),
    "sub": ("f16_sub", lambda a, b: a - b),
    "mul": ("f16_mul", lambda a, b: a * b),
    "div": ("f16_div", lambda a, b: a / b),
}


def bits(x):
    return int(np.float16(x).view(np.uint16))


def as_f16(u):
    return np.uint16(u).view(np.float16)


def reference(op, a, b):
    with np.errstate(all="ignore"):
        return bits(OPS[op][1](as_f16(a), as_f16(b)))


def isnan(u):
    return (u & 0x7C00) == 0x7C00 and (u & 0x03FF) != 0


def check(bench, op, pairs, label):
    entry = bench.syms[OPS[op][0]]
    results = bench.batch(entry, pairs)
    bad = 0
    for (a, b), got in zip(pairs, results):
        want = reference(op, a, b)
        # IEEE leaves the NaN payload to the implementation, so any NaN
        # answers for a NaN answer; everything else must match bit for bit.
        if got == want or (isnan(got) and isnan(want)):
            continue
        bad += 1
        if bad <= 10:
            print("  MISMATCH %s(%04X,%04X) = %04X, want %04X   (%r %s %r = %r)"
                  % (op, a, b, got, want, as_f16(a), op, as_f16(b), as_f16(want)))
    print("  %-28s %8d cases, %d mismatches" % (label, len(pairs), bad))
    return bad
