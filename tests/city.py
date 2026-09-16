#!/usr/bin/env python3
"""A city on the horizon: two layers of buildings, scrolling at
different speeds.

    python3 tests/city.py [out.png]

Sixteen scanlines sitting straight on top of chequer5's board, which
starts at row 97. Everything in the band is a rectangle - a building is
a run of whole bytes wide and a number of rows tall - so drawing one is
`SP` and a compiled run of `PUSH`es, and the whole band is

    sky, then the far buildings over it, then the near ones over them.

That is overdraw: a byte under a near building is written three times.
The alternative is merging two interval lists a row on a Z80, and the
merge costs more than the pixels it saves. The band is 2,048 bytes and
the floor for writing those is 11,264 T-states; the overdraw adds about
nine thousand and the whole band measures 30,000.

WHAT THE PARALLAX COSTS IS ONE BYTE. The far layer moves one byte a
frame and the near one two, so an offset can be odd, and where a
building wraps round the screen's right hand edge that leaves a part
with an odd width - which `PUSH` cannot write, because it writes two
bytes at a time. So a part of odd width has its left hand byte drawn as
a column of its own, sixteen `LD (HL),A` at 31 T-states a row. There is
at most one such column a layer a frame.

THE LEFT FACE IS LIT, and free: a run's last `PUSH` is its leftmost, so
the block ends `PUSH BC` where every other push is `PUSH DE`. Make BC
the same as DE and the building is flat, which is what the far layer
does; make it lighter and the near layer gets a four pixel highlight
down its left side for nothing at all.
"""
import sys

ROWS = 16                       # scanlines of band
TOP = 81                        # the first of them; the board starts at 97
STRIDE = 128                    # bytes a scanline, and a layer's period,
                                # which is what makes the wrap a mask

SKY = 1                         # the board's own sky index, and three of
FAR, NEAR, LIT = 11, 10, 8      # the pilot's, which are fixed: mid grey
                                # for the far layer, darker for the near
                                # one - aerial perspective, the far things
                                # paler - and a light grey left face


def skyline(seed, hlo, hhi, wlo, whi, glo, ghi):
    """A layer of buildings: (x, width, height), widths in whole bytes.

    Widths are even so that a building that does not wrap needs no odd
    column, and the heights come off a cheap LCG quantised to a few
    values, because a skyline reads better when shapes recur. The last
    building of a layer runs past the period's end and wraps, which the
    drawing has to handle anyway.
    """
    out, x, s = [], 0, seed
    while x < STRIDE:
        s = (s * 1103515245 + 12345) & 0x7FFFFFFF
        w = 2 * (wlo + (s >> 7) % (whi - wlo + 1))
        s = (s * 1103515245 + 12345) & 0x7FFFFFFF
        h = hlo + (s >> 7) % (hhi - hlo + 1)
        s = (s * 1103515245 + 12345) & 0x7FFFFFFF
        gap = glo + (s >> 7) % (ghi - glo + 1)
        out.append((x, w, h))
        x += w + gap
    return out


FARS = skyline(11, 3, 8, 2, 5, 1, 3)
NEARS = skyline(29, 5, 13, 3, 6, 5, 14)


def parts(x, w, off):
    """Where a building lands, and how the screen's edge cuts it.

    A layer's period is the screen's width, so the wrap is one mask and
    a building is in one piece or two. The piece with the left face is
    the one that carries the light.
    """
    u = (x - off) % STRIDE
    if u + w <= STRIDE:
        return [(u, w, True)]
    return [(u, STRIDE - u, True), (0, u + w - STRIDE, False)]


def stamp(px, u, w, left, body, lit, rows):
    """One part, byte for byte as the Z80 draws it.

    An odd width leaves a single byte at the left, which is a column of
    its own; the pairs after it go right to left and the last of them -
    the leftmost - is the lit one.
    """
    cols = []
    if w & 1:
        cols.append((u, lit if left else body))
    for k in range(w >> 1):
        c = (lit if left else body) if k == 0 else body
        cols += [(u + (w & 1) + 2 * k, c), (u + (w & 1) + 2 * k + 1, c)]
    for r in range(ROWS - rows, ROWS):
        for i, c in cols:
            if 0 <= i < STRIDE:
                px[r][i] = c


def band(t):
    """The 16 rows of band at frame t, as MODE 4 bytes.

    The far layer moves a byte a frame and the near one two, both to the
    left, which is the parallax.
    """
    px = [[SKY] * STRIDE for _ in range(ROWS)]
    for blds, off, body, lit in ((FARS, t % STRIDE, FAR, FAR),
                                 (NEARS, 2 * t % STRIDE, NEAR, LIT)):
        for x, w, h in blds:
            for u, wp, left in parts(x, w, off):
                stamp(px, u, wp, left, body, lit, h)
    return [bytes(c * 17 for c in row) for row in px]


def main(path):
    from PIL import Image
    import jetpack as J
    pal = {SKY: (30, 90, 200)}
    pal.update({i: tuple(v * 255 // 7 for v in J.PAL[i])
                for i in (FAR, NEAR, LIT)})
    n, z = 8, 3
    im = Image.new("RGB", (256 * z, (ROWS + 1) * z * n))
    p = im.load()
    for f in range(n):
        for y, row in enumerate(band(f * 3)):
            for x in range(256):
                b = row[x >> 1]
                c = (b >> 4) if not (x & 1) else (b & 15)
                for dy in range(z):
                    for dx in range(z):
                        p[x * z + dx, (f * (ROWS + 1) + y) * z + dy] = pal[c]
    im.save(path)
    odd = sum(1 for t in range(STRIDE)
              for blds, off in ((FARS, t % STRIDE), (NEARS, 2 * t % STRIDE))
              for x, w, _ in blds for _, wp, _ in parts(x, w, off) if wp & 1)
    print("%s: %d far buildings, %d near, %.2f odd columns a frame"
          % (path, len(FARS), len(NEARS), odd / STRIDE))


if __name__ == "__main__":
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/city.png")
