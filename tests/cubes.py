#!/usr/bin/env python3
"""A model of cubes.z80s - several lit cubes bouncing in a drawn room.

democube.z80s moves one cube around a box and renderlit.z80s draws it.
This does the same for four of them, with gravity, with the cubes
bouncing off each other as well as off the walls, and with the room
they are in drawn as a wire frame so that the box is something you can
see rather than something you have to believe.

The physics is integers and no multiplication anywhere:

    v.y -= G                        gravity, one add
    p   += (v + f) >> 4             democube's step, remainder kept
    wall:  v = -v                   if it is heading into the wall
    cube:  swap the two v's         along the axis of least overlap

Elastic throughout, so it runs for ever without either dying down or
running away; tests/test_cubes.py checks that over a million frames.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import raster
import rasterlit
from test_democube import Model, SIN, asr, s16

W, H, STRIDE = raster.W, raster.H, raster.STRIDE
FOCAL = 64                              # what t3d_recip is built for

N = 4                                   # cubes
S = 34                                  # a cube's half size
R = 59                                  # and its bounding sphere, ceil(S*3^.5)
BX, BY, ZN, ZF = 187, 140, 100, 254     # the room, in world units

# The far wall is where it is because of sixteen bits, not because of
# taste: t3d adds up to R*128 of rotated corner onto the centre, and
# the sum has to stay inside a signed word. That is 195 units of z at
# this size, and the room's other three dimensions follow from the
# viewport its front face has to fill.
G = 6                                   # gravity, velocity units a frame

XLIM, YLIM = (BX - R) * 128, (BY - R) * 128
ZMIN, ZMAX = (ZN + R) * 128, (ZF - R) * 128
VERTS = [(x, y, z) for x in (S, -S) for y in (S, -S) for z in (S, -S)]

ROOM = 7                                # the wire frame's colour
BASE = [[0] * 6, [8] * 6, [0, 0, 8, 8, 0, 8], [8, 8, 0, 0, 8, 0]]


def project(x, y, z):
    """A room corner to screen, the same arithmetic t3d does on vertices."""
    return 128 + (x * FOCAL) // z, 96 - (y * FOCAL) // z


def edges():
    """The room, as screen coordinates.

    Its front face is the viewport, and everything outside that is
    painted once and never touched again - the cubes cannot reach it,
    because the room's own walls keep them off it. The other eight
    edges are drawn every frame, because a cube goes in front of them
    and the erase takes them with it when it goes.
    """
    c = [project(x, y, z)
         for z in (ZN, ZF) for y in (BY, -BY) for x in (-BX, BX)]
    back = [(4, 5), (5, 7), (7, 6), (6, 4)]
    side = [(0, 4), (1, 5), (2, 6), (3, 7)]
    inner = []
    for a, b in back + side:      # major axis increasing, which is what
        p0, p1 = c[a], c[b]       # lets cb_line walk the address rather
        if abs(p1[0] - p0[0]) >= abs(p1[1] - p0[1]):
            if p1[0] < p0[0]:     # than work it out per pixel
                a, b = b, a
        elif p1[1] < p0[1]:
            a, b = b, a
        inner.append((a, b))
    return c, (c[0], c[3]), inner


def border(buf, colour=ROOM):
    """The room's front face, as the frame around the viewport."""
    (x0, y0), (x1, y1) = edges()[1]
    for y in range(H):
        for x in range(W):
            if x <= x0 or x >= x1 or y <= y0 or y >= y1:
                plot(buf, x, y, colour)


def plot(buf, x, y, colour):
    if 0 <= x < W and 0 <= y < H:
        i = y * STRIDE + (x >> 1)
        if x & 1:
            buf[i] = (buf[i] & 0xF0) | colour
        else:
            buf[i] = (buf[i] & 0x0F) | (colour << 4)


def line(buf, p0, p1, colour):
    """Bresenham on the major axis, which is what cb_line does."""
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x1 >= x0 else -1
    sy = 1 if y1 >= y0 else -1
    if dx >= dy:
        err, y = dx >> 1, y0
        for i in range(dx + 1):
            plot(buf, x0 + i * sx, y, colour)
            err -= dy
            if err < 0:
                err += dx
                y += sy
    else:
        err, x = dy >> 1, x0
        for i in range(dy + 1):
            plot(buf, x, y0 + i * sy, colour)
            err -= dx
            if err < 0:
                err += dy
                x += sx


class Cube(Model):
    """democube's cube, with gravity and a room it shares."""

    def __init__(self, p, v, a, da):
        Model.__init__(self)
        self.p, self.v, self.a, self.da = list(p), list(v), list(a), list(da)
        self.f = [0, 0, 0]

    def move(self):
        self.v[1] = s16(self.v[1] - G)
        for i in range(3):
            acc = s16(self.v[i] + self.f[i])
            self.f[i] = acc & 15
            self.p[i] = s16(self.p[i] + asr(acc, 4))
        for i, lo, hi in ((0, -XLIM, XLIM), (1, -YLIM, YLIM),
                          (2, ZMIN, ZMAX)):
            if self.p[i] >= hi:
                self.p[i] = hi              # the wall turns it round, and
                if self.v[i] >= 0:          # holds it: a cube squeezed
                    self.v[i] = -self.v[i]  # between a wall and another
            elif self.p[i] < lo:            # cube would burrow out of the
                self.p[i] = lo              # room otherwise, a step a
                if self.v[i] < 0:           # frame, for as long as the
                    self.v[i] = -self.v[i]  # squeeze lasts


def collide(a, b):
    """Two cubes that overlap swap velocities along one axis.

    The axis is whichever they overlap least in, which for equal boxes
    is the one they met on, and swapping is what equal masses do in a
    head on hit. No multiplication, and no energy either made or lost.

    The test is on the cubes' unrotated extent, 2S, not on their
    bounding spheres: four spheres of radius R do not fit in this room
    with any freedom, and a corner that dips into a neighbour for a
    frame is not what anybody is looking at.
    """
    d = [s16(a.p[i] - b.p[i]) for i in range(3)]
    over = [2 * S * 128 - abs(d[i]) for i in range(3)]
    if min(over) <= 0:
        return False
    i = over.index(min(over))
    if (d[i] > 0 and a.v[i] - b.v[i] >= 0) or (d[i] < 0 and a.v[i] - b.v[i] <= 0):
        return False                    # already parting
    a.v[i], b.v[i] = b.v[i], a.v[i]
    return True


def cubes_start():
    """Where the cubes begin: position, velocity, angles, spin rates."""
    return [
        ((-90 * 128, 60 * 128, 165 * 128), (620, 0, 300), (0, 0, 0),
         (3, 5, 2)),
        ((90 * 128, 40 * 128, 190 * 128), (-500, 200, -260),
         (40, 90, 7), (-4, 3, 5)),
        ((0, -30 * 128, 176 * 128), (430, 700, 420), (128, 20, 200),
         (5, -2, 4)),
        ((40 * 128, 70 * 128, 186 * 128), (-350, -150, -500),
         (200, 160, 60), (2, 6, -3)),
    ][:N]


class Scene:
    def __init__(self):
        self.cubes = [Cube(*c) for c in cubes_start()]

    def step(self):
        for c in self.cubes:
            c.spin()
            c.move()
        for i in range(N):
            for j in range(i + 1, N):
                collide(self.cubes[i], self.cubes[j])

    def draw(self, recip, lite, buf=None):
        """The room and the cubes, farthest cube first."""
        from test_transform3d import model as t3d
        if buf is None:
            buf = bytearray(STRIDE * H)
        c, _, inner = edges()
        border(buf)
        for a, b in inner:
            line(buf, c[a], c[b], ROOM)
        order = sorted(range(N), key=lambda i: -self.cubes[i].p[2])
        pts = {}
        for i in order:
            cu = self.cubes[i]
            pts[i] = t3d(VERTS, cu.m, cu.p, recip)
            vis, col = rasterlit.light(cu.m, cu.p, lite, BASE[i % len(BASE)])
            for f, idx in enumerate(raster.FACES):
                if vis[f]:
                    raster.fill_quad(buf, [pts[i][k] for k in idx], col[f])
        return buf, order, pts


def main():
    """The thing this claims: it runs for ever and stays in the room."""
    n = 1000000 if "--long" in sys.argv else 20000
    sc = Scene()
    worst = 0
    hits = 0
    for f in range(n):
        sc.step()
        for c in sc.cubes:
            for i, lim in ((0, XLIM), (1, YLIM)):
                worst = max(worst, abs(c.p[i]) - lim)
            worst = max(worst, c.p[2] - ZMAX, ZMIN - c.p[2])
            for i in range(3):
                hits = max(hits, abs(c.v[i]))
    print("  %d frames: furthest past a wall %d, fastest %d of 6000"
          % (n, max(0, worst), hits))
    ok = worst <= 0 and hits < 6000
    print("%s" % ("PASSED: the cubes stay in the room and keep bouncing"
                  if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
