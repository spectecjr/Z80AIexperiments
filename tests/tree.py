#!/usr/bin/env python3
"""A Space Harrier tree, at the eight sizes the distance asks for.

    python3 tests/tree.py [out.png]

The arcade draws its scenery at eight discrete scales and lets an
object pop from one to the next as it comes in. Its tree is a narrow
cypress four times as tall as it is wide, foliage nearly to the ground
and a short dark trunk under it; the sizes on its sprite sheet are
4x15, 6x22, 8x31, 12x46, 16x63, 23x95, 31x122 and 40x158, which is a
step of about 1.4 each time. These are the same proportions, drawn
here rather than lifted - the same as the pilot and the pyramids.

THE SHAPE IS DRAWN AT EACH SIZE rather than scaled from one, because a
15 row tree resampled from a 158 row one is a mess. The silhouette is a
lozenge whose half width is a function of how far down it is, the
foliage is speckled to break it up, and the trunk is two pixels wider
at the foot than at the top.

IT COSTS NO PALETTE. Green is the desert's palms, the trunk is the near
pyramids' shadow brown, and the speckle and the outline are the pilot's
black: three indices the screen already has, because there are none
spare. The arcade's tree has five greens; this one has green, and a
deep shadow where its darkest green was.
"""
import os
import sys

CLEAR = -1
BLACK = 0                       # the outline, and the shadow in the leaves
GREEN = int(os.environ.get("TREE_GREEN", 13))   # the palms' green
BROWN = int(os.environ.get("TREE_BROWN", 14))   # and the pyramids' shadow

SIZES = (13, 19, 27, 39, 54, 81, 105, 135)      # scanlines: the arcade's
                                # own eight - 15, 22, 31, 46, 63, 95, 122
                                # and 158 - on a screen of 192 rows rather
                                # than its 224, which is the same tree and
                                # four thousand T-states cheaper at the
                                # size it matters
SPECKLE = int(os.environ.get("TREE_SPECKLE", 5))        # one leaf byte in
                                # this many goes dark. It is the whole
                                # texture and most of the cost: a run of
                                # PUSHes holds its pair in DE and reloads
                                # it wherever the colour changes, so every
                                # speck is 10 T-states


def width(h):
    """A tree h tall is this wide: the arcade's aspect, rounded up to a
    whole PUSH - four pixels.

    The box being a multiple of four costs nothing, because a
    transparent byte is one the compiled sprite skips, and it buys the
    sky behind the tree being put back with PUSHes rather than with a
    byte at a time: the fill writes pairs and never has an odd one.
    """
    return 4 * max(1, int(round(0.25 * h / 4)))


def profile(t):
    """Half the foliage's width, as a fraction of the sprite's, at t of
    the way down it. A point at the top, widest two thirds down, and
    drawn in again where the trunk comes through."""
    if t < 0.10:                        # the tip
        return 0.35 * (t / 0.10)
    if t < 0.70:                        # opening out
        return 0.35 + 0.65 * ((t - 0.10) / 0.60) ** 0.7
    if t < 0.86:                        # and the skirt of it
        return 1.0 - 0.35 * ((t - 0.70) / 0.16) ** 2
    return 0.0


def lcg(s):
    while True:
        s = (s * 1103515245 + 12345) & 0x7FFFFFFF
        yield s >> 7


def tree(h):
    """The tree h scanlines tall, as palette indices with CLEAR for air."""
    w = width(h)
    px = [[CLEAR] * w for _ in range(h)]
    r, half = lcg(7 + h), w / 2.0
    for y in range(h):
        k = profile((y + 0.5) / h) * half
        for x in range(w):
            if abs(x + 0.5 - half) <= k:
                px[y][x] = GREEN
    for y in range(h):                          # the speckle: a shadow in
        for x in range(w):                      # the leaves where the
            if px[y][x] != GREEN:               # arcade has its darkest
                continue                        # green, and none of it on
            edge = abs(x + 0.5 - half) > profile((y + 0.5) / h) * half - 1.2
            if not edge and next(r) % SPECKLE == 0:
                px[y][x] = BLACK
    base = int(0.80 * h)                        # the trunk, flaring at the
    for y in range(base, h):                    # foot
        k = 0.06 * w + 0.06 * w * (y - base) / max(1.0, h - base)
        for x in range(int(round(half - k)), int(round(half + k))):
            if 0 <= x < w:
                px[y][x] = BROWN
    return outline(px), w, h


def outline(px):
    """A black edge round everything, so the tree reads against a board
    of its own brightness - the pilot's trick."""
    h, w = len(px), len(px[0])
    out = [row[:] for row in px]
    for y in range(h):
        for x in range(w):
            if px[y][x] != CLEAR:
                continue
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                j, i = y + dy, x + dx
                if 0 <= j < h and 0 <= i < w and px[j][i] not in (CLEAR, BLACK):
                    out[y][x] = BLACK
                    break
    return out


def rows(px):
    """The tree as MODE 4 bytes and how to draw each: the pilot's four
    kinds, so that mksprite.py serves both.

        0   nothing here          2   the left pixel only
        1   both pixels           3   the right pixel only
    """
    out = []
    for row in px:
        by, kind = [], []
        for x in range(0, len(row), 2):
            a, b = row[x], row[x + 1]
            if a < 0 and b < 0:
                by.append(0)
                kind.append(0)
            elif a >= 0 and b >= 0:
                by.append((a << 4) | b)
                kind.append(1)
            elif a >= 0:
                by.append(a << 4)
                kind.append(2)
            else:
                by.append(b)
                kind.append(3)
        out.append((by, kind))
    return out


def main(path):
    from PIL import Image
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from mkchqdata import sam
    from mkgif import sam_rgb
    pal = {BLACK: (0, 0, 0), GREEN: sam_rgb(sam(2, 5, 2)),
           BROWN: sam_rgb(sam(4, 2, 0))}
    z, gap = 2, 6
    wide = sum(width(h) + gap for h in SIZES)
    im = Image.new("RGB", (wide * z, max(SIZES) * z), sam_rgb(sam(2, 4, 4)))
    p = im.load()
    at, drawn, masked = 0, 0, 0
    for h in SIZES:
        px, w, _ = tree(h)
        drawn += sum(1 for _, k in rows(px) for v in k if v)
        masked += sum(1 for _, k in rows(px) for v in k if v > 1)
        for y in range(h):
            for x in range(w):
                c = px[y][x]
                if c == CLEAR:
                    continue
                for dy in range(z):
                    for dx in range(z):
                        p[(at + x) * z + dx, (max(SIZES) - h + y) * z + dy] \
                            = pal[c]
        at += w + gap
    im.save(path)
    print("%s: %d sizes, %d to %d rows; %d bytes to draw in all, %d of them"
          " masked" % (path, len(SIZES), SIZES[0], SIZES[-1], drawn, masked))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/tree.png")
