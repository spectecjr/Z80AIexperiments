#!/usr/bin/env python3
"""A desert on the horizon: pyramids behind, dunes in front.

    python3 tests/desert.py [out.png]

Twenty-four scanlines between chequer5's board and the sky, holding two
layers that scroll at different speeds:

    the REAR layer   sky, pyramids, a far ridge, palms and rocks - one
                     pixel every three frames, which at 25 Hz is eight
                     pixels a second
    the FRONT layer  a nearer dune ridge, eight rows of it at the bottom
                     of the band, one pixel every frame

BOTH MOVE BY PIXELS, not bytes, which is what the city did and what
made it read as scenery on rails rather than as distance. A pixel is
half a MODE 4 byte, so this costs two things: the rear layer is
compiled twice, once per pixel phase, and the front layer's spans have
a read-modify-write at each end where the edge lands inside a byte.

THE REAR LAYER IS A PICTURE, NOT A SHAPE LIST. It is drawn here as
pixels and compiled into one run of PUSHes a (row, phase), so detail in
it is free at run time and costs only the DE reloads where the colour
changes. That is why it can have palms and rock fields and a two-tone
ridge, and why the city - drawn out of rectangles at run time - could
not.

THE FRONT LAYER IS A HEIGHTFIELD. One dune top a pixel column, which
gives per row the spans where the dune has already started (its body)
and the spans where it starts on this very row (its lit crest). Both
are intervals, so both are PUSHes over the rear layer.

The period is 256 pixels, the width of the screen, so the wrap is a
mask on both layers.
"""
import sys

ROWS = 24                       # scanlines of band
TOP = 73                        # the first of them; the board starts at 97
STRIDE = 128
PERIOD = 256                    # pixels, which is the screen's width

SKY = 1                         # the board's own sky index; the rest are
LIT, SAND, DARK = 7, 6, 5       # the pilot's, which are fixed: pale hazy
DUNE, CREST = 4, 12             # sand and a dull rose shadow for the far
                                # layer - aerial perspective, the far
                                # things paler - and for the near one the
                                # darkest red there is with an orange
                                # crest, because that is the one edge in
                                # the picture the eye should follow

REAR_EVERY = 3                  # frames a pixel, rear layer
GROUND = 17                     # the rear layer's own horizon, in rows


def lcg(s):
    while True:
        s = (s * 1103515245 + 12345) & 0x7FFFFFFF
        yield s >> 7


def pyramid(px, cx, half, high, gap=0):
    """A pyramid standing on the rear layer's ground line.

    The left face takes the light and the right is in shadow, which is
    the same sun the city had and the same one the pilot has.
    """
    for r in range(GROUND, GROUND - high - 1, -1):
        w = round(half * (GROUND - r) / high)
        for x in range(cx - half + w, cx + half - w + 1):
            c = LIT if x < cx else SAND
            if gap and abs(x - cx) < gap and r < GROUND - 2:
                c = SAND                # a course of stone in the light
            px[r][x % PERIOD] = c


def palm(px, x, h):
    """A palm: a trunk and four fronds, in silhouette."""
    for r in range(GROUND, GROUND - h, -1):
        px[r][x % PERIOD] = DARK
    top = GROUND - h
    for d, k in ((-3, 1), (-2, 0), (2, 0), (3, 1)):
        px[(top + k) % ROWS][(x + d) % PERIOD] = DARK
        px[top % ROWS][(x + d // 2) % PERIOD] = DARK


def rear():
    """The whole rear layer, 24 rows by 256 pixels, as palette indices."""
    px = [[SKY] * PERIOD for _ in range(ROWS)]
    r = lcg(9)

    for y in range(GROUND + 1, ROWS):           # the sand it all stands on
        for x in range(PERIOD):
            px[y][x] = SAND
    for x in range(PERIOD):                     # with a lit near edge and a
        px[GROUND + 1][x] = LIT                 # far ridge that undulates
    ridge = [GROUND - (1 if (x // 8 + next(r) % 2) % 3 == 0 else 0)
             for x in range(PERIOD)]
    for x in range(PERIOD):
        px[ridge[x]][x] = SAND

    pyramid(px, 40, 17, 14, gap=2)              # the big one, and two more
    pyramid(px, 96, 9, 8)                       # at other distances
    pyramid(px, 196, 12, 10, gap=1)
    pyramid(px, 220, 6, 5)

    for x in (132, 137, 143, 250):              # a stand of palms, and the
        palm(px, x, 5 + next(r) % 3)            # rocks are the detail that
    for _ in range(26):                         # a compiled run gets free
        x, y = next(r) % PERIOD, GROUND + 1 + next(r) % (ROWS - GROUND - 1)
        px[y][x] = DARK if next(r) % 3 else LIT
    return px


def heights():
    """The front layer's dune tops, one a pixel column.

    Three sines with different periods, which is enough to look like
    dunes and keeps the spans a row down to a handful.
    """
    import math
    out = []
    for x in range(PERIOD):
        t = 2 * math.pi * x / PERIOD
        h = (2.4 * math.sin(t) + 1.6 * math.sin(3 * t + 0.9)
             + 0.9 * math.sin(5 * t + 2.2))
        out.append(ROWS - 1 - max(0, int(round(2.2 + h))))
    return out


HEIGHTS = heights()


def spans():
    """Per row, the front layer's (x0, x1, colour) in layer pixels.

    A column whose dune top is this row is the lit crest; one whose top
    is above it is the body. Both come out as runs, which is what the
    Z80 draws.
    """
    out = []
    for y in range(ROWS):
        row, x = [], 0
        while x < PERIOD:
            c = (CREST if HEIGHTS[x] == y else
                 DUNE if HEIGHTS[x] < y else None)
            k = x
            while k < PERIOD and (CREST if HEIGHTS[k] == y else
                                  DUNE if HEIGHTS[k] < y else None) == c:
                k += 1
            if c is not None:
                row.append((x, k - 1, c))
            x = k
        out.append(row)
    return out


SPANS = spans()


def band(t):
    """The 24 rows of band at frame t, as MODE 4 bytes.

    The rear layer moves a pixel every three frames and the front one a
    pixel a frame, both to the left.
    """
    back, off = rear(), t // REAR_EVERY
    px = [[back[y][(x + off) % PERIOD] for x in range(PERIOD)]
          for y in range(ROWS)]
    for y, row in enumerate(SPANS):
        for x0, x1, c in row:
            for x in range(x0, x1 + 1):
                px[y][(x - t) % PERIOD] = c
    return [bytes((row[2 * i] << 4) | row[2 * i + 1] for i in range(STRIDE))
            for row in px]


def main(path):
    from PIL import Image
    import jetpack as J
    pal = {SKY: (30, 90, 200)}
    pal.update({i: tuple(v * 255 // 7 for v in J.PAL[i])
                for i in (LIT, SAND, DARK, DUNE, CREST)})
    n, z = 6, 3
    im = Image.new("RGB", (PERIOD * z, (ROWS + 1) * z * n))
    p = im.load()
    for f in range(n):
        for y, row in enumerate(band(f * 9)):
            for x in range(PERIOD):
                b = row[x >> 1]
                c = (b >> 4) if not (x & 1) else (b & 15)
                for dy in range(z):
                    for dx in range(z):
                        p[x * z + dx, (f * (ROWS + 1) + y) * z + dy] = pal[c]
    im.save(path)
    ns = sum(len(r) for r in SPANS)
    print("%s: %d front spans over %d rows, %d of them lit crest"
          % (path, ns, sum(1 for r in SPANS if r),
             sum(1 for r in SPANS for s in r if s[2] == CREST)))


if __name__ == "__main__":
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/desert.png")
