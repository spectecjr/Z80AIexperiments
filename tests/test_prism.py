#!/usr/bin/env python3
"""Verify and time prism.z80s against tests/prism.py.

The logo turning, compared byte for byte with the model every frame,
which checks the per-normal lighting, the plane test, the ordering and
seven pieces' worth of renderlit at once.

    pip install z80
    python3 tests/test_prism.py
"""
import sys

from bench import Bench
import prism as P

ENTROPY = P.LOGO == "entropy"
HARNESS = ("harness_entropy.asm" if ENTROPY else "harness_prism.asm")
LIVE = HARNESS
import raster

BUF = {0x80: 0x8000, 0x20: 0x2000}
PAL = ([(32 * i, 32 * i, 30 * i) for i in range(8)]
       + [(36 * i, 6 * i, 6 * i) for i in range(8)])


def check_faces():
    """Every declared normal must agree with the face's own winding.

    renderlit keeps a face when N.T + off < 0 and then draws the four
    vertices its face table names, in that order. If the normal and
    that winding disagree the face is kept exactly when it should be
    culled - and being wound backwards on screen it then fills
    nothing, so it goes missing rather than looking wrong. That is
    what an inward edge normal did here, to three sides in four.

    The plane offset gets the same treatment: all four of the face's
    vertices have to lie on n.x = off, or the visibility test is
    testing some other plane than the face.
    """
    bad = 0
    for pi, (quad, _) in enumerate(P.PIECES):
        vs, ns = P.verts(quad), P.normals(quad)
        for fi, idx in enumerate(raster.FACES):
            q = [vs[k] for k in idx]
            w = [0, 0, 0]                       # Newell's normal
            for j in range(4):
                x0, y0, z0 = q[j]
                x1, y1, z1 = q[(j + 1) & 3]
                w[0] += (y0 - y1) * (z0 + z1)
                w[1] += (z0 - z1) * (x0 + x1)
                w[2] += (x0 - x1) * (y0 + y1)
            n, off = ns[fi]
            if sum(w[a] * n[a] for a in range(3)) <= 0:
                print("  WINDING piece %d face %d: normal %s against %s"
                      % (pi, fi, n, tuple(w)))
                bad += 1
            for v in q:
                if abs(sum(n[a] * v[a] for a in range(3)) // 128 - off) > 1:
                    print("  PLANE   piece %d face %d: %s is not on n.x=%d"
                          % (pi, fi, v, off))
                    bad += 1
                    break
    print("  %-40s %6d faces, %d wrong"
          % ("normals against the face winding", 6 * len(P.PIECES), bad))
    return bad


def main():
    b = Bench(HARNESS, org=0)
    s = b.syms
    recip = list(b.peek(s["t3d_recip"], 256))
    lite = [x - 256 if x > 127 else x for x in b.peek(s["rndl_lite"], 3)]
    it, _ = b.call_regs(s["pr_init"])
    print("  pr_init   %d T-states once" % it)
    print("  logo      %d pieces, %d faces, %d normals"
          % (len(P.PIECES), 6 * len(P.PIECES), len(set(
              n for q, _ in P.PIECES for n, _ in P.normals(q)))))

    bad = check_faces()
    lo = P.Logo()
    times, shown = [], None
    frames = 256
    for f in range(frames):
        into = b.peek(s["rndl_back"], 1)[0]
        t, _ = b.call_regs(s["pr_frame"])
        times.append(t)
        want, order, drawn = lo.frame(recip, lite)
        got = b.peek(BUF[into], raster.STRIDE * raster.H)
        if got != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("  MISMATCH frame %d: %d bytes, first at %d (y=%d x=%d) "
                      "got %02X want %02X, order %s, %d faces drawn"
                      % (f, len(d), d[0], d[0] // raster.STRIDE,
                         (d[0] % raster.STRIDE) * 2, got[d[0]], want[d[0]],
                         order, len(drawn)))
        elif f == 40:
            shown = got
    n = len(times)
    print("  %-40s %6d frames, %d mismatches"
          % ("Z80 buffer against the model", frames, bad))
    print()
    print("  pr_frame     min %d T-states, mean %.0f, max %d"
          % (min(times), sum(times) / n, max(times)))
    print("  %-40s %.0f%% of 120,000 (50 Hz on a 6 MHz SAM)"
          % ("mean", 100 * (sum(times) / n) / 120000))
    print("  %-40s %.1f Hz mean, %.1f Hz worst"
          % ("which at 6 MHz is", 6e6 / (sum(times) / n), 6e6 / max(times)))
    if shown is not None:
        raster.to_png(shown, "/tmp/z80prism.png", PAL)
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
