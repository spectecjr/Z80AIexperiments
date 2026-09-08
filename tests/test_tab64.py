#!/usr/bin/env python3
"""Verify and measure tab64.z80s on an emulated Z80.

Correctness is against a Python model of the same construction, and
the assembled tables are checked against the generator that produced
them. --quality additionally runs the statistical comparison against
MurmurHash3 that the header quotes: avalanche, collisions, an
end-to-end Bloom filter, and a chi-square on the index distribution.

    pip install z80
    python3 tests/test_tab64.py [--quality]

Needs sjasmplus on PATH (or in $SJASMPLUS).
"""
import collections
import math
import random
import sys

from bench import Bench

DATA, OUT = 0xA000, 0xB000
M32 = 0xFFFFFFFF
M64 = (1 << 64) - 1


# --- the model -------------------------------------------------------

def splitmix64(x):
    x = (x + 0x9E3779B97F4A7C15) & M64
    z = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & M64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & M64
    return z ^ (z >> 31)


TAB = [[splitmix64(lane * 0x1000 + i + 1) & M32 for i in range(256)]
       for lane in (0, 1)]
INIT = [splitmix64(0xA5A5A5A5) & M32, splitmix64(0x5A5A5A5A) & M32]


def lane_hash(data, lane, seed=0):
    T = TAB[lane]
    h = (INIT[lane] ^ seed) & M32
    for b in data:
        h = (h >> 8) ^ T[(h ^ b) & 0xFF]
    for b in (len(data) & 0xFF, (len(data) >> 8) & 0xFF):
        h = (h >> 8) ^ T[(h ^ b) & 0xFF]
    for _ in range(4):
        h = (h >> 8) ^ T[h & 0xFF]
    return h


def tab64(data, seed=0):
    return (lane_hash(data, 1, seed) << 32) | lane_hash(data, 0, seed)


def main():
    quality = "--quality" in sys.argv
    rng = random.Random(20260908)
    b = Bench("harness_tab.asm")
    s = b.syms
    print("library is %d bytes: %d of code, 2048 of tables, %d of workspace\n"
          % (s["tab64_end"] - s["tab64"], s["tab_t0"] - s["tab64"],
             s["tab64_end"] - s["tab64_seed"]))
    bad = 0

    # --- the tables in the binary are the ones the generator makes ---
    n = 0
    for lane in (0, 1):
        page = s["tab_t%d" % lane]
        for byte in range(4):
            got = b.peek(page + 256 * byte, 256)
            want = bytes((TAB[lane][i] >> (8 * byte)) & 0xFF for i in range(256))
            if got != want:
                n += 1
    for lane in (0, 1):
        if b.peek(s["tab_i%d" % lane], 4) != INIT[lane].to_bytes(4, "little"):
            n += 1
    bad += n
    print("  %-34s %7d checks, %d wrong" % ("tables match the generator", 10, n))

    # --- the hash ----------------------------------------------------
    def zhash(data, seed=0):
        b.poke(s["tab64_seed"], seed.to_bytes(4, "little"))
        b.poke(DATA, data)
        t, _ = b.call_regs(s["tab64"], hl=DATA, bc=len(data))
        return int.from_bytes(b.peek(s["tab64_h"], 8), "little"), t

    lengths = list(range(0, 40)) + [63, 64, 65, 127, 128, 129, 255, 256, 257,
                                    511, 512, 513, 1000, 4096]
    n = checked = 0
    for length in lengths:
        for _ in range(3):
            d = bytes(rng.randrange(256) for _ in range(length))
            seed = rng.choice((0, 1, 0xFFFFFFFF, rng.randrange(1 << 32)))
            got, _ = zhash(d, seed)
            checked += 1
            if got != tab64(d, seed):
                n += 1
                if n <= 5:
                    print("  MISMATCH len %d seed %08x: %016x, want %016x"
                          % (length, seed, got, tab64(d, seed)))
    bad += n
    print("  %-34s %7d cases, %d mismatches"
          % ("tab64 against the model", checked, n))

    # --- the indices --------------------------------------------------
    n = 0
    for _ in range(60):
        d = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 40)))
        h, _ = zhash(d)
        h1, h2 = h & M32, h >> 32
        m = 1 << rng.randrange(1, 17)
        t, _ = b.call_regs(s["tab64_km13"], hl=OUT, de=m - 1)
        raw = b.peek(OUT, 26)
        got = [raw[i] | (raw[i + 1] << 8) for i in range(0, 26, 2)]
        want = [(h1 + i * h2) % m for i in range(13)]
        if got != want:
            n += 1
            if n <= 3:
                print("  MISMATCH km13 m=%d: %s want %s" % (m, got, want))
    bad += n
    print("  %-34s %7d cases, %d mismatches" % ("tab64_km13", 60, n))

    # --- timings ------------------------------------------------------
    print()
    prev = None
    for length in (0, 1, 5, 8, 16, 32, 64, 128, 256):
        d = bytes(rng.randrange(256) for _ in range(length))
        _, t = zhash(d)
        extra = "" if prev is None else "  (%.1fT per byte)" % ((t - prev[1]) /
                                                               (length - prev[0]))
        print("  tab64, %4d byte string     %8d T-states%s" % (length, t, extra))
        prev = (length, t)
    t, _ = b.call_regs(s["tab64_km13"], hl=OUT, de=0xFFFF)
    print("  tab64_km13 (13 indices)     %8d T-states" % t)

    # --- statistical quality, against murmur3 -------------------------
    if quality:
        from test_murmur3 import murmur3_x64_128

        def mm(data, seed=0):
            return murmur3_x64_128(bytes(data), seed)[0]

        def avalanche(fn, nkeys, klen):
            r = random.Random(7)
            counts = [0] * 64
            trials = 0
            for _ in range(nkeys):
                key = bytearray(r.randrange(256) for _ in range(klen))
                h0 = fn(bytes(key))
                for bit in range(klen * 8):
                    key[bit // 8] ^= 1 << (bit % 8)
                    d = h0 ^ fn(bytes(key))
                    key[bit // 8] ^= 1 << (bit % 8)
                    for o in range(64):
                        counts[o] += (d >> o) & 1
                    trials += 1
            p = [c / trials for c in counts]
            return min(p), max(p)

        print()
        for name, fn in (("murmur3", mm), ("tab64", tab64)):
            lo, hi = avalanche(fn, 400, 12)
            print("  avalanche, %-8s per output bit  %.4f .. %.4f "
                  "(0.5 is ideal)" % (name, lo, hi))

        def keysets():
            yield ("60,000 sequential u32",
                   [i.to_bytes(4, "little") for i in range(60000)])
            yield ("60,000 formatted strings",
                   [("key%05d" % i).encode() for i in range(60000)])
            yield ("every 3-letter word",
                   [bytes([x, y, z]) for x in range(97, 123)
                    for y in range(97, 123) for z in range(97, 123)])
            r = random.Random(3)
            yield ("60,000 random 16-byte keys",
                   [bytes(r.randrange(256) for _ in range(16))
                    for _ in range(60000)])

        print()
        for label, keys in keysets():
            row = "  %-26s" % label
            for name, fn in (("murmur3", mm), ("tab64", tab64)):
                c64 = len(keys) - len({fn(k) for k in keys})
                c24 = len(keys) - len({fn(k) & 0xFFFFFF for k in keys})
                row += "  %s: %d / %d" % (name, c64, c24)
            print(row + "   (64-bit / low-24 collisions)")
        print("  low-24 collisions are expected: n^2/2^25, about %d for 60,000"
              % (60000 ** 2 // 2 ** 25))

        def bloom(fn, n=4000, mbits=1 << 16, k=13):
            r = random.Random(11)
            bits = bytearray(mbits // 8)
            for i in range(n):
                h = fn(("member-%d-%s" % (i, r.randrange(1 << 20))).encode())
                h1, h2 = h & M32, h >> 32
                for j in range(k):
                    idx = (h1 + j * h2) % mbits
                    bits[idx >> 3] |= 1 << (idx & 7)
            fp = 0
            trials = 20000
            for j in range(trials):
                h = fn(("nonmember-%d" % j).encode())
                h1, h2 = h & M32, h >> 32
                if all(bits[((h1 + i * h2) % mbits) >> 3] >>
                       (((h1 + i * h2) % mbits) & 7) & 1 for i in range(k)):
                    fp += 1
            return fp / trials, (1 - math.exp(-k * n / mbits)) ** k

        print()
        for name, fn in (("murmur3", mm), ("tab64", tab64)):
            fp, theory = bloom(fn)
            print("  bloom filter, %-8s m=65536 n=4000 k=13: false positives "
                  "%.4f (theory %.4f)" % (name, fp, theory))

        print()
        for klen in (1, 2):
            keys = ([bytes([x]) for x in range(256)] if klen == 1 else
                    [bytes([x, y]) for x in range(256) for y in range(256)])
            for name, fn in (("murmur3", mm), ("tab64", tab64)):
                cells = 1 << 12
                hist = collections.Counter()
                for k in keys:
                    h = fn(k)
                    h1, h2 = h & M32, h >> 32
                    for i in range(13):
                        hist[(h1 + i * h2) % cells] += 1
                total = sum(hist.values())
                exp = total / cells
                chi = sum((hist[j] - exp) ** 2 / exp for j in range(cells))
                print("  chi-square, %-8s every %d-byte key over 4096 cells: "
                      "%.0f (expect 4096 +- 90)" % (name, klen, chi))

    print("\n%s" % ("ALL TESTS PASSED" if bad == 0 else "FAILURES: %d" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
