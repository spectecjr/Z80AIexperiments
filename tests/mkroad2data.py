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

M = A.M                         # the repaint margin, which the model
                                # owns because the rails depend on it


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
    """Where the PUSHes fall, relative to the road, for this row.

    The run is the whole window - grass margin, road, grass margin - and
    SP starts at the byte just past its right hand end, so the first
    PUSH's four pixels end M+1-phase pixels right of the road's edge.
    That one pixel is the whole of the phase, and none of the rest
    depends on where the road actually is.
    """
    u0 = M + 1 - phase
    np = (2 * w + 2 * M + 1 - phase) // 4 + 1
    return u0, np


def run(w, k, lw, phase, par):
    """The window, compiled: one PUSHed pair per four pixels of it."""
    cols = colours(par)
    u0, np = grid(w, phase)
    out = []
    for j in range(np):
        px = [pixel(w + u0 - 4 - 4 * j + i, w, k, lw, cols) for i in range(4)]
        out.append(((px[0] << 4) | px[1], (px[2] << 4) | px[3]))
    return out


def maxskip(w):
    """How many PUSHes of this row's window can be off the right."""
    return max(0, ((A.CHI + w + M + 1) // 2 - 128 + 1) // 2)


def place(c, w):
    """Where SP goes, how many PUSHes to skip, and the odd byte.

    A window whose right hand end is past the screen's cannot start
    there, so the run is entered `skip` PUSHes in. The skip is rounded
    up, which leaves byte 127 unwritten whenever the window's end is on
    an odd byte - the PUSH that would have covered it was skipped - so
    that byte is stored on its own, out of a table beside the skips.
    """
    bo = (c + w + M + 1) >> 1
    skip = max(0, (bo - 128 + 1) >> 1)
    return bo - 2 * skip, skip, bo & 1 and skip > 0


def widths():
    """The distinct half widths, and which one each scanline uses."""
    ws = sorted({A.WTAB[y] for y in range(A.HZ + 1, A.H)})
    return ws, {w: i for i, w in enumerate(ws)}


def simulate(poses):
    """Drive road2.z80s's procedure over a sequence of camera positions.

    Including the spill: the road is wider than the screen down at the
    bottom, so a window that runs off the left hand end carries on into
    the *previous* row's right hand end, which is where SP lands next.
    Rows are drawn bottom upwards, so that row is drawn immediately
    afterwards and paints over it - but only as far right as its own
    window reaches, so what it has to do first is put grass back from
    there to the screen's edge. That is the only thing the spill costs,
    it is nothing at all when the road is on screen, and it never
    reaches the sky: a row only spills once it is wider than the rails,
    which is forty rows below the horizon.
    """
    buf = [bytearray(A.STRIDE * A.H) for _ in range(2)]
    seen = [[-1] * A.H for _ in range(2)]
    for b in buf:
        for y in range(A.HZ + 1):
            b[y * A.STRIDE:(y + 1) * A.STRIDE] = bytes([A.SKY[y] * 17]) * 128
    out, back = [], 0
    for camx, camz in poses:
        par, cen = A.geometry(camx, camz)
        dst, mark = buf[back], seen[back]
        dirt = 128                      # nothing spilled into the bottom row
        for y in range(A.H - 1, A.HZ, -1):
            c, w, k, lw = cen[y], A.WTAB[y], A.KTAB[y], A.LTAB[y]
            p, row = par[y], y * A.STRIDE
            grass = (A.GRASS0 + p) * 17
            sp, skip, odd = place(c, w)
            if mark[y] != p:            # the band has moved on under it
                f = 0
                mark[y] = p
            elif dirt < 128:            # the row below spilled into it
                f = max(dirt, sp) & ~1
            else:
                f = 128
            if f < 128:
                dst[row + f:row + 128] = bytes([grass]) * (128 - f)
            phase = (c + w + M + 1) & 1
            r = run(w, k, lw, phase, p)
            if odd:                             # the PUSH that would have
                dst[row + 127] = r[skip - 1][0]         # covered it went
            a = row + sp
            for lo, hi in r[skip:]:
                a -= 2
                dst[a], dst[a + 1] = lo, hi
            assert a >= (A.HZ + 1) * A.STRIDE, "spilled into the sky"
            dirt = a - row + 128        # where that leaves the row above
            if dirt > 128:
                dirt = 128
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
    push = 0
    for y in range(A.HZ + 1, A.H):
        push += grid(A.WTAB[y], 0)[1]
    return push, 95 * (44 + 42 + 44 + 22)


LOWBANK = 5000                  # how much of the run bank fits below the
                                # screens, once the code and tables have
                                # had their share; the rest goes above


def emit_runs(ws, kw, lw):
    """The compiled runs, their skip tables, and the two index tables.

    A run is the whole window - grass margin, road, grass margin - one
    PUSH per four pixels of it, with the value reloaded only where it
    changes. The skip table is what lets it be entered part way: a run
    is a mix of one-byte PUSHes and four-byte LD HL,nn / PUSH pairs, so
    "skip n PUSHes" is not arithmetic, it is a lookup. Beside each
    offset are two more things the entry needs: the low byte of the
    PUSH that was stepped over, for the odd byte at the screen's edge
    that it would have covered, and the value it would have left in HL
    - because a run reloads HL only where the colour changes, so an
    entry part way in can land on a PUSH whose LD went with the part
    that was skipped.
    """
    body, hi, runs, skips, n, split = [], [], [], [], 0, False
    for w in ws:
        for par in (0, 1):
            for ph in (0, 1):
                if n > LOWBANK:
                    split = True
                out = hi if split else body
                nm = "rd2_r%d_%d_%d" % (w, ph, par)
                runs.append(nm)
                skips.append("rd2_s%d_%d_%d" % (w, ph, par))
                r = run(w, kw[w], lw[w], ph, par)
                off, last, pos = [], None, 0
                for a, b in r:
                    off.append(pos)
                    if (a, b) != last:
                        pos += 4
                        last = (a, b)
                    else:
                        pos += 1
                tab = []
                for sk in range(maxskip(w) + 1):
                    tab += [off[sk], r[sk - 1][0] if sk else 0,
                            r[sk][0], r[sk][1]]
                out.append("rd2_s%d_%d_%d:\n" % (w, ph, par) + defb(tab, 16))
                out.append(nm + ":")
                last = None
                for a, b in r:
                    if (a, b) != last:
                        out.append("        LD   HL,%d" % ((b << 8) | a))
                        last = (a, b)
                    out.append("        PUSH HL")
                out.append("        JP   rd2_out")
                n += pos + 3 + len(tab)
    return body, hi, runs, skips, n


def emit(path):
    ws, wix = widths()
    kw = {A.WTAB[y]: A.KTAB[y] for y in range(A.HZ + 1, A.H)}
    lw = {A.WTAB[y]: A.LTAB[y] for y in range(A.HZ + 1, A.H)}
    rec = []
    for y in range(A.H - 1, A.HZ, -1):
        w = A.WTAB[y]
        rec += [A.ZTAB[y] & 255, A.ZTAB[y] >> 8, w + M + 1, wix[w] * 4,
                255, 255]
    body, hibody, runs, skips, nrun = emit_runs(ws, kw, lw)
    pal = [0] * 16
    for i, c in ((A.SKY0, (0, 0, 4)), (A.SKY1, (0, 2, 6)), (A.SKY2, (2, 4, 6)),
                 (A.SKY3, (4, 6, 6)), (A.GRASS0, (0, 4, 0)),
                 (A.GRASS1, (0, 6, 2)), (A.TARMAC0, (2, 2, 2)),
                 (A.TARMAC1, (4, 4, 4)), (A.KERB0, (6, 0, 0)),
                 (A.KERB1, (6, 6, 6)), (A.LINE, (6, 6, 4))):
        pal[i] = sam(*c)

    def page(names, i):
        return "\n".join("        DEFW " + ",".join(names[k:k + 2])
                          for k in range(i, len(names), 4))

    parts = ["; Generated by tests/mkroad2data.py - do not edit by hand.",
             "\nRD2_HZ:         EQU %d" % A.HZ,
             "RD2_ROWS:       EQU %d          ; scanlines of road"
             % (A.H - 1 - A.HZ),
             "RD2_M:          EQU %d           ; the repaint margin, pixels" % M,
             "RD2_REC:        EQU 6           ; bytes of record a row",
             "RD2_CLO:        EQU %d          ; and the rails the centre" % A.CLO,
             "RD2_CHI:        EQU %d         ; is held between" % A.CHI]
    for nm, v in (("GRASS", A.GRASS0), ("TARMAC", A.TARMAC0),
                  ("KERB", A.KERB0), ("LINE", A.LINE)):
        parts.append("RD2_%-11s EQU 0x%02X%02X" % (nm + ":", v * 17, v * 17))
    parts += ["\n        ALIGN 256\nrd2_trk:\n" + defw(A.TRACK),
              "\nrd2_pal:\n" + defb(pal),
              "\nrd2_sky:\n" + defb([c * 17 for c in A.SKY]),
              "\n        ALIGN 256\nrd2_rec:\n" + defb(rec, 6),
              "\n        ALIGN 256\nrd2_rt0:\n" + page(runs, 0),
              "\n        ALIGN 256\nrd2_rt1:\n" + page(runs, 2),
              "\n        ALIGN 256\nrd2_st0:\n" + page(skips, 0),
              "\n        ALIGN 256\nrd2_st1:\n" + page(skips, 2),
              "\n" + "\n".join(body)]
    open(path, "w").write("\n".join(parts) + "\n")
    open(path.replace(".z80s", "hi.z80s"), "w").write(
        "; Generated by tests/mkroad2data.py - do not edit by hand.\n"
        "; The rest of the run bank, for above the screen buffers.\n"
        + "\n".join(hibody) + "\n")
    print("  %-44s %d widths, %d bytes of run and skip table"
          % ("wrote " + os.path.basename(path), len(ws), nrun))


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
