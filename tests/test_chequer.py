#!/usr/bin/env python3
"""Verify and time chequer.z80s against tests/chequer.py.

Checks every byte of the screen and every scanline's palette parity
against the model, over a walk of camera positions, and reports what a
frame costs against the 120,000 T-states a 6 MHz SAM has between 50 Hz
frames.

    pip install z80
    python3 tests/test_chequer.py
"""
import sys

from bench import Bench
import chequer as C

BUF = {0x80: 0x8000, 0x20: 0x2000}


def main():
    b = Bench("harness_chq.asm", org=0)
    s = b.syms
    it, _ = b.call_regs(s["chq_init"])
    used = int.from_bytes(b.peek(s["chq_gp"], 2), "little") - 0xE000
    print("  chq_init  %d T-states once, for %d bytes of compiled run"
          % (it, used))

    poses = [(x, z) for x in range(0, 256, 37) for z in (0, 100, 900, 4321)]
    bad = 0
    times = []
    for camx, camz in poses:
        b.poke(s["chq_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["chq_camz"], (camz & 0xFFFF).to_bytes(2, "little"))
        into = b.peek(s["chq_back"], 1)[0]
        t, _ = b.call_regs(s["chq_frame"])
        times.append(t)
        want, par = C.frame(camx, camz)
        got = b.peek(BUF[into], C.STRIDE * C.H)
        gpar = b.peek(s["chq_par"], C.H)
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  PIXEL MISMATCH at x=%d z=%d: %d bytes, first at %d "
                      "(y=%d x=%d) got %02X want %02X"
                      % (camx, camz, len(d), d[0], d[0] // C.STRIDE,
                         (d[0] % C.STRIDE) * 2, got[d[0]], want[d[0]]))
        if list(gpar[C.HZ + 1:]) != par[C.HZ + 1:]:
            bad += 1
            d = [y for y in range(C.HZ + 1, C.H) if gpar[y] != par[y]]
            print("  PARITY MISMATCH at x=%d z=%d: %d scanlines, first %d"
                  % (camx, camz, len(d), d[0]))
    n = len(poses)
    print("  %-40s %4d camera positions, %d mismatches"
          % ("Z80 against the model, pixels and parity", n, bad))
    print()
    et, _ = b.call_regs(s["chq_entry"])
    pt, _ = b.call_regs(s["chq_par8"])
    ft, _ = b.call_regs(s["chq_floor"])
    print("  chq_entry    %7d T-states, the 16 run entries" % et)
    print("  chq_floor    %7d T-states, %d scanlines of board"
          % (ft, 192 - min(y for y in range(C.H) if C.PTAB[y])))
    print("  chq_par8     %7d T-states, the palette parities" % pt)
    mean = sum(times) / n
    print("  chq_frame    min %7d  mean %7.0f  max %7d"
          % (min(times), mean, max(times)))
    print("  %-40s %.1f%% of a 50 Hz frame" % ("which is", mean / 1200))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
