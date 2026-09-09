#!/usr/bin/env python3
"""A model of wolf3d.z80s - the same arithmetic, in Python.

A grid maze cast one ray per screen column, Wolfenstein fashion, with
textured walls. Half horizontal resolution: 128 columns of two pixels,
so a column is exactly one byte of a MODE 4 line and a wall column is
written straight down the screen.
"""
import math

W, H, STRIDE = 256, 192, 128
TOPLINE = 24                    # first viewport scanline
VH = 144                        # 256 x 144, 16:9 with square pixels
HALFV = VH // 2                 # 72
COLS = 128                      # rays, one a column
TEX = 32                        # textures are TEX x TEX
HMAX = VH                       # a wall is never drawn taller than this

# The height ladder the scalers are built for: every second row while
# the wall is short, every eighth while it fills the screen, so the
# relative error stays near 6% at any distance rather than being
# negligible near and hopeless far.
LADDER = (list(range(2, 33, 2)) + list(range(36, 65, 4))
          + list(range(72, 145, 8)))


def rung(h):
    """The ladder index for a raw half height, and the height drawn."""
    want = 2 * h
    idx = 0
    for i, L in enumerate(LADDER):
        if L <= want:
            idx = i
    return idx, LADDER[idx]
FOCAL = 221                     # half width 128 px over tan(30 degrees)
HSCALE = FOCAL * 128            # h = HSCALE / perpendicular distance

SIN = [round(16384 * math.sin(2 * math.pi * i / 256)) for i in range(256)]
PLANE = [round(16384 * 0.5773502692 * math.sin(2 * math.pi * i / 256))
         for i in range(256)]


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v > 0x7FFF else v


def recip_tab():
    """w3d_recip: delta distance from |ray component| >> 7."""
    return [0xFFFF] + [min(0xFFFF, 32768 // i) for i in range(1, 256)]


def height_tab():
    """w3d_htab: wall half height from perpendicular distance >> 3."""
    t = [HMAX // 2]
    for i in range(1, 1024):
        h = (HSCALE // 2) // (i << 3)
        t.append(min(HMAX // 2, h))
    return t


RECIP = recip_tab()
HTAB = height_tab()


def cast(mp, px, py, rayx, rayy):
    """One ray. Returns (perpendicular distance, side, texture u, cell)."""
    mapx, mapy = px >> 8, py >> 8
    ddx = RECIP[min(255, abs(rayx) >> 7)]
    ddy = RECIP[min(255, abs(rayy) >> 7)]
    if rayx < 0:
        stepx, fx = -1, px & 255
    else:
        stepx, fx = 1, 256 - (px & 255)      # a full cell when on the line
    if rayy < 0:
        stepy, fy = -1, py & 255
    else:
        stepy, fy = 1, 256 - (py & 255)
    sdx = (fx * ddx) >> 8
    sdy = (fy * ddy) >> 8
    side = 0
    for _ in range(64):
        if sdx < sdy:
            sdx = (sdx + ddx) & 0xFFFF
            mapx += stepx
            side = 0
        else:
            sdy = (sdy + ddy) & 0xFFFF
            mapy += stepy
            side = 1
        if not (0 <= mapx < 16 and 0 <= mapy < 16):
            return None
        cell = mp[mapy * 16 + mapx]
        if cell:
            dist = (sdx - ddx) if side == 0 else (sdy - ddy)
            if dist < 1:
                dist = 1
            # Where along the wall it hit, for the texture column: the
            # hit point is pos + dist * ray / 16384. The exact product
            # wants 16 by 16; one signed 8 by 8 is close enough, because
            # u is only ever used five bits wide. dist >> 5 stays inside
            # a byte because no ray in a 16 by 16 map runs further than
            # the diagonal, and ray >> 8 is the high byte of the ray.
            if side == 0:
                u = (py + ((((dist >> 5) & 255) * (rayy >> 8)) >> 1)) & 255
                if stepx > 0:
                    u = 255 - u
            else:
                u = (px + ((((dist >> 5) & 255) * (rayx >> 8)) >> 1)) & 255
                if stepy < 0:
                    u = 255 - u
            return dist, side, (u * TEX) >> 8, cell
    return None


def frame(mp, px, py, ang):
    """Every column's (wall height, texture, texture column), or None."""
    dx, dy = SIN[(ang + 64) & 255], SIN[ang & 255]
    plx, ply = -PLANE[ang & 255], PLANE[(ang + 64) & 255]
    rx, ry = s16(dx - plx), s16(dy - ply)
    sx, sy = plx >> 6, ply >> 6
    out = []
    for _ in range(COLS):
        hit = cast(mp, px, py, rx, ry)
        if hit is None:
            out.append(None)
        else:
            dist, side, u, cell = hit
            h = HTAB[min(1023, dist >> 3)]
            if h < 1:
                h = 1
            out.append((h, cell, u, side))
        rx, ry = s16(rx + sx), s16(ry + sy)
    return out


def draw(cols, textures, ceil_col, floor_col, buf=None):
    """The columns into a MODE 4 buffer, one byte a column."""
    if buf is None:
        buf = bytearray(STRIDE * H)
    for y in range(VH):
        base = (TOPLINE + y) * STRIDE
        c = ceil_col if y < HALFV else floor_col
        for x in range(COLS):
            buf[base + x] = c
    for x, col in enumerate(cols):
        if col is None:
            continue
        h, cell, u, side = col
        _, n = rung(h)                  # the height a scaler exists for
        top = HALFV - n // 2
        tex = textures[cell - 1]
        for k in range(n):
            v = (k * TEX) // n
            b = tex[u * TEX + v]
            y = top + k
            if 0 <= y < VH:
                buf[(TOPLINE + y) * STRIDE + x] = b
    return buf
