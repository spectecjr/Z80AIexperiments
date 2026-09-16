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
            if mark[y] != p:            # the band has moved on under it,
                mark[y] = p             # so the grass either side of the
                f = sp & ~1             # window is stale - but not the
                left = sp + 2 * skip - 2 * grid(w, 1)[1]        # window
                if left > 0:            # itself, which the road is about
                    n = (left + 1) & ~1                 # to cover anyway
                    dst[row:row + n] = bytes([grass]) * n
            elif dirt < 128:            # the row below spilled into it
                f = max(dirt, sp) & ~1
            else:
                f = 128
            if f < 128:
                dst[row + f:row + 128] = bytes([grass]) * (128 - f)
            phase = (c + w + M + 1) & 1
            r = run(w, k, lw, phase, p)
            if skip:                        # what the last skipped PUSH
                dst[row + 127] = r[skip - 1][0]         # would have put at
                                        # the screen's own right hand edge.
                                        # Unconditional: where it was not
                                        # wanted the run covers it again
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


TABLES = 8 * 256                # the eight index pages at the foot of a
                                # chunk: a page for each (parity, phase) of
                                # the run table and of the stub table, so
                                # that the page is the parity and the phase
                                # and the offset is the width
CHUNK = 0x7F00 - TABLES         # and what is left of the 32K window for
                                # runs, less a little for the caller's stack
RD2_OUT = 0xE003                # where a run goes when it is done: a fixed
                                # address, because a chunk is assembled on
                                # its own and knows nothing of the code


def emit_runs(ws, kw, lw):
    """The compiled runs, the stubs that enter them part way, and the
    two index tables.

    A run is the whole window - grass margin, road, grass margin - one
    PUSH per four pixels of it, with the value reloaded only where it
    changes. Entering one part way in is not arithmetic: it is a mix of
    one-byte PUSHes and four-byte LD HL,nn / PUSH pairs, and the PUSH
    that `skip` lands on may be one whose LD went with the part that
    was skipped. So each run carries a stub per skip, seven bytes:

        DEFB  the byte the last skipped PUSH would have put at the
              screen's own right hand edge
        LD    HL,what it would have left there
        JP    into the run

    which is one lookup and a JP (HL) at run time, and no offset
    arithmetic at all. The odd byte is stored unconditionally, because
    where it was not wanted the run's own first PUSH covers it.

    Skipping nothing needs no stub: a run starts by loading HL itself.
    """
    groups, runs, stubs, n = [], {}, {}, 0
    for w in ws:
        out, size = [], 0
        for par in (0, 1):
            for ph in (0, 1):
                nm = "rd2_r%d_%d_%d" % (w, ph, par)
                sm = "rd2_s%d_%d_%d" % (w, ph, par)
                runs[(w, ph, par)] = nm
                stubs[(w, ph, par)] = sm
                r = run(w, kw[w], lw[w], ph, par)
                off, last, pos = [], None, 0
                for a, b in r:
                    off.append(pos)
                    if (a, b) != last:
                        pos += 4
                        last = (a, b)
                    else:
                        pos += 1
                out.append(sm + ":")
                for sk in range(1, maxskip(w) + 1):
                    out.append("        DEFB %d" % r[sk - 1][0])
                    out.append("        LD   HL,%d"
                               % ((r[sk][1] << 8) | r[sk][0]))
                    out.append("        JP   %s + %d" % (nm, off[sk]))
                out.append(nm + ":")
                last = None
                for a, b in r:
                    if (a, b) != last:
                        out.append("        LD   HL,%d" % ((b << 8) | a))
                        last = (a, b)
                    out.append("        PUSH HL")
                out.append("        JP   RD2_OUT")
                size += pos + 3 + 7 * maxskip(w)
        groups.append((w, size, "\n".join(out)))
        n += size
    return groups, runs, stubs, n


def emit(here):
    """Write the two bank chunks and the resident tables.

    The bank is paged, so it is cut into chunks of a 32K window rather
    than squeezed either side of the screens. A chunk carries its own
    index tables at its foot - eight pages, one for each (parity, phase)
    of the run table and of the stub table - so the row loop's lookup is
    the same code whichever chunk is in, and a chunk needs to know
    nothing about the code except where a run goes when it is done.

    Widths are cut in the order the screen is drawn, bottom row first,
    so a frame walks the bank forwards and pages once.
    """
    ws, wix = widths()
    kw = {A.WTAB[y]: A.KTAB[y] for y in range(A.HZ + 1, A.H)}
    lw = {A.WTAB[y]: A.LTAB[y] for y in range(A.HZ + 1, A.H)}
    groups, runs, stubs, nrun = emit_runs(ws, kw, lw)
    order = sorted(groups, key=lambda g: -g[0])         # widest first
    banks, used, at = [[]], [0], {}
    for w, size, text in order:
        if used[-1] + size > CHUNK:
            banks.append([])
            used.append(0)
        banks[-1].append(text)
        used[-1] += size
        at[w] = len(banks) - 1

    rec, seg = [], []
    for y in range(A.H - 1, A.HZ, -1):
        w = A.WTAB[y]
        rec += [A.ZTAB[y] & 255, A.ZTAB[y] >> 8, w + M + 1, wix[w] * 2,
                2 * grid(w, 1)[1], 255]
        lmpr = 0x20 | 2 * at[w]         # RAM over ROM 0, and the chunk
        if seg and seg[-1][0] == lmpr:  # this row's run is in. The rows
            seg[-1][1] += 1             # are drawn widest first and the
        else:                           # bank is cut in the same order,
            seg.append([lmpr, 1])       # so this is two runs of rows and
    seg.append([0, 0])                  # the paging is two OUTs a frame

    pal = [0] * 16
    for i, c in ((A.SKY0, (0, 0, 4)), (A.SKY1, (0, 2, 6)), (A.SKY2, (2, 4, 6)),
                 (A.SKY3, (4, 6, 6)), (A.GRASS0, (0, 4, 0)),
                 (A.GRASS1, (0, 6, 2)), (A.TARMAC0, (2, 2, 2)),
                 (A.TARMAC1, (4, 4, 4)), (A.KERB0, (6, 0, 0)),
                 (A.KERB1, (6, 6, 6)), (A.LINE, (6, 6, 4))):
        pal[i] = sam(*c)

    def table(labels, par, ph, bank):
        """One index page: a word a width, and nothing for the widths
        that are not in this chunk."""
        return "\n".join("        DEFW %s"
                          % (labels[(w, ph, par)] if at[w] == bank else "0")
                          for w in ws)

    for bank, body in enumerate(banks):
        parts = ["; Generated by tests/mkroad2data.py - do not edit by hand.",
                 "; Chunk %d of the run bank: LMPR pages it in at 0x0000."
                 % bank,
                 "\nRD2_OUT:        EQU 0x%04X      ; where a run goes when"
                 " it is done" % RD2_OUT,
                 "\n        ORG 0x0000"]
        for kind, labels in (("rt", runs), ("st", stubs)):
            for par in (0, 1):
                for ph in (0, 1):
                    parts.append("\n        ALIGN 256\nrd2_%s%d%d_%d:\n%s"
                                 % (kind, par, ph, bank,
                                    table(labels, par, ph, bank)))
        parts.append("\n        ALIGN 256")
        parts += body
        parts.append("\n        ASSERT $ <= 0x%04X       ; the window, less"
                     " the caller's stack" % (CHUNK + TABLES))
        open(os.path.join(here, "roaddata2%s.z80s" % "abcdef"[bank]),
             "w").write("\n".join(parts) + "\n")

    parts = ["; Generated by tests/mkroad2data.py - do not edit by hand.",
             "\nRD2_OUT:        EQU 0x%04X      ; where a run goes when it is"
             " done, which" % RD2_OUT,
             ";                               ; the bank has baked in",
             "RD2_HZ:         EQU %d" % A.HZ,
             "RD2_ROWS:       EQU %d          ; scanlines of road"
             % (A.H - 1 - A.HZ),
             "RD2_M:          EQU %d           ; the repaint margin, pixels"
             % M,
             "RD2_REC:        EQU 6           ; bytes of record a row",
             "RD2_CLO:        EQU %d          ; and the rails the centre"
             % A.CLO,
             "RD2_CHI:        EQU %d         ; is held between" % A.CHI]
    for nm, v in (("GRASS", A.GRASS0), ("TARMAC", A.TARMAC0),
                  ("KERB", A.KERB0), ("LINE", A.LINE)):
        parts.append("RD2_%-11s EQU 0x%02X%02X" % (nm + ":", v * 17, v * 17))
    open(os.path.join(here, "roaddata2equ.z80s"), "w").write(
        "\n".join(parts) + "\n")
    open(os.path.join(here, "roaddata2rec.z80s"), "w").write(
        "; Generated by tests/mkroad2data.py - do not edit by hand.\n"
        "; The resident tables: the track, the palette, the sky, and a\n"
        "; record a row - which is where the band each buffer last\n"
        "; painted is remembered, one copy a buffer.\n"
        + "\n".join(["\nrd2_seg:\n" + defb([n for s in seg for n in s]),
                     "\n        ALIGN 256\nrd2_trk:\n" + defw(A.TRACK),
                     "\nrd2_pal:\n" + defb(pal),
                     "\nrd2_sky:\n" + defb([c * 17 for c in A.SKY]),
                     "\nrd2_rec:\n" + defb(rec, 6)]) + "\n")
    print("  %-44s %d widths, %d bytes in %d chunk%s of %d"
          % ("wrote the bank", len(ws), nrun, len(banks),
             "" if len(banks) == 1 else "s", max(used)))


if __name__ == "__main__":
    ws, _ = widths()
    n = sum(len(run(w, 0, 1, ph, p)) for w in ws for ph in (0, 1)
            for p in (0, 1))
    print("  %-44s %3d widths, %d PUSHes of run" % ("the bank", len(ws), n))
    push, dispatch = cost()
    print("  %-44s %d PUSHes a frame, %d T-states"
          % ("a frame", push, push * 11 + dispatch))
    emit(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.exit(1 if check() else 0)
