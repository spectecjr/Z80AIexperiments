#!/usr/bin/env python3
"""Verify and time transform3d.z80s on an emulated Z80.

Checks the generated multiply tables, then the whole rotate ->
translate -> project pipeline against a model of the same fixed-point
arithmetic, and reports what fits in a 192,000 T-state budget.

    pip install z80
    python3 tests/test_transform3d.py
"""
import random
import sys

from bench import Bench

VERTS, SCREEN = 0xC000, 0xD000
BUDGET = 192000


def s8(v):
    return v - 256 if v > 127 else v


def s16(v):
    v &= 0xFFFF
    return v - 65536 if v > 32767 else v


def model(verts, m, t, recip):
    """The same arithmetic the Z80 does, including where it wraps."""
    out = []
    for x, y, z in verts:
        acc = []
        for row in range(3):
            a = t[row]
            for j, v in enumerate((x, y, z)):
                a = s16(a + m[3 * row + j] * v)
            acc.append(a)
        X, Y, Z = acc
        d = (Z >> 8) & 0xFF                 # the high byte, as the Z80 sees it
        if d >= 0x80 or d < 0x20:
            zi = 64
        elif d >= 0x7F:
            zi = 255
        else:
            zi = (Z >> 7) & 0xFF
        r = recip[zi]
        sx = ((X >> 7) & 0xFF)
        sy = ((Y >> 7) & 0xFF)
        px = abs(s8(sx)) if s8(sx) != -128 else 128
        py = abs(s8(sy)) if s8(sy) != -128 else 128
        hx = (px * r) >> 8
        hy = (py * r) >> 8
        if s8(sx) < 0:
            hx = (-hx) & 0xFF
        if s8(sy) < 0:
            hy = (-hy) & 0xFF
        out.append(((hx + 128) & 0xFF, (96 - hy) & 0xFF))
    return out


def main():
    rng = random.Random(20260908)
    b = Bench("harness_t3d.asm")
    s = b.syms
    recip = list(b.peek(s["t3d_recip"], 256))
    bad = 0

    def setup(m, t):
        b.poke(s["t3d_m"], bytes(v & 0xFF for v in m))
        for i, name in enumerate(("t3d_tx", "t3d_ty", "t3d_tz")):
            b.poke(s[name], (t[i] & 0xFFFF).to_bytes(2, "little"))
        return b.call_regs(s["t3d_build"])[0]

    def run(verts):
        flat = bytes(v & 0xFF for vert in verts for v in vert)
        b.poke(VERTS, flat)
        t, _ = b.call_regs(s["t3d_run"], hl=VERTS, de=SCREEN, bc=len(verts) << 8)
        raw = b.peek(SCREEN, 2 * len(verts))
        return [(raw[i], raw[i + 1]) for i in range(0, len(raw), 2)], t

    # --- the tables the build produces --------------------------------
    m = [rng.randrange(-128, 128) for _ in range(9)]
    build_t = setup(m, (0, 0, 128 * 128))
    n = 0
    for k in range(9):
        page = s["t3d_tab"] + 512 * k
        lo, hi = b.peek(page, 256), b.peek(page + 256, 256)
        for v in range(256):
            want = (m[k] * s8(v)) & 0xFFFF
            if lo[v] | (hi[v] << 8) != want:
                n += 1
    bad += n
    print("  %-34s %7d entries, %d wrong" % ("t3d_build tables", 9 * 256, n))

    # --- the pipeline --------------------------------------------------
    n = checked = 0
    for trial in range(60):
        # a real rotation matrix, so the accumulator cannot overflow
        import math
        ax, ay, az = (rng.uniform(0, 6.283) for _ in range(3))
        ca, sa = math.cos(ax), math.sin(ax)
        cb, sb = math.cos(ay), math.sin(ay)
        cc, sc = math.cos(az), math.sin(az)
        R = [[cb * cc, -cb * sc, sb],
             [sa * sb * cc + ca * sc, -sa * sb * sc + ca * cc, -sa * cb],
             [-ca * sb * cc + sa * sc, ca * sb * sc + sa * cc, ca * cb]]
        m = [max(-128, min(127, int(round(R[i][j] * 128))))
             for i in range(3) for j in range(3)]
        t = (rng.randrange(-4000, 4000), rng.randrange(-4000, 4000),
             rng.randrange(64 * 128, 250 * 128))
        setup(m, t)
        verts = [(rng.randrange(-70, 71), rng.randrange(-70, 71),
                  rng.randrange(-70, 71)) for _ in range(20)]
        got, _ = run(verts)
        want = model(verts, m, t, recip)
        checked += len(verts)
        for i, (g, w) in enumerate(zip(got, want)):
            if g != w:
                n += 1
                if n <= 5:
                    print("  MISMATCH vertex %r -> %r, want %r" % (verts[i], g, w))
    bad += n
    print("  %-34s %7d vertices, %d mismatches"
          % ("t3d_run against the model", checked, n))

    # --- timings --------------------------------------------------------
    print()
    print("  t3d_build (nine 512-byte tables)   %8d T-states" % build_t)
    counts = [1, 2, 4, 8, 16, 32, 64, 128]
    times = {}
    for cnt in counts:
        verts = [(rng.randrange(-70, 71), rng.randrange(-70, 71),
                  rng.randrange(-70, 71)) for _ in range(cnt)]
        _, times[cnt] = run(verts)
    per = (times[128] - times[16]) / (128 - 16)
    fixed = times[16] - 16 * per
    for cnt in counts:
        print("  t3d_run, %3d vertices              %8d T-states" % (cnt, times[cnt]))
    print("\n  per vertex %.1f T-states, call overhead %.0f" % (per, fixed))
    print("  in %d T-states:" % BUDGET)
    print("    %d vertices, rebuilding the tables each frame"
          % int((BUDGET - build_t - fixed) / per))
    print("    %d vertices if the matrix has not changed"
          % int((BUDGET - fixed) / per))
    direct = per + 9 * (195 - 45)      # estimate: a 45T table term -> 195T
    print("    %d vertices multiplying directly instead, no build "
          "(estimated %.0fT a vertex)" % (int(BUDGET / direct), direct))
    print("    so the build pays for itself above %d vertices"
          % int(build_t / (direct - per)))

    print("\n%s" % ("ALL TESTS PASSED" if bad == 0 else "FAILURES: %d" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
