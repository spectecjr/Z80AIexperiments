#!/usr/bin/env python3
"""Generate roaddata2.z80s, and simulate what road2.z80s does with it.

    python3 tests/mkroad2data.py          # regenerate and self-check

The road is drawn three pieces to a row: grass in from the right, one
compiled run for the whole road, grass out to the left. The run is what
makes this cheap - a row's road has a shape fixed by the row and only
its position moves, so it compiles once and is positioned by SP, which
is chequer3's trick with the road's edges in place of the phase.

Everything inside the road rides in the run: both kerbs, both of their
inner edges and the centre line, all baked to the pixel. That is why a
one pixel marking costs nothing here - it is a nibble in a PUSHed
constant rather than a span that has to be at least four pixels wide.

A run is indexed by (half width, phase, band parity):

  half width  is the row's, and consecutive rows share one, so 62 runs
              cover 95 rows
  phase       is one pixel. SP is a byte address, so it places the road
              to two pixels on its own and the run only has to exist in
              two versions rather than four
  parity      is which way round the bands are. The solid colours could
              come from registers, but the baked boundary bytes could
              not, so the bank is doubled instead

`simulate` below runs the whole procedure in Python, including the
double buffer and the full width repaint a row wants when its band
parity flips, and is checked against tests/road2.py's ideal picture.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import road2 as A
from mkchqdata import defb, defw, sam

M = 8                           # the repaint margin, pixels each side:
                                # four times the two pixels a row's centre
                                # can move between frames at 50 Hz, and
                                # twice that again for the two frames a
                                # buffer waits its turn


def colours(par):
    """The four indices this row draws in, given its band parity."""
    return (A.GRASS0 + par, A.TARMAC0 + par, A.KERB0 + par,
            A.LINE if par else A.TARMAC0 + par)


def pixel(dx, w, k, lw, cols):
    """The colour at dx pixels right of the road's centre."""
    grass, tarmac, kerb, mark = cols
    lx = -(lw // 2)
    if dx < -w or dx >= w:
        return grass
    if dx < -w + k or dx >= w - k:
        return kerb
    if lx <= dx < lx + lw:
        return mark
    return tarmac


def grid(w, phase):
    """Where the pushes fall, relative to the road, for this row.

    The window is [c-w-M, c+w+M) and SP is the byte just past its right
    hand end, so the road's right edge sits u0 pixels left of where the
    first PUSH ends - which is M or M+1, and that one pixel is the whole
    of the phase. Everything else here follows from it, and none of it
    depends on where the road actually is.
    """
    u0 = M + 1 - phase                  # right edge, pixels from the top
    i0 = u0 >> 2                        # the PUSH the road starts in
    uL = u0 + 2 * w                     # and the one it ends in
    iL = uL >> 2
    # the window's left hand end, in PUSHes from the top
    np = ((M + 1 - phase + 2 * w + M) + 3) >> 2
    return u0, i0, iL, max(np, iL + 1)


def run(w, k, lw, phase, par):
    """The road, compiled: one PUSHed pair per 4 pixels of it."""
    cols = colours(par)
    u0, i0, iL, _ = grid(w, phase)
    out = []
    for j in range(i0, iL + 1):
        # SP starts u0 pixels right of the road's edge, so this PUSH's
        # four pixels sit here relative to the road's own centre
        px = [pixel(w + u0 - 4 - 4 * j + i, w, k, lw, cols)
              for i in range(4)]
        out.append(((px[0] << 4) | px[1], (px[2] << 4) | px[3]))
    return out


def entries(w, phase):
    """Where the two grass runs are entered, and how long the row is."""
    _, i0, iL, np = grid(w, phase)
    return 64 - i0, 64 - (np - 1 - iL), np


def widths():
    """The distinct half widths, and which one each scanline uses."""
    ws = sorted({A.WTAB[y] for y in range(A.HZ + 1, A.H)})
    return ws, {w: i for i, w in enumerate(ws)}


def simulate(poses):
    """Drive road2.z80s's procedure over a sequence of camera positions.

    Returns the back buffer after each pose, which is what the Z80 will
    have left behind and what tests/road2.py has to agree with.
    """
    ws, wi = widths()
    buf = [bytearray(A.STRIDE * A.H) for _ in range(2)]
    seen = [[-1] * A.H for _ in range(2)]       # the band parity each
    for b in buf:                               # buffer last painted
        for y in range(A.HZ + 1):
            b[y * A.STRIDE:(y + 1) * A.STRIDE] = bytes([A.SKY[y] * 17]) * 128
    out, back = [], 0
    for camx, camz in poses:
        par, cen = A.geometry(camx, camz)
        dst, mark = buf[back], seen[back]
        for y in range(A.HZ + 1, A.H):
            c, w, k, lw = cen[y], A.WTAB[y], A.KTAB[y], A.LTAB[y]
            p, row = par[y], y * A.STRIDE
            grass = (A.GRASS0 + p) * 17
            if mark[y] != p:                    # the bands moved on: this
                dst[row:row + 128] = bytes([grass]) * 128       # row's
                mark[y] = p                     # grass is all stale
            phase = (c + w + M + 1) & 1
            e0, ef, np = entries(w, phase)
            br = (c + w + M + 1) >> 1           # SP, as a byte in the row
            sp = row + br
            for j in range(64 - e0):            # grass in from the right
                sp -= 2
                dst[sp] = dst[sp + 1] = grass
            for lo, hi in run(w, k, lw, phase, p):
                sp -= 2
                dst[sp], dst[sp + 1] = lo, hi
            for _ in range(64 - ef):             # and out to the left
                sp -= 2
                dst[sp] = dst[sp + 1] = grass
        out.append(bytes(dst))
        back ^= 1
    return out


def check():
    """The procedure against road2.py's ideal picture, over a drive."""
    import math
    poses = []
    for t in range(240):
        camx = int(0.6 * A.RW * math.sin(2 * math.pi * t / 350.0))
        poses.append((camx, (t * 20) & 0xFFFF))
    got = simulate(poses)
    bad = 0
    for n, ((camx, camz), g) in enumerate(zip(poses, got)):
        if n < 2:
            continue                    # a buffer's first frame is its init
        want, _ = A.frame(camx, camz)
        if g != bytes(want):
            bad += 1
            if bad <= 3:
                d = [i for i in range(len(want)) if g[i] != want[i]]
                print("  FRAME %d x=%d z=%d: %d bytes, first at y=%d x=%d "
                      "got %02X want %02X"
                      % (n, camx, camz, len(d), d[0] // A.STRIDE,
                         (d[0] % A.STRIDE) * 2, g[d[0]], want[d[0]]))
    print("  %-44s %3d frames, %d wrong"
          % ("the procedure against the ideal picture", len(poses) - 2, bad))
    return bad


def cost():
    """What the procedure would cost on the Z80, from the counts."""
    ws, _ = widths()
    push = dispatch = 0
    for y in range(A.HZ + 1, A.H):
        w = A.WTAB[y]
        _, _, np = entries(w, 0)
        push += np
        dispatch += 44 + 42 + 44 + 22          # in, the run, out, the loop
        dispatch += 10 * 6                     # the run's baked boundaries
    return push, dispatch


LOWBANK = 3800                  # how much of the run bank fits below the
                                # screens, once the code and tables have
                                # had their share; the rest goes above


def emit_runs(ws, kw, lw):
    """The compiled runs, and the table of where each one starts.

    A run is the whole road: one PUSH per four pixels of it, with the
    value reloaded only where it changes - which is at the two kerbs,
    their inner edges and the centre line, and nowhere else. So a wide
    road is mostly PUSH HL at 11 T-states, and the six places a byte
    carries two colours at once cost 21.
    """
    body, hi, table, n, split = [], [], [], 0, False
    for w in ws:
        for par in (0, 1):
            for ph in (0, 1):
                if n > LOWBANK:
                    split = True
                out = hi if split else body
                table.append("rd2_r%d_%d_%d" % (w, ph, par))
                out.append("rd2_r%d_%d_%d:" % (w, ph, par))
                last = None
                for a, b in run(w, kw[w], lw[w], ph, par):
                    if (a, b) != last:
                        out.append("        LD   HL,%d" % ((b << 8) | a))
                        last = (a, b)
                        n += 4
                    else:
                        n += 1
                    out.append("        PUSH HL")
                out.append("        JP   rd2_out")
                n += 3
    return body, hi, table, n


def emit(path):
    ws, wix = widths()
    kw = {A.WTAB[y]: A.KTAB[y] for y in range(A.HZ + 1, A.H)}
    lw = {A.WTAB[y]: A.LTAB[y] for y in range(A.HZ + 1, A.H)}
    rec = []
    for y in range(A.H - 1, A.HZ, -1):
        w, (lo, hi) = A.WTAB[y], A.CLAMP[y]
        e00, ef0, _ = entries(w, 0)
        e01, ef1, _ = entries(w, 1)
        rec += [A.ZTAB[y] & 255, A.ZTAB[y] >> 8, lo, hi, w + M + 1, 0,
                e00, ef0, e01, ef1, wix[w] * 4, 0,
                255, 255]         # and a band parity per buffer,
                                        # which no row can match at first
    body, hibody, table, nrun = emit_runs(ws, kw, lw)
    pal = [0] * 16
    for i, c in ((A.SKY0, (0, 0, 4)), (A.SKY1, (0, 2, 6)), (A.SKY2, (2, 4, 6)),
                 (A.SKY3, (4, 6, 6)), (A.GRASS0, (0, 4, 0)),
                 (A.GRASS1, (0, 6, 2)), (A.TARMAC0, (2, 2, 2)),
                 (A.TARMAC1, (4, 4, 4)), (A.KERB0, (6, 0, 0)),
                 (A.KERB1, (6, 6, 6)), (A.LINE, (6, 6, 4))):
        pal[i] = sam(*c)
    parts = ["; Generated by tests/mkroad2data.py - do not edit by hand.",
             "\nRD2_HZ:         EQU %d" % A.HZ,
             "RD2_ROWS:       EQU %d          ; scanlines of road" % (A.H - 1 - A.HZ),
             "RD2_M:          EQU %d           ; the repaint margin, pixels" % M,
             "RD2_REC:        EQU 14          ; bytes of record a row"]
    for nm, v in (("GRASS", A.GRASS0), ("TARMAC", A.TARMAC0),
                  ("KERB", A.KERB0), ("LINE", A.LINE)):
        parts.append("RD2_%-11s EQU 0x%02X%02X" % (nm + ":", v * 17, v * 17))
    parts += ["\n        ALIGN 256\nrd2_trk:\n" + defw(A.TRACK),
              "\nrd2_pal:\n" + defb(pal),
              "\nrd2_sky:\n" + defb([c * 17 for c in A.SKY]),
              "\n        ALIGN 256\nrd2_rec:\n" + defb(rec, 14),
              # two pages, one a parity, so a run is LD L,offset / LD H,page
              "\n        ALIGN 256\nrd2_rt0:\n"
              + "\n".join("        DEFW " + ",".join(table[i:i + 2])
                          for i in range(0, len(table), 4)),
              "\n        ALIGN 256\nrd2_rt1:\n"
              + "\n".join("        DEFW " + ",".join(table[i + 2:i + 4])
                          for i in range(0, len(table), 4)),
              "\n" + "\n".join(body)]
    open(path, "w").write("\n".join(parts) + "\n")
    open(path.replace(".z80s", "hi.z80s"), "w").write(
        "; Generated by tests/mkroad2data.py - do not edit by hand.\n"
        "; The rest of the run bank, for above the screen buffers.\n"
        + "\n".join(hibody) + "\n")
    print("  %-44s %d widths, %d bytes of run, %d of record"
          % ("wrote " + os.path.basename(path), len(ws), nrun, len(rec)))


if __name__ == "__main__":
    ws, _ = widths()
    n = sum(len(run(w, 0, 1, ph, p)) for w in ws for ph in (0, 1)
            for p in (0, 1))
    print("  %-44s %3d widths, %d PUSHes of run" % ("the bank", len(ws), n))
    push, dispatch = cost()
    print("  %-44s %d PUSHes a frame, %d T-states"
          % ("a frame", push, push * 11 + dispatch))
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    emit(os.path.join(here, "roaddata2.z80s"))
    sys.exit(1 if check() else 0)
