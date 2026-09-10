#!/usr/bin/env python3
"""The Entropy logo, as convex quads, from the artwork.

Same conventions as the provisional shape in prism.py, which this does
not replace - that one is still there, and being simpler it is also
cheaper to draw:

  * y is up, and the quads are wound clockwise
  * every piece is convex, so renderlit's face table draws it as a
    prism with no changes
  * every pair of pieces must be separated by one of their own side
    faces, which is what pr_order's planes are built from
  * where two pieces meet, both own a face on the join and neither is
    on the outside of anything - buried() finds those and they are
    never drawn

The triangle is a ring, so it takes three trapezoids; the sigma is a
concave glyph and takes one convex piece an arm and a bar.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The artwork is about four units wide to three tall. Everything here
# is in artwork units with the origin at the middle of the logo, and
# prism.py's _place() scales and shifts it to fit the screen.

def sigma():
    """Four convex pieces: two bars and two arms.

    The extra vertices against the provisional shape are the steps
    where each bar meets its arm - the bars run past the arms rather
    than stopping at them.
    """
    return [
        # top bar, running right from the arm's shoulder
        [(96, 48), (96, 26), (-30, 26), (-30, 48)],
        # bottom bar
        [(96, -26), (96, -48), (-30, -48), (-30, -26)],
        # upper arm: from under the top bar down to the point
        [(-2, 26), (30, 0), (6, 0), (-30, 26)],
        # lower arm
        [(30, 0), (-2, -26), (-30, -26), (6, 0)],
    ]


def triangle():
    """A ring: an outline triangle pointing right, three trapezoids."""
    o = [(-104, 40), (-40, 0), (-104, -40)]     # the outer corners
    i = [(-92, 22), (-62, 0), (-92, -22)]       # and the hole's
    return [[o[0], o[1], i[1], i[0]],
            [o[1], o[2], i[2], i[1]],
            [o[2], o[0], i[0], i[2]]]


WHITE, RED = 0, 8
SHAPE = [(q, WHITE) for q in sigma()] + [(q, RED) for q in triangle()]


def preview(path, scale=3, grid=20):
    """Draw it flat, with a grid, so the numbers can be corrected."""
    from PIL import Image, ImageDraw
    w, h = 260, 120
    im = Image.new("RGB", (w * scale, h * scale), (16, 16, 16))
    d = ImageDraw.Draw(im)
    def pt(p):
        return ((p[0] + w // 2) * scale, (h // 2 - p[1]) * scale)
    for x in range(-w // 2, w // 2 + 1, grid):
        d.line([pt((x, -h // 2)), pt((x, h // 2))], (48, 48, 48))
        d.text(pt((x + 2, -h // 2 + 12)), str(x), fill=(120, 120, 120))
    for y in range(-h // 2, h // 2 + 1, grid):
        d.line([pt((-w // 2, y)), pt((w // 2, y))], (48, 48, 48))
        d.text(pt((-w // 2 + 2, y + 10)), str(y), fill=(120, 120, 120))
    for k, (quad, base) in enumerate(SHAPE):
        col = (230, 230, 225) if base == WHITE else (200, 40, 40)
        d.polygon([pt(p) for p in quad], fill=col, outline=(90, 90, 90))
        cx = sum(p[0] for p in quad) // 4
        cy = sum(p[1] for p in quad) // 4
        d.text(pt((cx, cy)), str(k), fill=(20, 20, 20))
    im.save(path)
    return path


if __name__ == "__main__":
    print(preview("/tmp/entropylogo.png"))
