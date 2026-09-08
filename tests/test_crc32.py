#!/usr/bin/env python3
"""Verify crc32.z80s against zlib's crc32, on an emulated Z80.

Covers both entry points, the streaming interface, the page-boundary
cases in the two-level loop counter, and the standard check vectors.

    pip install z80
    python3 tests/test_crc32.py

Needs sjasmplus on PATH (or in $SJASMPLUS).
"""
import random
import sys
import zlib

from bench import Bench

DATA = 0xA000


def main():
    rng = random.Random(20260908)
    bench = Bench("harness_crc.asm")
    syms = bench.syms
    print("library is %d bytes: %d of code, %d of tables, 4 of accumulator"
          % (syms["crc32_end"] - syms["crc32"],
             syms["crc32_tab0"] - syms["crc32"],
             syms["crc32_acc"] - syms["crc32_tab0"]))

    bad = 0
    checked = 0
    total_bytes = 0

    def run(entry, data):
        bench.poke(DATA, data)
        t, crc = bench.call_regs(syms[entry], hl=DATA, bc=len(data))
        return crc, t

    # --- the standard check vectors ---------------------------------
    vectors = [(b"", 0x00000000),
               (b"a", 0xE8B7BE43),
               (b"abc", 0x352441C2),
               (b"123456789", 0xCBF43926),
               (b"The quick brown fox jumps over the lazy dog",
                0x414FA339)]
    for data, want in vectors:
        got, _ = run("crc32", data)
        checked += 1
        if got != want:
            bad += 1
            print("  MISMATCH crc32(%r) = %08X, want %08X" % (data, got, want))
    print("  %-34s %6d vectors, %d mismatches" % ("published check vectors",
                                                  len(vectors), bad))

    # --- lengths that exercise the loop counter ---------------------
    lengths = list(range(0, 40)) + [63, 64, 65, 127, 128, 129, 254, 255, 256,
                                    257, 258, 511, 512, 513, 767, 768, 1023,
                                    1024, 1025, 4095, 4096]
    lbad = 0
    for n in lengths:
        data = bytes(rng.randrange(256) for _ in range(n))
        want = zlib.crc32(data) & 0xFFFFFFFF
        for entry in ("crc32", "crc32_bits"):
            got, _ = run(entry, data)
            checked += 1
            total_bytes += n
            if got != want:
                lbad += 1
                if lbad <= 6:
                    print("  MISMATCH %s, length %d: %08X, want %08X"
                          % (entry, n, got, want))
    bad += lbad
    print("  %-34s %6d cases, %d mismatches"
          % ("both routines, all lengths", 2 * len(lengths), lbad))

    # --- random blocks ----------------------------------------------
    rbad = 0
    for _ in range(400):
        n = rng.randrange(1, 3000)
        data = bytes(rng.randrange(256) for _ in range(n))
        want = zlib.crc32(data) & 0xFFFFFFFF
        got, _ = run("crc32", data)
        checked += 1
        total_bytes += n
        if got != want:
            rbad += 1
            if rbad <= 6:
                print("  MISMATCH random block of %d: %08X, want %08X"
                      % (n, got, want))
    bad += rbad
    print("  %-34s %6d cases, %d mismatches" % ("random blocks", 400, rbad))

    # --- streaming: start, several updates, final -------------------
    sbad = 0
    for _ in range(200):
        chunks = [bytes(rng.randrange(256) for _ in range(rng.randrange(0, 500)))
                  for _ in range(rng.randrange(1, 5))]
        want = zlib.crc32(b"".join(chunks)) & 0xFFFFFFFF
        bench.call_regs(syms["crc32_start"])
        for chunk in chunks:
            bench.poke(DATA, chunk)
            bench.call_regs(syms["crc32_update"], hl=DATA, bc=len(chunk))
        _, got = bench.call_regs(syms["crc32_final"])
        checked += 1
        if got != want:
            sbad += 1
            if sbad <= 6:
                print("  MISMATCH streaming %s: %08X, want %08X"
                      % ([len(c) for c in chunks], got, want))
    bad += sbad
    print("  %-34s %6d cases, %d mismatches" % ("streamed in several blocks",
                                                200, sbad))

    # --- throughput --------------------------------------------------
    data = bytes(rng.randrange(256) for _ in range(4096))
    for entry in ("crc32", "crc32_bits"):
        _, t1 = run(entry, data[:1024]), None
        crc, t = run(entry, data)
        crc2, t2 = run(entry, data[:2048])
        per_byte = (t - t2) / 2048.0
        print("  %-34s %6.1f T-states per byte (%d T for 4096 bytes)"
              % (entry, per_byte, t))

    print("\nchecked %d cases over %d bytes of data" % (checked, total_bytes))
    print("%s" % ("ALL TESTS PASSED" if bad == 0 else "FAILURES: %d" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
