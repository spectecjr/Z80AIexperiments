#!/usr/bin/env python3
"""A model of portal.z80s - a maze of convex rooms, seen through doors.

room3d.z80s draws one convex room: its walls tile the view exactly, so
there is no sorting, no overdraw and no depth buffer. A maze is not
convex, but a maze cut into convex sectors is - each sector's walls
still tile the part of the view you can see it through, and that part
is a range of screen columns.

So the renderer is room3d's, driven recursively: draw the sector the
camera is in with the window 0..256; where a wall is a door rather than
a wall, draw the sector behind it with the window narrowed to the door.
Every pixel is still written exactly once, and the only thing that has
been added to a wall is which two columns it lives between.

A door seen from the far side is wound backwards, which room3d's
"sx1 <= sx0" test already throws out, so the recursion never turns
round and walks back through the door it came in by. Depth is capped
all the same, because a ring of rooms can see itself.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import room as R

W, H, STRIDE = R.W, R.H, R.STRIDE
MAXDEPTH = 6

# The maze: a three by three grid of convex cells, wound clockwise in
# (x, z) as room3d's room is, each wall carrying the cell behind it or
# None if it is solid. The open edges make a ring of eight cells with a
# room in the middle off the north one - so there is a loop to see
# round and a dead end to walk into.
XS = [-512, -128, 128, 512]
ZS = [-512, -128, 128, 512]
VERTS = [(x, z) for z in ZS for x in XS]

OPEN = {((0, 0), (1, 0)), ((1, 0), (2, 0)), ((2, 0), (2, 1)),
        ((2, 1), (2, 2)), ((1, 2), (2, 2)), ((0, 2), (1, 2)),
        ((0, 1), (0, 2)), ((0, 0), (0, 1)), ((1, 0), (1, 1))}


def cells():
    """Every cell's four walls: (v0, v1, colour base, behind)."""
    def sect(c, r):
        return r * 3 + c

    def opened(a, b):
        return (a, b) in OPEN or (b, a) in OPEN

    out = []
    for r in range(3):
        for c in range(3):
            a, b = r * 4 + c, r * 4 + c + 1
            d, e = (r + 1) * 4 + c, (r + 1) * 4 + c + 1
            walls = []
            for v0, v1, nc, nr, col in ((a, d, c - 1, r, 1),
                                        (d, e, c, r + 1, 8),
                                        (e, b, c + 1, r, 1),
                                        (b, a, c, r - 1, 8)):
                on = (0 <= nc < 3 and 0 <= nr < 3
                      and opened((c, r), (nc, nr)))
                walls.append((v0, v1, col, sect(nc, nr) if on else None))
            out.append(walls)
    return out


SECTORS = cells()


def span(view, w):
    """A wall's screen span and end heights, or None if it is not on."""
    seg = R.clip_wall(view[w[0]], view[w[1]])
    if seg is None:
        return None
    sx0, h0 = R.project(seg[0])
    sx1, h1 = R.project(seg[1])
    if sx1 <= sx0:                      # wound away from the camera, which
        return None                     # is how a door stops us going back
    return sx0, sx1, h0, h1


def window(sx0, sx1, h0, h1, wl, wr):
    """Clamp a wall to the window, h being affine in screen x."""
    if sx1 <= wl or sx0 >= wr:
        return None
    d = sx1 - sx0
    if sx0 < wl:
        t = ((wl - sx0) << 16) // d
        h0 = (h0 + (((h1 - h0) * t) >> 16)) & 0xFF
        sx0 = wl
    if sx1 > wr:
        t = ((sx1 - wr) << 16) // d
        h1 = (h1 + (((h0 - h1) * t) >> 16)) & 0xFF
        sx1 = wr
    return sx0, sx1, h0, h1


def render(cam, ceil_col=14, floor_col=7, buf=None, sector=None):
    """One frame, and the strips it drew."""
    if buf is None:
        buf = bytearray(STRIDE * H)
    view = R.transform(VERTS, cam)
    strips = []
    todo = [(sector if sector is not None else locate(cam), 0, 256, 0)]
    while todo:
        s, wl, wr, depth = todo.pop(0)
        for w in SECTORS[s]:
            sp = span(view, w)
            if sp is None:
                continue
            sp = window(*sp, wl, wr)
            if sp is None:
                continue
            sx0, sx1, h0, h1 = sp
            if w[3] is not None:
                if depth < MAXDEPTH:
                    todo.append((w[3], R.snap(sx0) * 2, R.snap(sx1) * 2,
                                 depth + 1))
                continue
            bl, br = R.snap(sx0), R.snap(sx1) - 1
            if br < bl:
                continue
            col = R.dup(R.shade(h0, h1, w[2]))
            R.draw_strip(buf, bl, br, h0, h1, col, R.dup(ceil_col),
                         R.dup(floor_col))
            strips.append((bl, br, h0, h1, col))
    return buf, strips


def locate(cam):
    """Which sector the camera is in - the maze is a three by three grid."""
    cx, cz = cam[0], cam[1]
    col = 0 if cx < XS[1] else (1 if cx < XS[2] else 2)
    row = 0 if cz < ZS[1] else (1 if cz < ZS[2] else 2)
    return row * 3 + col


def coverage(buf):
    """How many viewport bytes were never written - should be none."""
    n = 0
    for y in range(R.TOPLINE, R.TOPLINE + R.VH):
        row = buf[y * STRIDE:(y + 1) * STRIDE]
        n += sum(1 for b in row if b == 0)
    return n


def sector_for(cam, band=48):
    """The sector to start drawing from.

    The cell the camera is in - unless it is standing within the near
    plane of an open edge, in which case the cell on the side it is
    facing. A door that close covers more than the whole viewport, so
    the cell in front tiles the view on its own; the cell behind does
    not, because what is behind the camera is exactly the part of that
    cell the door no longer shows. Standing on a door plane is the one
    place this renderer cannot draw from either side, and handing over
    a near plane early is how a walker gets past it.
    """
    cx, cz = cam[0], cam[1]
    fx, fz = R.SIN[cam[2] & 255], R.SIN[(cam[2] + 64) & 255]
    col = 0 if cx < XS[1] else (1 if cx < XS[2] else 2)
    row = 0 if cz < ZS[1] else (1 if cz < ZS[2] else 2)
    for i in (1, 2):
        if abs(cx - XS[i]) < band and fx:
            nc = i if fx > 0 else i - 1
            if nc != col and (((col, row), (nc, row)) in OPEN
                              or ((nc, row), (col, row)) in OPEN):
                return row * 3 + nc
        if abs(cz - ZS[i]) < band and fz:
            nr = i if fz > 0 else i - 1
            if nr != row and (((col, row), (col, nr)) in OPEN
                              or ((col, nr), (col, row)) in OPEN):
                return nr * 3 + col
    return row * 3 + col


def clear(cam):
    """Is the camera far enough from its cell's walls to be drawable?

    room3d clips at NEAR and nothing checks; standing inside the near
    plane of a wall is outside what either renderer promises.
    """
    cx, cz = cam[0], cam[1]
    col = 0 if cx < XS[1] else (1 if cx < XS[2] else 2)
    row = 0 if cz < ZS[1] else (1 if cz < ZS[2] else 2)
    m = R.NEAR + 16
    return (cx - XS[col] > m and XS[col + 1] - cx > m
            and cz - ZS[row] > m and ZS[row + 1] - cz > m)


def main():
    bad = 0
    for cz in range(-400, 401, 40):
        for cx in range(-400, 401, 40):
            if not clear((cx, cz, 0)):
                continue
            for ca in range(0, 256, 16):
                buf = bytearray(b"\x00" * (STRIDE * H))
                buf, strips = render((cx, cz, ca), buf=buf)
                gap = coverage(buf)
                if gap:
                    print("(%d,%d) angle %d: %d unwritten bytes, %d strips"
                          % (cx, cz, ca, gap, len(strips)))
                    bad += 1
    print("%s" % ("PASSED: the maze tiles the view from everywhere"
                  if not bad else "FAILURES: %d" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
