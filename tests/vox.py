#!/usr/bin/env python3
"""A model of vox.z80s - a Comanche-style heightmap, in Python.

One ray a screen column, stepped outwards in fixed increments, and a
column of the screen filled from the bottom up. The trick that makes it
cheap is the horizon buffer: a column only draws where the new sample
rises above everything already drawn in it, so every screen byte is
written exactly once and there is no overdraw at all. wolf3d, by
contrast, prefills the viewport and paints over 78% of it.

Four pixels a column, so a column is two bytes and the same
LD (HL),A / INC L / LD (HL),A / ADD HL,BC that wolf3d's wide scaler
uses - 14.5 T-states a byte, going upwards.
"""
W, H, STRIDE = 256, 192, 128
TOP, VH = 48, 96                # the viewport, 256 x 96
COLS = 64                       # rays, four pixels each
MAPW = 64                       # the map wraps every 64 cells
STEPS = 32                      # how far a ray is walked
STEP = 384                      # world units a step, one and a half cells
FOCAL = 221
HORIZON = TOP + 30              # so most of the viewport is ground
SKY = 0


def mapdata():
    """A heightmap with a few hills and a river, 0..255."""
    import math
    m = bytearray(MAPW * MAPW)
    for y in range(MAPW):
        for x in range(MAPW):
            h = (95 * math.sin(2 * math.pi * x / 21)
                 * math.sin(2 * math.pi * y / 16)
                 + 60 * math.sin(2 * math.pi * (x + y) / 11)
                 + 45 * math.sin(2 * math.pi * (x - 2 * y) / 27)
                 + 25 * math.sin(2 * math.pi * (3 * x + y) / 9))
            m[y * MAPW + x] = max(0, min(255, int(110 + h)))
    return m


def rowtab(camh):
    """Where a height lands on screen at each step out, 16 levels.

    A multiply and a divide per sample would be 300 T-states; sixteen
    height levels a step is a 512 byte table and one lookup. The eye
    does not miss the other four bits.
    """
    t = bytearray(STEPS * 16)
    for z in range(STEPS):
        for hq in range(16):
            h = hq * 16 + 8
            r = HORIZON - ((h - camh) * FOCAL) // ((z + 1) * STEP)
            t[z * 16 + hq] = max(TOP, min(TOP + VH, r))
    return t


def frame(mp, rt, px, py, dxs, dys, colour):
    """dxs, dys: the ray step for each column, 8.8 in map cells."""
    buf = bytearray(STRIDE * H)
    for c in range(COLS):
        x, y = px, py
        top = TOP + VH                          # nothing drawn yet
        for z in range(STEPS):
            x = (x + dxs[c]) & 0xFFFF
            y = (y + dys[c]) & 0xFFFF
            h = mp[((y >> 8) % MAPW) * MAPW + ((x >> 8) % MAPW)]
            r = rt[z * 16 + (h >> 4)]
            if r < top:
                col = colour[h >> 4]
                for row in range(r, top):
                    if TOP <= row < TOP + VH:
                        o = row * STRIDE + 2 * c
                        buf[o] = col
                        buf[o + 1] = col
                top = r
        for row in range(TOP, min(top, TOP + VH)):
            o = row * STRIDE + 2 * c
            buf[o] = SKY
            buf[o + 1] = SKY
    return buf
