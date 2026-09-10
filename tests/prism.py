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


# Which logo. The provisional one is the default and nothing that was
# measured against it moves; PRISM_SHAPE=entropy swaps in the traced
# artwork, which is nine pieces rather than seven.
LOGO = os.environ.get("PRISM_SHAPE", "provisional")

if LOGO == "entropy":
    import entropylogo
    SHIFT = 0                           # it is already centred
    PIECES = [(_place(q), b) for q, b in entropylogo.SHAPE]
else:
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
        # the quads are wound clockwise, so the outward normal of the
        # edge p0 -> p1 is (-dy, dx). (dy, -dx) is the inward one, and
        # with that every side face is culled when it should be drawn
        # and kept when it should not - and a face kept wrongly is
        # wound backwards on screen, so its spans come out empty and
        # nothing is drawn at all. The logo looked like its front face
        # and nothing else.
        nx, ny = unit(p0[1] - p1[1], p1[0] - p0[0])
        out.append(((nx, ny, 0), (nx * p0[0] + ny * p0[1]) // 128))
    out.append(((0, 0, 127), D))
    out.append(((0, 0, -127), D))
    return out


def _edges(quad):
    a, b, c, d = quad
    return [(a, b), (c, d), (d, a), (b, c)]     # renderlit's face order


def _onseg(p, q0, q1):
    """p on the segment q0-q1, in integers, ends included."""
    if (q1[0] - q0[0]) * (p[1] - q0[1]) - (q1[1] - q0[1]) * (p[0] - q0[0]):
        return False
    dot = (p[0] - q0[0]) * (q1[0] - q0[0]) + (p[1] - q0[1]) * (q1[1] - q0[1])
    return 0 <= dot <= (q1[0] - q0[0]) ** 2 + (q1[1] - q0[1]) ** 2


def buried():
    """A six-bit mask a piece: faces that are inside the solid.

    The pieces are a cut-up of one plate, so wherever two of them meet
    both own a side face on the join and neither face is part of the
    plate's surface. The triangle is three trapezoids meeting at three
    mitred corners, which is six such faces; the sigma's arms meet each
    other and sit against the bars, which is four more. Their normals
    are opposite, so exactly one of each pair passes the cull every
    frame - 4.6 faces and 429 pixels of fill a frame, 12% of all of it,
    for something that is never on the outside of anything.

    Drawn, they are also what a painter order gets wrong: a piece
    ordered too near shows the wall it shares with its neighbour.
    """
    out = []
    for i, (qi, _) in enumerate(PIECES):
        mask = 0
        for e, (p0, p1) in enumerate(_edges(qi)):
            for j, (qj, _) in enumerate(PIECES):
                if j == i:
                    continue
                for r0, r1 in _edges(qj):
                    if not (_onseg(p0, r0, r1) and _onseg(p1, r0, r1)):
                        continue
                    d1 = (p1[0] - p0[0], p1[1] - p0[1])
                    d2 = (r1[0] - r0[0], r1[1] - r0[1])
                    if d1[0] * d2[1] - d1[1] * d2[0]:
                        continue                # not the same line
                    if d1[0] * d2[0] + d1[1] * d2[1] >= 0:
                        continue                # the same way round: not a join
                    mask |= 1 << e
        out.append(mask)
    return out


BURIED = buried()


def light(m, t, lite, piece, buried=0):
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
        vis.append(v < 0 and not (buried >> len(vis)) & 1)
        col.append((base + RAMP[sh + 128]) & 15)
    return vis, col


def depth(m, t, quad):
    """The view z of a piece's centre. Not what orders them - see below."""
    cx = sum(p[0] for p in quad) // 4
    cy = sum(p[1] for p in quad) // 4
    return s16(t[2] + m[6] * cx + m[7] * cy)


def pairs():
    """For every pair of pieces, a face plane of the first that has the
    second wholly on its outward side.

    The pieces are disjoint convex prisms of the same z extent, so the
    separating axis theorem promises one of the four side faces is a
    separating plane, and a separating plane settles the order exactly:
    whichever piece is on the eye's side of it is the nearer one, and
    that is the same N.T + off test the faces are culled with. A
    centroid depth settles nothing - it was wrong on 72 pairs in 44 of
    prismpre's 64 frames, and 344 in 178 of prism's 256.
    """
    out = []
    for i in range(len(PIECES)):
        for j in range(i + 1, len(PIECES)):
            for e in range(4):
                n, off = normals(PIECES[i][0])[e]
                if all(n[0] * x + n[1] * y >= off * 128
                       for x, y in PIECES[j][0]):
                    out.append((i, j, 6 * i + e))
                    break
            else:
                raise AssertionError("no plane separates %d and %d" % (i, j))
    return out


PAIRS = pairs()


def overlap(a, b):
    """Do two screen boxes (xmin, xmax, ymin, ymax) touch?"""
    return not (a[1] < b[0] or b[1] < a[0] or a[3] < b[2] or b[3] < a[2])


def order(m, t, box):
    """The pieces farthest first.

    Only pieces that overlap on screen constrain each other, so the
    sort is a topological one over those pairs. The relation can have
    a cycle once the boxes are taken for the shapes - three frames in
    prismpre's 64 - and then the piece in front of the fewest others
    goes first, which leaves exactly one pair the wrong way round
    instead of a cascade.
    """
    w = [v >> 8 for v in t]
    cv = [sum(s8(m[k * 3 + a] & 0xFF) * w[k] for k in range(3))
          for a in range(3)]
    n_ = len(PIECES)
    fr = [0] * n_                       # bit j: piece i is in front of j
    for i, j, fi in PAIRS:
        n, off = normals(PIECES[i][0])[fi % 6]
        v = sum((n[a] * cv[a]) >> 7 for a in range(3)) + 64 * off
        if v < 0:
            fr[j] |= 1 << i             # the eye is outward, so j is nearer
        else:
            fr[i] |= 1 << j
    ov = [0] * n_
    for i in range(n_):
        for j in range(n_):
            if i != j and overlap(box[i], box[j]):
                ov[i] |= 1 << j
    out, left = [], (1 << n_) - 1
    while left:
        best, count = None, 99
        for x in range(n_):
            if not (left >> x) & 1:
                continue
            c = bin(fr[x] & ov[x] & left).count("1")
            if c < count:
                best, count = x, c
        out.append(best)
        left &= ~(1 << best)
    return out


def boxes(pts):
    """Each piece's screen box, from its eight projected corners."""
    out = []
    for p in pts:
        xs = [q[0] for q in p]
        ys = [q[1] for q in p]
        out.append((min(xs), max(xs), min(ys), max(ys)))
    return out


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
        pts = [t3d(verts(q), self.m, self.p, recip) for q, _ in PIECES]
        ord_ = order(self.m, self.p, boxes(pts))
        drawn = []
        for i in ord_:
            quad, base = PIECES[i]
            vis, col = light(self.m, self.p, lite, PIECES[i], BURIED[i])
            for f, idx in enumerate(FACES):
                if vis[f]:
                    raster.fill_quad(buf, [pts[i][k] for k in idx], col[f])
                    drawn.append((i, f))
        return buf, ord_, drawn


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
