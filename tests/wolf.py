#!/usr/bin/env python3
"""A model of wolf3d.z80s - the same arithmetic, in Python.

A grid maze cast one ray per screen column, Wolfenstein fashion, with
textured walls. Half horizontal resolution: two pixels a column, so a
column is exactly one byte of a MODE 4 line and a wall column is
written straight down the screen. set_view sizes the viewport; the
tables the Z80 reads are generated to match by tests/mkwolfdata.py.
"""
import math

W, H, STRIDE = 256, 192, 128     # the screen the viewport sits in
TEX = 32                        # textures are TEX x TEX
TAN30 = 0.5773502692            # the camera plane, a 60 degree view

SIN = [round(16384 * math.sin(2 * math.pi * i / 256)) for i in range(256)]
PLANE = [round(16384 * TAN30 * math.sin(2 * math.pi * i / 256))
         for i in range(256)]


def step_tab():
    """PSTEP: the camera plane divided by half the ray count.

    The sweep is built out of this rather than the plane itself, so it
    stays centred and the full 60 degrees wide whatever the ray count
    is. Dividing the plane by a shift only works when half the count is
    a power of two, which 128 rays is and 96 is not.
    """
    return [round(p / (COLS // 2)) for p in PLANE]


def ladder(vh):
    """The height ladder the scalers are built for.

    Every second row while the wall is short, every eighth while it
    fills the screen, so the relative error stays near 6% at any
    distance rather than being negligible near and hopeless far.
    """
    return ([h for h in range(2, 33, 2) if h <= vh]
            + [h for h in range(36, 65, 4) if h <= vh]
            + [h for h in range(72, vh + 1, 8)])


def set_view(width=256, height=144, bpc=1):
    """Size the viewport: width pixels by height rows, centred.

    bpc is bytes a column: 1 for two-pixel columns, 2 for four. The
    focal length follows the width, which keeps the 60 degree view the
    camera plane gives and lets the vertical field narrow with the
    window, the way shrinking a window in Wolfenstein did.
    """
    global VW, VH, HALFV, COLS, BPC, BYTES, TOPLINE, XOFF
    global FOCAL, HSCALE, HMAX, LADDER, HTAB, PSTEP
    VW, VH = width, height
    HALFV = VH // 2
    BPC = bpc                   # bytes, so pixels over two, a column
    COLS = VW // (2 * bpc)
    BYTES = COLS * bpc          # what a viewport row is, in bytes
    TOPLINE = (H - VH) // 2
    XOFF = (W - VW) // 4
    FOCAL = int((VW // 2) / TAN30)
    HSCALE = FOCAL * 128        # h = HSCALE / perpendicular distance
    HMAX = VH                   # a wall is never drawn taller than this
    LADDER = ladder(VH)
    HTAB = height_tab()
    PSTEP = step_tab()


def rung(h):
    """The ladder index for a raw half height, and the height drawn."""
    want = 2 * h
    idx = 0
    for i, L in enumerate(LADDER):
        if L <= want:
            idx = i
    return idx, LADDER[idx]


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
set_view()


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
    sx, sy = -PSTEP[ang & 255], PSTEP[(ang + 64) & 255]
    half = COLS // 2                    # so the sweep is centred on dir
    rx, ry = s16(dx - half * sx), s16(dy - half * sy)
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
        base = (TOPLINE + y) * STRIDE + XOFF
        c = ceil_col if y < HALFV else floor_col
        for x in range(BYTES):
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
                o = (TOPLINE + y) * STRIDE + XOFF + x * BPC
                for i in range(BPC):
                    buf[o + i] = b
    return buf
