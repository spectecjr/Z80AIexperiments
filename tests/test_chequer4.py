#!/usr/bin/env python3
"""Verify and time chequer4.z80s against tests/chequer4.py.

    pip install z80
    python3 tests/test_chequer4.py

chequer4 is chequer3's board with the depth alternation moved out of
the palette and into the pixels, so the model it is checked against is
harrier's screen with the two colour indices exchanged on every row
whose depth parity is odd - which tests/chequer4.py shows is the same
thing as a whole square of horizontal phase.
"""
import sys

from bench import Bench
import chequer4 as C
import harrier as HR

BUF = {0x80: 0x8000, 0x20: 0x2000}


def main():
    b = Bench("harness_chq4.asm", org=0)
    s = b.syms
    it, _ = b.call_regs(s["chq4_init"])
    print("  chq4_init %d T-states once, sky and haze into both buffers" % it)
    # camx runs past one square and goes negative, because the square
    # the camera is standing in is a parity of its own
    poses = [(x, z) for x in range(-640, 641, 47) for z in (0, 100, 900, 4321)]
    bad = 0
    times = []
    swapped = rows = 0
    for camx, camz in poses:
        b.poke(s["chq4_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["chq4_camz"], (camz & 0xFFFF).to_bytes(2, "little"))
        into = b.peek(s["chq4_back"], 1)[0]
        t, _ = b.call_regs(s["chq4_frame"])
        times.append(t)
        want = C.frame(camx, camz)
        plain, par = HR.frame(camx, camz)
        rows += C.H - C.TOP
        swapped += sum(par[C.TOP:])
        got = b.peek(BUF[into], C.STRIDE * C.H)
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  PIXEL MISMATCH x=%d z=%d: %d bytes, first at %d "
                      "(y=%d x=%d p=%d) got %02X want %02X"
                      % (camx, camz, len(d), d[0], d[0] // C.STRIDE,
                         (d[0] % C.STRIDE) * 2, C.PTAB[d[0] // C.STRIDE],
                         got[d[0]], want[d[0]]))
    n = len(poses)
    print("  %-40s %4d camera positions, %d mismatches"
          % ("Z80 against the model, pixels", n, bad))
    print("  %-40s %d of %d board rows drawn swapped"
          % ("which is harrier's picture, restriped", swapped, rows))
    print()
    ft, _ = b.call_regs(s["chq4_floor"])
    mt, _ = b.call_regs(s["chq4_msk8"])
    mean = sum(times) / n
    print("  chq4_floor   %7d T-states, %d scanlines of board"
          % (ft, 192 - C.TOP))
    print("  chq4_msk8    %7d T-states, the swap mask a scanline" % mt)
    print("  chq4_frame   min %7d  mean %7.0f  max %7d"
          % (min(times), mean, max(times)))
    print("  %-40s %.1f%% of a 50 Hz frame, %.1f Hz"
          % ("which is", mean / 1200, 6e6 / mean))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
