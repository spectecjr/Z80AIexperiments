#!/usr/bin/env python3
"""Verify and time 8x8multiply_r16.z80s on an emulated Z80.

Both routines are checked against every one of the 65,536 possible
operand pairs, and timed exactly.

    pip install z80
    python3 tests/test_mult8x8.py

Needs sjasmplus on PATH (or in $SJASMPLUS).
"""
import os
import sys
import tempfile

from bench import Bench, zeus_shim

IN, OUT = 0xA000, 0xB000


def main():
    build = zeus_shim(os.path.join(tempfile.gettempdir(), "z80build"))
    b = Bench("harness_mult.asm", incdirs=(build,))
    s = b.syms
    m = b.m
    bad = 0

    # --- mult8x8_16: B = M1, C = M2, product in DE -------------------
    entry = s["mult8x8_16"]
    times = {"M1>=M2": [], "M1<M2": []}
    n = 0
    for m1 in range(256):
        for m2 in range(256):
            t, r = b.call_regs(entry, bc=(m1 << 8) | m2)
            if ((r >> 16) & 0xFFFF) != m1 * m2:
                n += 1
                if n <= 5:
                    print("  MISMATCH %d * %d = %d" % (m1, m2, (r >> 16) & 0xFFFF))
            times["M1>=M2" if m1 >= m2 else "M1<M2"].append(t)
    bad += n
    print("  %-32s %6d cases, %d mismatches" % ("mult8x8_16, exhaustive",
                                                65536, n))

    # --- stream_mult8x8_16: IX = pairs in, IY = results out ----------
    def stream(pairs):
        b.poke(IN, b"".join(bytes([x, y]) for x, y in pairs))
        m.sp = 0xFEFE
        m.ix = IN
        m.iy = OUT
        m.bc = len(pairs) << 8          # B = count
        m.pc = s["stream_mult8x8_16"]
        m.halted = False
        total, prev = 0, m.frame_tick
        for _ in range(400):
            m.ticks_to_stop = 50000
            m.run()
            step = m.frame_tick - prev
            total += step + 100000 if step < 0 else step
            prev = m.frame_tick
            if m.pc == 0:
                break
        else:
            raise RuntimeError("stream_mult8x8_16 did not return")
        raw = b.peek(OUT, 2 * len(pairs))
        return [raw[i] | (raw[i + 1] << 8) for i in range(0, len(raw), 2)], total

    n = 0
    allpairs = [(x, y) for x in range(256) for y in range(256)]
    for base in range(0, len(allpairs), 250):
        chunk = allpairs[base:base + 250]
        got, _ = stream(chunk)
        for (x, y), g in zip(chunk, got):
            if g != x * y:
                n += 1
                if n <= 5:
                    print("  MISMATCH stream %d * %d = %d" % (x, y, g))
    bad += n
    print("  %-32s %6d cases, %d mismatches"
          % ("stream_mult8x8_16, exhaustive", 65536, n))

    # --- timings ------------------------------------------------------
    print()
    for label in ("M1>=M2", "M1<M2"):
        ts = times[label]
        print("  mult8x8_16, %-8s  min %3dT  mean %5.1fT  max %3dT"
              % (label, min(ts), sum(ts) / len(ts), max(ts)))
    every = times["M1>=M2"] + times["M1<M2"]
    print("  mult8x8_16, overall     mean %5.1fT  (a CALL adds 17T)"
          % (sum(every) / len(every)))

    # per-pair cost of the streaming version, from the slope
    pairs = [(x * 7 & 255, x * 13 & 255) for x in range(200)]
    _, t200 = stream(pairs)
    _, t100 = stream(pairs[:100])
    _, t1 = stream(pairs[:1])
    print("  stream_mult8x8_16       %5.1fT per pair (%dT for one, "
          "%dT for 200)" % ((t200 - t100) / 100.0, t1, t200))
    print("  ... versus %5.1fT per pair going through mult8x8_16 with a CALL"
          % (sum(every) / len(every) + 17))

    print("\n%s" % ("ALL TESTS PASSED" if bad == 0 else "FAILURES: %d" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
