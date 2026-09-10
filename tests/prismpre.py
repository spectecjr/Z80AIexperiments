#!/usr/bin/env python3
"""A model of prismpre.z80s - prism.z80s with the frame precomputed.

prism.z80s spends 216,000 of its 536,000 T-states on work that depends
only on the frame number: the spin, the nine multiply tables, the
eight projected corners of each of seven pieces, the shade and the
visibility of each of the 42 faces, and the separating-plane sort that
puts the pieces back to front. All
of it can be worked out once and read out of a table at run time,
which leaves the rasteriser and nothing else.

What that costs is the length of the animation. A frame's table is

    112 bytes   seven pieces of eight (sx, sy)
     21 bytes   42 faces of a nibble: the ramp level, bit 3 set if the
                face is turned away
      7 bytes   the pieces, farthest first
      4 bytes   the box to erase, in renderlit's own record form

which is 144 bytes, and the free RAM either side of the two screen
buffers is 16K less the code. Sixty four frames fit. So the spin has
to come back to where it started in 64 frames, which means turn rates
that are multiples of four - one turn per axis per loop here, against
prism's two, three and one per 256.

Everything is generated from tests/prism.py, whose model is verified
byte-for-byte against prism.z80s, and the levels come out of the same
light() by asking it for a piece whose ramp starts at zero.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import raster
import prism as P

NFRAMES = 64                    # the loop, and what the free RAM allows
DA = (4, 4, 4)                  # turns per loop, one an axis
REC = 32                        # 7 order + 4 box + 21 colour
PTS = 112                       # 7 pieces of 8 points


class Logo(P.Logo):
    def __init__(self):
        P.Logo.__init__(self)
        self.da = list(DA)


def build(recip, lite):
    """The whole loop: per frame a 32-byte record, 112 bytes of point.

    Also returns the frames themselves, drawn exactly as prism's model
    draws them, which is what the Z80 has to match.
    """
    lo = Logo()
    recs, pts, bufs = bytearray(), bytearray(), []
    for f in range(NFRAMES):
        lo.spin()
        pp, nib = {}, {}
        bx0, bx1, by0, by1 = 255, 0, 255, 0
        for i, (quad, base) in enumerate(P.PIECES):
            pp[i] = P.t3d(P.verts(quad), lo.m, lo.p, recip)
            for x, y in pp[i]:
                bx0, bx1 = min(bx0, x), max(bx1, x)
                by0, by1 = min(by0, y), max(by1, y)
            # a piece whose ramp starts at zero gives the level itself
            vis, lev = P.light(lo.m, lo.p, lite, (quad, 0))
            nib[i] = [lev[k] | (0 if vis[k] else 8) for k in range(6)]
        order = P.order(lo.m, lo.p, P.boxes([pp[i] for i in range(len(pp))]))

        rec = bytearray(order)
        rec += bytes([by0, (by1 + 1) & 0xFF, bx0 >> 1, bx1 >> 1])
        for i in range(len(P.PIECES)):
            for k in range(0, 6, 2):
                rec.append(nib[i][k] | (nib[i][k + 1] << 4))
        assert len(rec) == REC, len(rec)
        recs += rec
        for i in range(len(P.PIECES)):
            for x, y in pp[i]:
                pts += bytes([x, y])

        buf = bytearray(raster.STRIDE * raster.H)
        for i in order:
            vis, col = P.light(lo.m, lo.p, lite, P.PIECES[i])
            for fi, idx in enumerate(raster.FACES):
                if vis[fi]:
                    raster.fill_quad(buf, [pp[i][k] for k in idx], col[fi])
        bufs.append(buf)
    assert len(pts) == NFRAMES * PTS
    return recs, pts, bufs


def main():
    from bench import Bench
    b = Bench("harness_prism.asm", org=0)
    s = b.syms
    recip = list(b.peek(s["t3d_recip"], 256))
    lite = [x - 256 if x > 127 else x for x in b.peek(s["rndl_lite"], 3)]
    recs, pts, bufs = build(recip, lite)
    print("  %d frames: %d bytes of record, %d of point, %d in all"
          % (NFRAMES, len(recs), len(pts), len(recs) + len(pts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
