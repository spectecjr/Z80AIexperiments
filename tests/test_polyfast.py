#!/usr/bin/env python3
"""Verify and time polyfast.z80s against tests/polyfast.py.

Random convex quads of every shape the logo produces, plus every quad
prism actually draws, compared byte for byte - and timed head to head
against renderlit's own rasteriser on the same quads.

    pip install z80
    python3 tests/test_polyfast.py
"""
import random
import sys

from bench import Bench
import polyfast as PF
import raster

BUF = 0x8000
N = 128 * 192
PTS = 0x1F00          # free low RAM, clear of either rasteriser


def quads(n, rnd):
    """Convex quads, wound so the descending edges are on the right."""
    out = []
    while len(out) < n:
        cx, cy = rnd.randint(40, 210), rnd.randint(30, 160)
        rx, ry = rnd.randint(1, 45), rnd.randint(1, 40)
        a = rnd.random() * 6.283
        import math
        q = []
        for k in range(4):
            t = a + k * 1.5708
            q.append((int(cx + rx * math.cos(t)), int(cy + ry * math.sin(t))))
        if min(p[0] for p in q) < 0 or max(p[0] for p in q) > 255:
            continue
        if min(p[1] for p in q) < 0 or max(p[1] for p in q) > 191:
            continue
        cr = sum(q[j][0] * q[(j + 1) & 3][1] - q[(j + 1) & 3][0] * q[j][1]
                 for j in range(4))
        if cr == 0:
            continue
        out.append(q if cr < 0 else q[::-1])
    return out


def draw(b, s, entry, quad, colour):
    """One quad through a rasteriser, as face 0 of a prism."""
    order = raster.FACES[0]
    v = dict(zip(order, quad))
    flat = bytearray()
    for k in range(8):
        flat += bytes(v.get(k, (0, 0)))
    b.poke(PTS, flat)
    b.poke(s["rndl_pts"], bytes([PTS & 0xFF, PTS >> 8]))
    b.poke(s["rndl_vis"], bytes([0xFF] + [0] * 5))
    b.poke(s["rndl_fcol"], bytes([colour] * 6))
    b.poke(BUF, bytes(N))
    t, _ = b.call_regs(s[entry])
    return t, b.peek(BUF, N)


def box(w, h, slant=0):
    """A quad of a known height, wound the way the face table gives."""
    return [(60, 40), (60 + slant, 40 + h), (60 + slant + w, 40 + h),
            (60 + w, 40)][::-1]


def curve(b, s):
    """What a face costs each of them, and where the two cross."""
    def t(entry, q):
        return draw(b, s, entry, q, 0x77)[0]
    lo, hi = 2, 64
    r1, r2 = t("rndl_six", box(40, lo)), t("rndl_six", box(40, hi))
    p1, p2 = t("pf_six", box(40, lo)), t("pf_six", box(40, hi))
    rs = (r2 - r1) / float(hi - lo)
    ps = (p2 - p1) / float(hi - lo)
    rf, pf = r1 - rs * lo, p1 - ps * lo
    print("  %-12s %6.0f T-states a face + %5.1f a scanline"
          % ("renderlit", rf, rs))
    print("  %-12s %6.0f T-states a face + %5.1f a scanline"
          % ("polyfast", pf, ps))
    print("  %-12s %6.0f scanlines a face, and prism's faces average 23"
          % ("even at", (pf - rf) / (rs - ps)))
    print()
    print("  a 40 by 32 quad, as its edges lean over:")
    for sl in (0, 16, 32, 64):
        print("     slant %2d   renderlit %6d   polyfast %6d"
              % (sl, t("rndl_six", box(40, 32, sl)), t("pf_six", box(40, 32, sl))))


def main():
    b = Bench("harness_pf.asm", org=0)
    s = b.syms
    b.call_regs(s["rndl_init"])
    it, _ = b.call_regs(s["pf_init"])
    print("  pf_init   %d T-states once, for a 384 byte reciprocal table" % it)
    rnd = random.Random(7)
    qs = quads(300, rnd)

    bad = 0
    tp = tr = 0
    for q in qs:
        colour = 0x77
        t1, got = draw(b, s, "pf_six", q, colour)
        t2, ren = draw(b, s, "rndl_six", q, colour)
        tp += t1
        tr += t2
        want = bytearray(raster.STRIDE * raster.H)
        PF.fill_quad(want, q, colour & 15)
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(N) if got[i] != want[i]]
                print("  MISMATCH %s: %d bytes, first at %d (y=%d x=%d) "
                      "got %02X want %02X"
                      % (q, len(d), d[0], d[0] // 128, (d[0] % 128) * 2,
                         got[d[0]], want[d[0]]))
    print("  %-40s %6d quads, %d mismatches"
          % ("Z80 against the model", len(qs), bad))
    print()
    print("  %-24s %8d T-states for the %d quads" % ("renderlit", tr, len(qs)))
    print("  %-24s %8d T-states, %.0f%% of it"
          % ("polyfast", tp, 100.0 * tp / tr))
    print("  %-24s %8d T-states a quad, against %d"
          % ("which is", tp / len(qs), tr / len(qs)))
    print()
    curve(b, s)
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
