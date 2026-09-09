#!/usr/bin/env python3
"""A model of room3d.z80s - the same arithmetic, in Python.

The renderer draws a convex room from inside it: walls as screen-space
trapezoids rather than a ray per column, because a Z80 can only fill a
frame buffer at a sensible rate along rows, and one ray per column
fills it along columns.
"""
import math

# the letterboxed viewport
W, H, STRIDE = 256, 192, 128
TOPLINE = 24                    # first viewport scanline
VH = 144                        # 256 x 144 is 16:9
HALFV = VH // 2                 # 72
NEAR = 32                       # near plane, world units
FOCAL = 128                     # 90 degree horizontal field of view
EYEH = 64                       # eye at half the wall height
HSCALE = EYEH * FOCAL           # h = HSCALE / vz

SIN = [max(-127, min(127, round(127 * math.sin(2 * math.pi * i / 256))))
       for i in range(256)]


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v > 0x7FFF else v


def mul7(d, c):
    """(d * c) >> 7, exactly as r3d_mul7 computes it."""
    return (d * c) >> 7                 # Python >> on ints is arithmetic


def idiv(a, b):
    """Truncating division, which is what a sign-magnitude divider does."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def transform(verts, cam):
    """World vertices into view space: +z ahead, +x right."""
    cx, cz, ca = cam
    sa, co = SIN[ca & 255], SIN[(ca + 64) & 255]
    out = []
    for x, z in verts:
        dx, dz = s16(x - cx), s16(z - cz)
        out.append((mul7(dx, co) - mul7(dz, sa),
                    mul7(dx, sa) + mul7(dz, co)))
    return out


def clip(p0, p1, d0, d1):
    """Move whichever end is outside onto the plane d = 0."""
    if d0 >= 0 and d1 >= 0:
        return p0, p1
    if d0 < 0 and d1 < 0:
        return None, None
    if d0 < 0:                          # r3d_clip0: a 16-bit fraction of
        t = ((-d0) << 16) // (d1 - d0)  # the way along, then a multiply
        p0 = (p0[0] + (((p1[0] - p0[0]) * t) >> 16),
              p0[1] + (((p1[1] - p0[1]) * t) >> 16))
    else:
        t = ((-d1) << 16) // (d0 - d1)
        p1 = (p1[0] + (((p0[0] - p1[0]) * t) >> 16),
              p1[1] + (((p0[1] - p1[1]) * t) >> 16))
    return p0, p1


def clip_wall(p0, p1):
    """Against the near plane only; the screen edges are handled after
    projection, by interpolating h."""
    p0, p1 = clip(p0, p1, p0[1] - NEAR, p1[1] - NEAR)
    return None if p0 is None else (p0, p1)


def project(p):
    """View space to a screen x - left unclamped - and a half height."""
    vx, vz = p
    if vz < NEAR:
        vz = NEAR
    h = min(255, idiv(HSCALE, vz))
    return 128 + idiv(vx << 7, vz), h


def snap(sx):
    """Screen x to an even byte column - four pixels, so that every run
    the stack filler writes is a whole number of pairs."""
    return ((sx + 2) >> 2) << 1


def shade(hl, hr, base, levels=6):
    lv = (hl + hr) >> 6
    if lv > levels - 1:
        lv = levels - 1
    return (base + lv) & 15


def strip_rows(n, hl, hr):
    """The split column for each j = 71 .. 0, as r3d_strip walks it.

    c is how many columns of the run the wall covers at height level j,
    taken from whichever end is nearer. Returns 72 counts.
    """
    hmax = max(hl, hr)
    d = abs(hl - hr) or 1
    inc = min(0xFFFF, (n << 8) // d)
    k = hmax - (HALFV - 1)
    out = []
    if k <= 0:
        out = [0] * (HALFV - hmax)
        acc = inc
    elif k >= d:
        acc = 0xFFFF
    else:
        acc = k * inc
    while len(out) < HALFV:
        out.append(min(acc >> 8, n))
        acc = min(0xFFFF, acc + inc)
    return out


def fill(buf, base, bl, br, nr, rc, nl, lc):
    """One row of a strip: nr bytes of rc at the right, nl of lc left."""
    i = base + br + 1
    for _ in range(nr):
        i -= 1
        buf[i] = rc
    for _ in range(nl):
        i -= 1
        buf[i] = lc
    assert i == base + bl


def draw_strip(buf, bl, br, hl, hr, wc, cc, fc):
    n = br - bl + 1
    left_heavy = hl > hr
    for j, c in zip(range(HALFV - 1, -1, -1), strip_rows(n, hl, hr)):
        for y, bg in ((HALFV - 1 - j, cc), (HALFV + j, fc)):
            base = (TOPLINE + y) * STRIDE
            if left_heavy:
                fill(buf, base, bl, br, n - c, bg, c, wc)
            else:
                fill(buf, base, bl, br, c, wc, n - c, bg)


def dup(c):
    return ((c << 4) | c) & 0xFF


def render(verts, colours, cam, ceil_col=14, floor_col=7, buf=None):
    """One frame. Returns the buffer and the strips it drew."""
    if buf is None:
        buf = bytearray(STRIDE * H)
    view = transform(verts, cam)
    strips = []
    n = len(verts)
    for i in range(n):
        seg = clip_wall(view[i], view[(i + 1) % n])
        if seg is None:
            continue
        sx0, h0 = project(seg[0])
        sx1, h1 = project(seg[1])
        if sx1 <= 0 or sx0 >= 256 or sx1 <= sx0:
            continue
        d = sx1 - sx0
        if sx0 < 0:                     # clamp onto the screen, h being
            t = ((0 - sx0) << 16) // d  # affine in screen x
            h0 = (h0 + (((h1 - h0) * t) >> 16)) & 0xFF
            sx0 = 0
        if sx1 > 256:
            t = ((sx1 - 256) << 16) // d
            h1 = (h1 + (((h0 - h1) * t) >> 16)) & 0xFF
            sx1 = 256
        bl, br = snap(sx0), snap(sx1) - 1
        if br < bl:
            continue
        col = dup(shade(h0, h1, colours[i]))
        draw_strip(buf, bl, br, h0, h1, col, dup(ceil_col), dup(floor_col))
        strips.append((i, bl, br, h0, h1, col))
    return buf, strips
