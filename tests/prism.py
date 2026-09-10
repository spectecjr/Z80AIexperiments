#!/usr/bin/env python3
"""A model of prism.z80s - a lit extruded logo, in convex pieces.

renderlit.z80s draws a cube: eight vertices, six quad faces, one
dispatch each, with the face normals free because they are the columns
of the rotation matrix. An extruded quad has exactly the same shape -
eight vertices and six quad faces - so a logo cut into convex quads is
a handful of cubes that are not cubes, and renderlit draws them
unchanged.

What has to be found for each face rather than assumed:

  the normal    a side face's is the quad edge's 2D normal, and the
                front and back faces' is the z axis. Both are object
                space constants, so N.L and N.T are the same two
                transposed matrix-vector products renderlit already
                does, dotted with the face's own normal

  the plane     renderlit tests N.T + S < 0 with S the cube's half
                size; here it is N.T + (n . p) with p a point on the
                face, which is a constant per face too

  the order     the pieces are convex and disjoint but the whole is
                not convex, so they are drawn back to front by the
                depth of their centres, which is exact whenever a
                plane separates them - which for a flat logo it does

The shape here is provisional: a serif sigma of 45 degree angles and a
triangle with a triangular hole, from a description rather than from
the artwork. Everything except the numbers in PIECES is independent of
it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import raster
import rasterlit
from rasterlit import RAMP, shift7, s8
from test_democube import Model, SIN, smul7, addsat
from test_transform3d import model as t3d, s16

W, H, STRIDE = raster.W, raster.H, raster.STRIDE

D = 14                                  # how far the logo is extruded
TZ = 147 * 128                          # and how far away it sits
SCALE = 12                              # tenths: the logo's own units

# Both of those are pinned by sixteen bits and the near plane. t3d
# adds up to r*128 of rotated vertex onto the centre and the sum must
# stay in a signed word, so tz + r <= 255 units; and no vertex may
# come nearer than the reciprocal table's floor, so tz - r >= 40. That
# leaves r <= 107, which is the biggest this logo can be drawn - about
# a twelfth of the screen face on, a sixth when a corner swings near.
WHITE, RED = 0, 8                       # the two ramps

# The sigma, four quads, wound clockwise with y up; then the triangle's
# ring, three more. Shifted so the whole thing is centred on x.
SHIFT = 35


def _sigma():
    return [[(40, 48), (40, 32), (-40, 32), (-40, 48)],          # top bar
            [(40, -32), (40, -48), (-40, -48), (-40, -32)],      # bottom bar
            [(-16, 32), (16, 0), (-8, 0), (-40, 32)],            # upper arm
            [(16, 0), (-16, -32), (-40, -32), (-8, 0)]]          # lower arm


def _triangle():
    o = [(-110, 40), (-45, 0), (-110, -40)]     # pointing into the sigma
    i = [(-100, 22), (-64, 0), (-100, -22)]     # and its hole
    return [[o[0], o[1], i[1], i[0]],
            [o[1], o[2], i[2], i[1]],
            [o[2], o[0], i[0], i[2]]]


def _clockwise(q):
    """Wind a quad the way renderlit's face table expects."""
    area = sum((q[i][0] * q[(i + 1) % 4][1] - q[(i + 1) % 4][0] * q[i][1])
               for i in range(4))
    return q if area < 0 else q[::-1]


def _place(q):
    return _clockwise([((x + SHIFT) * SCALE // 10, y * SCALE // 10)
                       for x, y in q])


PIECES = ([(_place(q), WHITE) for q in _sigma()]
          + [(_place(q), RED) for q in _triangle()])

FACES = raster.FACES                    # renderlit's, unchanged


def verts(quad):
    """Eight vertices in the order renderlit's face table indexes.

    Its bit 2 is the x sign, bit 1 the y sign and bit 0 the z sign, so
    the quad's corners go in as (+,+), (+,-), (-,-), (-,+) and each
    one twice, front then back. Then its six faces are this prism's:
    four sides on the four edges, and the front and the back.
    """
    a, b, c, d = quad
    out = []
    for p in (a, b, d, c):
        out.append((p[0], p[1], D))
        out.append((p[0], p[1], -D))
    return out


def unit(x, y):
    """A 2D vector as a 1.7 signed pair, which is what the shade wants."""
    n = max(1.0, (x * x + y * y) ** 0.5)
    return (max(-127, min(127, int(round(127 * x / n)))),
            max(-127, min(127, int(round(127 * y / n)))))


def normals(quad):
    """Each face's normal and plane offset, in the face table's order.

    The sides come first, in the order the cube's +X, -X, +Y and -Y
    faces take them, and then the front and the back.
    """
    a, b, c, d = quad
    out = []
    for p0, p1 in ((a, b), (c, d), (d, a), (b, c)):
        nx, ny = unit(p1[1] - p0[1], p0[0] - p1[0])
        out.append(((nx, ny, 0), (nx * p0[0] + ny * p0[1]) // 128))
    out.append(((0, 0, 127), D))
    out.append(((0, 0, -127), D))
    return out


def light(m, t, lite, piece):
    """Which of a piece's faces face us, and how lit each one is."""
    w = [v >> 8 for v in t]
    cv = [sum(s8(m[k * 3 + a] & 0xFF) * w[k] for k in range(3))
          for a in range(3)]
    lv = [sum(s8(m[k * 3 + a] & 0xFF) * lite[k] for k in range(3))
          for a in range(3)]
    quad, base = piece
    vis, col = [], []
    for n, off in normals(quad):
        sh = shift7(sum((n[a] * lv[a]) >> 7 for a in range(3)))
        v = sum((n[a] * cv[a]) >> 7 for a in range(3)) + 64 * off
        vis.append(v < 0)
        col.append((base + RAMP[sh + 128]) & 15)
    return vis, col


def depth(m, t, quad):
    """The view z of a piece's centre, which is what orders them."""
    cx = sum(p[0] for p in quad) // 4
    cy = sum(p[1] for p in quad) // 4
    return s16(t[2] + m[6] * cx + m[7] * cy)


SPIN = [2, 3, 1]                        # turns per 256 frames, an axis each


class Logo(Model):
    def __init__(self):
        Model.__init__(self)
        self.p = [0, 0, TZ]
        self.da = list(SPIN)

    def frame(self, recip, lite, buf=None):
        self.spin()
        self.a = [(self.a[i] + 0) & 0xFF for i in range(3)]
        if buf is None:
            buf = bytearray(STRIDE * H)
        order = sorted(range(len(PIECES)),
                       key=lambda i: -depth(self.m, self.p, PIECES[i][0]))
        drawn = []
        for i in order:
            quad, base = PIECES[i]
            pts = t3d(verts(quad), self.m, self.p, recip)
            vis, col = light(self.m, self.p, lite, PIECES[i])
            for f, idx in enumerate(FACES):
                if vis[f]:
                    raster.fill_quad(buf, [pts[k] for k in idx], col[f])
                    drawn.append((i, f))
        return buf, order, drawn


def main():
    """Draw a few frames and say how big the logo gets."""
    from bench import Bench
    b = Bench("harness_renderlit.asm", org=0)
    s = b.syms
    recip = list(b.peek(s["t3d_recip"], 256))
    lite = [x - 256 if x > 127 else x for x in b.peek(s["rndl_lite"], 3)]
    PAL = ([(32 * i, 32 * i, 30 * i) for i in range(8)]
           + [(36 * i, 6 * i, 6 * i) for i in range(8)])
    lo = Logo()
    worst = 0
    for f in range(120):
        buf, order, drawn = lo.frame(recip, lite)
        xs = [i % STRIDE for i in range(len(buf)) if buf[i]]
        ys = [i // STRIDE for i in range(len(buf)) if buf[i]]
        if xs:
            area = (max(xs) - min(xs) + 1) * 2 * (max(ys) - min(ys) + 1)
            worst = max(worst, area)
        if f in (0, 40, 80, 119):
            raster.to_png(buf, "/tmp/prism%d.png" % f, PAL)
    print("  biggest bounding box %d pixels, %.0f%% of the screen"
          % (worst, 100.0 * worst / (256 * 192)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
