#!/usr/bin/env python3
"""Verify and time prismpre.z80s.

Two checks, because a precomputed frame is only worth anything if it
is the same frame:

  against the model  every one of the 64 frames, byte for byte, twice
                     round the loop so the wrap is checked too

  against prism      prism.z80s, driven at the same turn rates, drawn
                     side by side and compared. The tables came out of
                     tests/prism.py, so this is the whole chain: the
                     model matches prism, and prismpre matches both

    pip install z80
    python3 tests/test_prismpre.py
"""
import sys

from bench import Bench
import prismpre as PP
import prism as P

ENTROPY = P.LOGO == "entropy"
HARNESS = ("harness_entropypre.asm" if ENTROPY else "harness_prismpre.asm")
LIVE = ("harness_entropy.asm" if ENTROPY else "harness_prism.asm")
import raster

BUF = {0x80: 0x8000, 0x20: 0x2000}
PAL = ([(32 * i, 32 * i, 30 * i) for i in range(8)]
       + [(36 * i, 6 * i, 6 * i) for i in range(8)])


def main():
    b = Bench(HARNESS, org=0)
    s = b.syms
    r = Bench(LIVE, org=0)          # prism, for the same spin
    rs = r.syms
    recip = list(r.peek(rs["t3d_recip"], 256))
    lite = [x - 256 if x > 127 else x for x in r.peek(rs["rndl_lite"], 3)]
    recs, pts, want = PP.build(recip, lite)
    print("  tables    %d frames, %d bytes of record and %d of point"
          % (PP.NFRAMES, len(recs), len(pts)))
    hi = len(pts) - (s["pp_ptslo"] and 0)      # what went above the buffers
    hi = 0xFE00 - s["pp_ptshi"]
    print("  RAM       records at %04X, %d bytes of point above the buffers "
          "and %d below" % (s["pp_recs"], min(hi, len(pts)),
                            max(0, len(pts) - hi)))

    it, _ = b.call_regs(s["pp_init"])
    print("  pp_init   %d T-states once" % it)
    r.call_regs(rs["pr_init"])
    r.poke(rs["demo_dax"], bytes(PP.DA))           # the same loop

    bad = badp = 0
    times, ptimes, shown = [], [], None
    for f in range(2 * PP.NFRAMES):
        into = b.peek(s["rndl_back"], 1)[0]
        t, _ = b.call_regs(s["pp_frame"])
        times.append(t)
        got = b.peek(BUF[into], raster.STRIDE * raster.H)

        pinto = r.peek(rs["rndl_back"], 1)[0]
        pt, _ = r.call_regs(rs["pr_frame"])
        ptimes.append(pt)
        pgot = r.peek(BUF[pinto], raster.STRIDE * raster.H)

        if got != bytes(want[f % PP.NFRAMES]):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(got))
                     if got[i] != want[f % PP.NFRAMES][i]]
                print("  MISMATCH frame %d: %d bytes, first at %d (y=%d x=%d)"
                      % (f, len(d), d[0], d[0] // raster.STRIDE,
                         (d[0] % raster.STRIDE) * 2))
        if got != pgot:
            badp += 1
        if f == 20:
            shown = got

    n = len(times)
    print("  %-40s %6d frames, %d mismatches"
          % ("Z80 buffer against the model", n, bad))
    print("  %-40s %6d frames, %d mismatches"
          % ("Z80 buffer against prism.z80s", n, badp))
    print()
    print("  pp_frame     min %d T-states, mean %.0f, max %d"
          % (min(times), sum(times) / n, max(times)))
    print("  pr_frame     min %d T-states, mean %.0f, max %d   (prism, "
          "same frames)" % (min(ptimes), sum(ptimes) / n, max(ptimes)))
    print("  %-40s %.1f Hz mean, %.1f Hz worst"
          % ("which at 6 MHz is", 6e6 / (sum(times) / n), 6e6 / max(times)))
    print("  %-40s %.1f%%, %.0f T-states a frame"
          % ("of prism's frame that leaves",
             100.0 * sum(times) / sum(ptimes),
             (sum(ptimes) - sum(times)) / n))
    if shown is not None:
        raster.to_png(shown, "/tmp/z80prismpre.png", PAL)
    ok = bad == 0 and badp == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else
                    "FAILURES: %d, %d" % (bad, badp)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
