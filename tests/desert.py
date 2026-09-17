#!/usr/bin/env python3
"""A desert on the horizon: dunes and a great pyramid behind, smaller
pyramids in front of them.

    python3 tests/desert.py [out.png]

Thirty-two scanlines between chequer8's board - which is the bottom 40%
of the screen - and the sky, holding two layers that scroll at
different speeds:

    the REAR layer   sky, the great pyramid, a dune field, palms and
                     rocks, at 21 focal lengths of depth
    the FRONT layer  three smaller pyramids standing nearer, at 10.7 -
                     half the depth, so exactly twice the motion

BOTH ARE DRIVEN BY THE CAMERA, not by a frame counter: a layer at depth
Z shifts by FOCAL * camx / Z pixels when the camera slides sideways, so
the offsets are the camera's own camx, tripled and shifted right by six
and by five. Slide the camera right and the board's squares go left, the
front pyramids go left half as fast, and the great one behind them half
as fast again. At the camera's fastest that is two pixels a frame for
the front layer and one for the rear.

THE FRONT PYRAMIDS OVERLAP THE REAR LAYER, which is the whole point of
them: something passing in front of something else at a different rate
is the one depth cue that does not need colour or perspective. It is
also what makes them cost what they cost. The rear layer is compiled -
one run of PUSHes a (row, phase), so its detail is free - but a layer
that has to leave the one behind it showing cannot be a run. It is
drawn as spans, and where a span's edge lands inside a MODE 4 byte the
byte is read, masked and written so that the pixel beside it keeps the
pyramid behind.

BOTH LAYERS MOVE BY PIXELS, not bytes. A pixel is half a byte, so the
rear layer is compiled at all four pixel phases and the front layer's
ends are the masked bytes above.

The period is 256 pixels, the width of the screen, so the wrap on both
layers is what the subtraction does on its own.
"""
import sys

ROWS = 32                       # scanlines of band
TOP = 83                        # the first of them; the board starts at 115
STRIDE = 128
PERIOD = 256                    # pixels, which is the screen's width

SKY = 1                         # the board's own sky index; the rest are
LIT, SAND, DARK = 7, 6, 5       # the pilot's, which are fixed. The great
FLIT, FDARK = 12, 4             # pyramid is pale sand with a dull rose
                                # shadow - aerial perspective, the far
                                # things paler - the dune field below it
                                # is darker still, and the front pyramids
                                # are an orange lit face against the
                                # darkest red there is, because nearer
                                # means more contrast, not more detail

FAR_SHIFT, NEAR_SHIFT = 6, 5    # how deep the two layers are: a layer at
                                # depth Z moves FOCAL * camx / Z pixels
                                # when the camera slides, and camx times
                                # three shifted by six and by five is a
                                # depth of 4,715 and 2,357 world units -
                                # 21.3 and 10.7 focal lengths. At the
                                # camera's fastest, twenty world units a
                                # frame, that is a pixel a frame for the
                                # rear layer and two for the front, and
                                # the front is exactly twice the rear
                                # because it is the same number shifted
                                # one place less
GROUND = 24                     # the rear layer's own horizon, in rows


def offsets(camx):
    """Where the two layers stand, from the camera's sideways position.

    Both are drawn on the horizon, which strictly means infinitely far
    away and no parallax at all - the shifts above are the arcade fudge
    that every game of this kind makes, and they are what ties the
    scenery to the board underneath it: slide the camera right and both
    move left, the board by a square and the desert by a few pixels.

    The Z80 keeps the low byte of each, so this does too.
    """
    return (3 * camx >> FAR_SHIFT) & 0xFF, (3 * camx >> NEAR_SHIFT) & 0xFF


def lcg(s):
    while True:
        s = (s * 1103515245 + 12345) & 0x7FFFFFFF
        yield s >> 7


def pyramid(px, cx, half, high, base, lit, shade, course=0):
    """A pyramid standing on a ground line, its left face in the light.

    Rows are drawn from the base up, the width falling away linearly,
    which is what a pyramid is and also what makes every row of one a
    pair of runs - one lit, one in shadow.
    """
    for r in range(base, base - high - 1, -1):
        w = round(half * (base - r) / high)
        for x in range(cx - half + w, cx + half - w + 1):
            c = lit if x < cx else shade
            if course and abs(x - cx) < course and r < base - 2:
                c = shade               # a course of stone in the light
            if 0 <= r < ROWS:
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
    """The whole rear layer, 32 rows by 256 pixels, as palette indices."""
    import math
    px = [[SKY] * PERIOD for _ in range(ROWS)]
    r = lcg(9)

    for y in range(GROUND, ROWS):               # the dune field it all
        for x in range(PERIOD):                 # stands on
            px[y][x] = DARK

    pyramid(px, 56, 42, 22, GROUND, LIT, SAND, course=4)    # the great one
    pyramid(px, 170, 20, 12, GROUND, LIT, SAND)             # and a lesser
    pyramid(px, 202, 11, 7, GROUND, LIT, SAND)              # pair beside it

    for amp, f, ph, base, crest in ((1.8, 2, 0.7, GROUND + 2, LIT),
                                    (2.2, 3, 2.3, GROUND + 4, SAND),
                                    (1.6, 5, 4.1, GROUND + 7, SAND)):
        for x in range(PERIOD):                 # three ridges of dune, the
            t = 2 * math.pi * x / PERIOD        # nearer ones lower and the
            d = base + int(round(amp * math.sin(f * t + ph)      # far one
                                 + 0.9 * math.sin(11 * t + ph)))  # palest
            for y in range(max(0, d), ROWS):
                px[y][x] = DARK
            if 0 <= d < ROWS:
                px[d][x] = crest                # the crest catches the sun

    for x in (108, 114, 120, 236):              # a stand of palms, and the
        palm(px, x, 5 + next(r) % 3)            # rocks are the detail a
    for _ in range(34):                         # compiled run gets free
        x, y = next(r) % PERIOD, GROUND + 1 + next(r) % (ROWS - GROUND - 1)
        px[y][x] = SAND if next(r) % 3 else LIT
    return px


# The front layer: three pyramids standing on the bottom row of the band,
# which is nearer than the rear layer's ground line, and smaller than the
# great pyramid behind them - so they pass in front of it.
FRONTS = ((36, 15, 9), (128, 21, 11), (206, 12, 7))


def spans():
    """Per row, the front layer's (x0, x1, colour) in layer pixels.

    A pyramid's row is two runs, the lit face and the shadow: exactly
    what the Z80 draws, and why the front layer is spans rather than a
    compiled run.
    """
    out = [[] for _ in range(ROWS)]
    for cx, half, high in FRONTS:
        base = ROWS - 1
        for r in range(base, base - high - 1, -1):
            w = round(half * (base - r) / high)
            x0, x1 = cx - half + w, cx + half - w
            if x0 <= cx - 1:                    # the apex is one pixel of
                out[r].append((x0 % PERIOD, (cx - 1) % PERIOD, FLIT))
            if cx <= x1:                        # shadow and no lit face
                out[r].append((cx % PERIOD, x1 % PERIOD, FDARK))
    return out


SPANS = spans()


def band(far, near):
    """The 32 rows of band at these two offsets, as MODE 4 bytes.

    Both layers move left as their offset grows, which is the way the
    board's own pattern moves when the camera slides right.
    """
    back = rear()
    px = [[back[y][(x + far) % PERIOD] for x in range(PERIOD)]
          for y in range(ROWS)]
    for y, row in enumerate(SPANS):
        for x0, x1, c in row:
            n = (x1 - x0) % PERIOD + 1
            for k in range(n):
                px[y][(x0 + k - near) % PERIOD] = c
    return [bytes((row[2 * i] << 4) | row[2 * i + 1] for i in range(STRIDE))
            for row in px]


def main(path):
    from PIL import Image
    import jetpack as J
    pal = {SKY: (30, 90, 200)}
    pal.update({i: tuple(v * 255 // 7 for v in J.PAL[i])
                for i in (LIT, SAND, DARK, FLIT, FDARK)})
    n, z = 6, 3
    im = Image.new("RGB", (PERIOD * z, (ROWS + 1) * z * n))
    p = im.load()
    for f in range(n):
        for y, row in enumerate(band(*offsets(f * 192))):
            for x in range(PERIOD):
                b = row[x >> 1]
                c = (b >> 4) if not (x & 1) else (b & 15)
                for dy in range(z):
                    for dx in range(z):
                        p[x * z + dx, (f * (ROWS + 1) + y) * z + dy] = pal[c]
    im.save(path)
    ns = sum(len(r) for r in SPANS)
    print("%s: %d front spans over %d rows, %d pixels of them"
          % (path, ns, sum(1 for r in SPANS if r),
             sum((x1 - x0) % PERIOD + 1 for r in SPANS for x0, x1, _ in r)))


if __name__ == "__main__":
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/desert.png")
