#!/usr/bin/env python3
"""The Entropy logo, traced from entropylogo.png, as convex quads.

The artwork is 138x99. Its outlines came out of the pixels rather than
by eye: the white and red regions were boundary-traced and simplified,
which gave the sigma twelve vertices and the triangle three plus three
for its hole. Those are turned into the model's frame here - y up,
origin at the middle of the artwork at (70, 48) - and cut into convex
quads, which is what prism's pipeline needs:

  * convex, and wound clockwise with y up
  * every pair of pieces separated by one of their own side faces
  * where two pieces meet, both own a face on the join and neither is
    on the outside of anything - prism's buried() finds those

The provisional shape in prism.py is still there and is cheaper: this
one is nine pieces against seven, because the sigma's ends are cut
back to points and its left edge is notched.

    python3 tests/entropylogo.py     # draw it, and score it against
                                     # the artwork it was traced from
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ART = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "entropylogo.png")
CX, CY = 70, 48                 # the artwork's middle, in its own pixels

# The traced outlines, in model coordinates. The sigma is symmetric
# about y = 0, so only the top half is written out and the bottom is
# its mirror.
#
#   (-46, 47) ------------------------------ (66, 47)   the top edge
#        \                                  /
#         \        (-1,37) --- (40,37)     /
#          \           \            \     /
#           \           \         (43,23)      the bar's end, cut to
#            \           \                     a point
#             \        (36, 0)
#          (-1, 0)                            the left edge, notched

SIGMA_TOP = [
    # the bar, left of where its end starts to taper
    [(-46, 47), (40, 47), (40, 37), (-36, 37)],
    # and the tapered end, down to its point
    [(40, 47), (66, 47), (43, 23), (40, 37)],
    # the arm, from under the bar down to the middle
    [(-1, 37), (36, 0), (-1, 0), (-36, 37)],
]

TRI_OUT = [(-67, 38), (-29, 0), (-67, -38)]     # the triangle
TRI_IN = [(-55, 7), (-47, 0), (-55, -7)]        # and its hole


def mirror(quad):
    """The same quad below the axis, wound the same way round."""
    return [(x, -y) for x, y in quad][::-1]


def sigma():
    return SIGMA_TOP + [mirror(q) for q in SIGMA_TOP]


def triangle():
    o, i = TRI_OUT, TRI_IN
    return [[o[0], o[1], i[1], i[0]],
            [o[1], o[2], i[2], i[1]],
            [o[2], o[0], i[0], i[2]]]


WHITE, RED = 0, 8
SHAPE = [(q, WHITE) for q in sigma()] + [(q, RED) for q in triangle()]


def area(q):
    return sum(q[i][0] * q[(i + 1) % 4][1] - q[(i + 1) % 4][0] * q[i][1]
               for i in range(4))


def convex(q):
    cr = []
    for i in range(4):
        a, b, c = q[i], q[(i + 1) % 4], q[(i + 2) % 4]
        cr.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
    cr = [x for x in cr if x]
    return all(x < 0 for x in cr) or all(x > 0 for x in cr)


def check():
    bad = 0
    for k, (q, _) in enumerate(SHAPE):
        if area(q) >= 0 or not convex(q):
            print("  piece %d: %s %s" % (k, "anticlockwise" if area(q) >= 0
                                         else "clockwise",
                                         "" if convex(q) else "NOT CONVEX"))
            bad += 1
    print("  %-34s %d pieces, %d wrong" % ("convex and clockwise", len(SHAPE), bad))
    return bad


def score():
    """Rasterise the vectors at the artwork's own size and diff them."""
    from PIL import Image, ImageDraw
    art = Image.open(ART).convert("RGB")
    w, h = art.size
    ap = art.load()

    def cls(p):
        r, g, b = p
        if r > 120 and g < 90 and b < 90: return 1        # red
        return 2 if (r + g + b) > 300 else 0              # white, black

    mine = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(mine)
    for quad, base in SHAPE:
        col = (255, 255, 255) if base == WHITE else (219, 0, 0)
        d.polygon([(x + CX, CY - y) for x, y in quad], fill=col)
    mp = mine.load()
    n = sum(1 for y in range(h) for x in range(w)
            if cls(ap[x, y]) != cls(mp[x, y]))
    print("  %-34s %d of %d pixels differ (%.1f%%)"
          % ("against the artwork", n, w * h, 100.0 * n / (w * h)))
    return mine, art


def preview(path="/tmp/entropylogo_check.png", scale=3):
    from PIL import Image
    mine, art = score()
    w, h = art.size
    out = Image.new("RGB", (w * 2 + 8, h), (40, 40, 40))
    out.paste(art, (0, 0))
    out.paste(mine, (w + 8, 0))
    out = out.resize((out.width * scale, out.height * scale), Image.NEAREST)
    out.save(path)
    return path


if __name__ == "__main__":
    check()
    print(" ", preview())
