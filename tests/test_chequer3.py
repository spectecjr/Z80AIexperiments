#!/usr/bin/env python3
"""Verify and time chequer3.z80s against tests/chequer3.py.

    pip install z80
    python3 tests/test_chequer3.py

chequer3 draws harrier's screen out of compiled runs, so the model it
is checked against is checked against harrier's in turn - a run has to
put every boundary on the pixel harrier's dispatch per square puts it.
"""
import sys

from bench import Bench
import chequer3 as C
import harrier as HR

BUF = {0x80: 0x8000, 0x20: 0x2000}


def main():
    b = Bench("harness_chq3.asm", org=0)
    s = b.syms
    it, _ = b.call_regs(s["chq3_init"])
    print("  chq3_init %d T-states once, sky and haze into both buffers" % it)
    poses = [(x, z) for x in range(0, 256, 19) for z in (0, 100, 900, 4321)]
    bad = 0
    times = []
    for camx, camz in poses:
        b.poke(s["chq3_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["chq3_camz"], (camz & 0xFFFF).to_bytes(2, "little"))
        into = b.peek(s["chq3_back"], 1)[0]
        t, _ = b.call_regs(s["chq3_frame"])
        times.append(t)
        want, par = HR.frame(camx, camz)
        got = b.peek(BUF[into], C.STRIDE * C.H)
        gpar = b.peek(s["chq3_par"], C.H)
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  PIXEL MISMATCH x=%d z=%d: %d bytes, first at %d "
                      "(y=%d x=%d p=%d) got %02X want %02X"
                      % (camx, camz, len(d), d[0], d[0] // C.STRIDE,
                         (d[0] % C.STRIDE) * 2, C.PTAB[d[0] // C.STRIDE],
                         got[d[0]], want[d[0]]))
        if list(gpar[C.HZ + 1:]) != par[C.HZ + 1:]:
            bad += 1
            print("  PARITY MISMATCH x=%d z=%d" % (camx, camz))
    n = len(poses)
    print("  %-40s %4d camera positions, %d mismatches"
          % ("Z80 against harrier's model, pixels and parity", n, bad))
    print()
    ft, _ = b.call_regs(s["chq3_floor"])
    pt, _ = b.call_regs(s["chq3_par8"])
    mean = sum(times) / n
    print("  chq3_floor   %7d T-states, %d scanlines of board"
          % (ft, 192 - C.TOP))
    print("  chq3_par8    %7d T-states, the palette parities" % pt)
    print("  chq3_frame   min %7d  mean %7.0f  max %7d"
          % (min(times), mean, max(times)))
    print("  %-40s %.1f%% of a 50 Hz frame, %.1f Hz"
          % ("which is", mean / 1200, 6e6 / mean))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
