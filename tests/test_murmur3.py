#!/usr/bin/env python3
"""Verify murmur3.z80s on an emulated Z80.

Checks the 64x64 multiply, the hash itself against a reference model of
MurmurHash3_x64_128 (cross-checked against the mmh3 package when it is
installed), and both Kirsch-Mitzenmacher index routines.

    pip install z80 [mmh3]
    python3 tests/test_murmur3.py [--quick]

Needs sjasmplus on PATH (or in $SJASMPLUS).
"""
import os
import random
import sys
import tempfile

from bench import Bench, zeus_shim

DATA = 0xA000           # where the bench puts the string
OUT = 0xB000            # where the index routines write
M64 = (1 << 64) - 1

try:
    import mmh3
except ImportError:
    mmh3 = None


# --- reference implementation, straight from Appleby's source ---------

def _rotl(x, r):
    return ((x << r) | (x >> (64 - r))) & M64


def _fmix(k):
    k ^= k >> 33
    k = (k * 0xFF51AFD7ED558CCD) & M64
    k ^= k >> 33
    k = (k * 0xC4CEB9FE1A85EC53) & M64
    k ^= k >> 33
    return k


def murmur3_x64_128(data, seed=0):
    c1, c2 = 0x87C37B91114253D5, 0x4CF5AD432745937F
    h1 = h2 = seed & M64
    nblocks = len(data) // 16
    for i in range(nblocks):
        k1 = int.from_bytes(data[i * 16:i * 16 + 8], "little")
        k2 = int.from_bytes(data[i * 16 + 8:i * 16 + 16], "little")
        k1 = (k1 * c1) & M64
        k1 = _rotl(k1, 31)
        k1 = (k1 * c2) & M64
        h1 ^= k1
        h1 = _rotl(h1, 27)
        h1 = (h1 + h2) & M64
        h1 = (h1 * 5 + 0x52DCE729) & M64
        k2 = (k2 * c2) & M64
        k2 = _rotl(k2, 33)
        k2 = (k2 * c1) & M64
        h2 ^= k2
        h2 = _rotl(h2, 31)
        h2 = (h2 + h1) & M64
        h2 = (h2 * 5 + 0x38495AB5) & M64
    tail = data[nblocks * 16:]
    k1 = int.from_bytes(tail[:8].ljust(8, b"\0"), "little")
    k2 = int.from_bytes(tail[8:].ljust(8, b"\0"), "little")
    if len(tail) > 8:
        k2 = (k2 * c2) & M64
        k2 = _rotl(k2, 33)
        k2 = (k2 * c1) & M64
        h2 ^= k2
    if len(tail) > 0:
        k1 = (k1 * c1) & M64
        k1 = _rotl(k1, 31)
        k1 = (k1 * c2) & M64
        h1 ^= k1
    h1 ^= len(data)
    h2 ^= len(data)
    h1 = (h1 + h2) & M64
    h2 = (h2 + h1) & M64
    h1, h2 = _fmix(h1), _fmix(h2)
    h1 = (h1 + h2) & M64
    h2 = (h2 + h1) & M64
    return h1, h2


class Murmur:
    def __init__(self):
        build = zeus_shim(os.path.join(tempfile.gettempdir(), "z80build"))
        self.b = Bench("harness_mh3.asm", incdirs=(build,))
        self.s = self.b.syms

    def hash(self, data, seed=0):
        self.b.poke(self.s["mh3_seed"], seed.to_bytes(4, "little"))
        self.b.poke(DATA, data)
        t, _ = self.b.call_regs(self.s["murmur3_64"], hl=DATA, bc=len(data))
        raw = self.b.peek(self.s["mh3_h1"], 16)
        return (int.from_bytes(raw[:8], "little"),
                int.from_bytes(raw[8:], "little"), t)

    def mul64(self, x, y):
        self.b.poke(0x9000, x.to_bytes(8, "little"))
        self.b.poke(0x9008, y.to_bytes(8, "little"))
        t, _ = self.b.call_regs(self.s["mh3_mul64"], hl=0x9000, de=0x9008)
        return int.from_bytes(self.b.peek(0x9000, 8), "little"), t

    def indices(self, entry, arg):
        t, _ = self.b.call_regs(self.s[entry], hl=OUT, de=arg, bc=arg)
        raw = self.b.peek(OUT, 26)
        return [raw[i] | (raw[i + 1] << 8) for i in range(0, 26, 2)], t


def main():
    quick = "--quick" in sys.argv
    rng = random.Random(20260908)
    mh = Murmur()
    scale = 1 if quick else 5
    print("library is %d bytes plus an %d byte workspace; it also needs "
          "mult8x8_16\n" % (mh.s["mh3_seed"] - mh.s["murmur3_64"],
                            mh.s["mh3_end"] - mh.s["mh3_seed"]))
    bad = 0

    # --- the 8x8 multiply it leans on, over every possible pair ------
    e = mh.s["mult8x8_16"]
    n = 0
    for x in range(256):
        for y in range(256):
            _, r = mh.b.call_regs(e, bc=(x << 8) | y)
            if ((r >> 16) & 0xFFFF) != x * y:
                n += 1
    bad += n
    print("  %-34s %7d cases, %d mismatches" % ("mult8x8_16, exhaustive",
                                                65536, n))

    # --- the 64x64 multiply -----------------------------------------
    cases = [(0, 0), (1, 1), (M64, M64), (M64, 1), (0x87C37B91114253D5, 3),
             (1 << 63, 2), (0xFFFFFFFF, 0xFFFFFFFF)]
    cases += [(rng.randrange(1 << 64), rng.randrange(1 << 64))
              for _ in range(400 * scale)]
    n = 0
    for x, y in cases:
        got, _ = mh.mul64(x, y)
        if got != (x * y) & M64:
            n += 1
            if n <= 5:
                print("  MISMATCH %016x * %016x = %016x, want %016x"
                      % (x, y, got, (x * y) & M64))
    bad += n
    print("  %-34s %7d cases, %d mismatches" % ("mh3_mul64", len(cases), n))

    # --- the hash ----------------------------------------------------
    if mmh3:
        n = 0
        for _ in range(200):
            d = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 70)))
            s = rng.randrange(1 << 32)
            if murmur3_x64_128(d, s) != mmh3.hash64(d, s, signed=False):
                n += 1
        bad += n
        print("  %-34s %7d cases, %d mismatches"
              % ("reference model vs mmh3", 200, n))
    else:
        print("  (mmh3 not installed - the reference model is unchecked)")

    lengths = list(range(0, 40)) + [47, 48, 49, 63, 64, 65, 100, 127, 128,
                                    129, 255, 256, 257]
    n = 0
    checked = 0
    for length in lengths:
        for _ in range(2 * scale):
            d = bytes(rng.randrange(256) for _ in range(length))
            s = rng.choice((0, 1, 0xFFFFFFFF, rng.randrange(1 << 32)))
            h1, h2, _ = mh.hash(d, s)
            checked += 1
            if (h1, h2) != murmur3_x64_128(d, s):
                n += 1
                if n <= 5:
                    w = murmur3_x64_128(d, s)
                    print("  MISMATCH len %d seed %08x: %016x %016x, want "
                          "%016x %016x" % (length, s, h1, h2, w[0], w[1]))
    bad += n
    print("  %-34s %7d cases, %d mismatches"
          % ("murmur3_64, lengths 0..257", checked, n))

    # --- Kirsch-Mitzenmacher ----------------------------------------
    n = 0
    for _ in range(40 * scale):
        d = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 40)))
        h1, h2, _ = mh.hash(d)
        bits = rng.randrange(1, 17)
        m = 1 << bits
        got, _ = mh.indices("mh3_km13", m - 1)
        want = [((h1 + i * h2) & M64) % m for i in range(13)]
        if got != want:
            n += 1
            if n <= 3:
                print("  MISMATCH km13 m=%d: %s want %s" % (m, got, want))
    bad += n
    print("  %-34s %7d cases, %d mismatches"
          % ("mh3_km13, power-of-two sizes", 40 * scale, n))

    n = 0
    for _ in range(20 * scale):
        d = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 40)))
        h1, h2, _ = mh.hash(d)
        m = rng.choice((3, 7, 1009, 4093, 10007, 65521, rng.randrange(2, 65536)))
        got, _ = mh.indices("mh3_km13_mod", m)
        want = [((h1 + i * h2) & M64) % m for i in range(13)]
        if got != want:
            n += 1
            if n <= 3:
                print("  MISMATCH km13_mod m=%d: %s want %s" % (m, got, want))
    bad += n
    print("  %-34s %7d cases, %d mismatches"
          % ("mh3_km13_mod, arbitrary sizes", 20 * scale, n))

    # --- timings -----------------------------------------------------
    print()
    for length in (0, 1, 8, 16, 32, 64, 128, 256):
        d = bytes(rng.randrange(256) for _ in range(length))
        _, _, t = mh.hash(d)
        print("  murmur3_64, %3d byte string   %8d T-states%s"
              % (length, t, "" if length == 0 else
                 "  (%d per byte)" % (t // max(length, 1))))
    _, t = mh.mul64(0x0123456789ABCDEF, 0xFEDCBA9876543210)
    print("  mh3_mul64                     %8d T-states" % t)
    _, t = mh.indices("mh3_km13", 0xFFFF)
    print("  mh3_km13 (13 indices)         %8d T-states" % t)
    _, t = mh.indices("mh3_km13_mod", 65521)
    print("  mh3_km13_mod (13 indices)     %8d T-states" % t)

    print("\n%s" % ("ALL TESTS PASSED" if bad == 0 else "FAILURES: %d" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
