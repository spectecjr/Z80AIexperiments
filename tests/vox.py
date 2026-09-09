#!/usr/bin/env python3
"""A model of vox.z80s - a Comanche-style heightmap, in Python.

One ray a screen column, stepped outwards in fixed increments, and the
column filled from the bottom upwards. The horizon buffer is what makes
it cheap: a column only draws where a sample rises above everything
already drawn in it, so every screen byte is written exactly once and
there is no overdraw at all. wolf3d, by contrast, prefills the viewport
and paints over 78% of what it wrote.

Everything about the layout is chosen to make one sample cheap:

  - the map is 16 by 16 and page aligned, so a cell's address is one
    byte - roto.z80s's texel trick;
  - y is 4.12, so its row is already in the top nibble of its high
    byte and needs no shifting - also roto's;
  - sixteen height levels and sixteen steps out, so the tables that
    turn a height into a screen row and a colour are indexed by
    (h & 0xF0) | z, with no shifting at all, and both are one page.

The colour table is indexed by the step as well as the height, so the
distance fade costs nothing.
"""
W, H, STRIDE = 256, 192, 128
TOP, VH = 64, 64                # the viewport: 256 x 64
COLS = 64                       # rays, four pixels each
MAPW = 16                       # and the map wraps every 16 cells
STEPS = 16
STEP = 256                      # world units a step: one cell, so the
                                # sixteen of them cross the map exactly once
FOCAL = 221
VSCALE = 420                    # vertical exaggeration: relief reads
                                # better than it measures, at this size
HORIZON = TOP + 20              # so most of the viewport is ground
SKY = 0x11


def mapdata():
    """A heightmap that tiles seamlessly every 16 cells."""
    import math
    m = bytearray(MAPW * MAPW)
    for y in range(MAPW):
        for x in range(MAPW):
            h = (78 * math.sin(2 * math.pi * x / 16)
                 * math.sin(2 * math.pi * y / 16)
                 + 55 * math.sin(2 * math.pi * (x + y) / 8)
                 + 38 * math.sin(2 * math.pi * (x - 2 * y) / 16)
                 + 26 * math.sin(2 * math.pi * (3 * x + y) / 8)
                 + 15 * math.sin(2 * math.pi * (x + 3 * y) / 4))
            m[y * MAPW + x] = max(0, min(255, int(118 + h)))
    return m


def rowtab(camh):
    """Where a height lands on screen, by level and step: (h & 0xF0) | z.

    A multiply and a divide a sample would be 300 T-states; sixteen
    levels and sixteen steps is one page and one lookup.
    """
    t = bytearray(256)
    for hq in range(16):
        for z in range(STEPS):
            h = hq * 16 + 8
            r = HORIZON - ((h - camh) * VSCALE) // ((z + 1) * STEP)
            # the step counts down on the Z80, so that its loop test is
            # one instruction - so the tables are laid out that way
            t[hq * 16 + (STEPS - 1 - z)] = max(TOP, min(TOP + VH, r))
    return t


def coltab():
    """The colour of a level at a step: the fade with distance is free."""
    t = bytearray(256)
    for hq in range(16):
        for z in range(STEPS):
            c = 2 + (hq * 13) // 15                 # 2..15 by height
            c = max(2, c - (z * 3) // STEPS)        # and darker with it
            t[hq * 16 + (STEPS - 1 - z)] = (c << 4) | c
    return t


def frame(mp, rt, ct, px, py, dxs, dys):
    """px is 8.8 in cells, py is 4.12. dxs, dys step one column's ray."""
    buf = bytearray(b"\x00" * (STRIDE * H))
    for c in range(COLS):
        x, y = px, py
        top = TOP + VH                              # nothing drawn yet
        for z in range(STEPS):
            x = (x + dxs[c]) & 0xFFFF
            y = (y + dys[c]) & 0xFFFF
            i = ((y >> 8) & 0xF0) | ((x >> 8) & 0x0F)
            h = mp[i]
            j = (h & 0xF0) | (STEPS - 1 - z)
            r = rt[j]
            if r < top:
                col = ct[j]
                for row in range(r, top):
                    o = row * STRIDE + 2 * c
                    buf[o] = col
                    buf[o + 1] = col
                top = r
        for row in range(TOP, top):
            o = row * STRIDE + 2 * c
            buf[o] = SKY
            buf[o + 1] = SKY
    return buf
