#!/usr/bin/env python3
"""A model of renderlit.z80s: the same rasteriser, lit and culled from
the rotation matrix's columns rather than from the projected quad."""
import raster
from raster import FACES, fill_quad, STRIDE, H, W, to_png

LEVELS = 8                              # RNDL_LEVELS
AMBIENT = 2                             # RNDL_AMBIENT
S = 40                                  # RNDL_S
CULL = 64 * S                           # RNDL_CULL


def s8(v):
    return v - 256 if v > 127 else v


def ramp():
    """rndl_init's table: shade + 128 -> level."""
    t = [AMBIENT] * 256
    for i in range(128, 256):
        t[i] = min(LEVELS - 1,
                   AMBIENT + (((i - 128) * (LEVELS - AMBIENT)) >> 7))
    return t


RAMP = ramp()


def shift7(x):
    """rndl_light's saturating >> 7 into a signed byte."""
    if x > 16383:
        return 127
    if x < -16384:
        return -128
    return x >> 7


def light(m, t, lite, base):
    """Visibility and lit colour for all six faces.

    m    the nine matrix bytes, signed, row order
    t    the translation, three signed 16-bit values, 9.7
    lite the light direction in view space, three signed bytes
    """
    w = [v >> 8 for v in t]             # the high byte of each component
    cv = [sum(s8(m[k * 3 + a] & 0xFF) * w[k] for k in range(3))
          for a in range(3)]
    lv = [sum(s8(m[k * 3 + a] & 0xFF) * lite[k] for k in range(3))
          for a in range(3)]
    vis, col = [], []
    for a in range(3):
        sh = shift7(lv[a])
        for sign in (0, 1):
            if sign == 0:
                v = cv[a] + CULL < 0    # N.T + S < 0
                d = sh
            else:
                v = cv[a] - CULL > 0    # the opposite normal
                d = 127 if sh == -128 else -sh
            f = 2 * a + sign
            vis.append(v)
            col.append((base[f] + RAMP[d + 128]) & 15)
    return vis, col


def render(screen_pts, m, t, lite, base):
    buf = bytearray(STRIDE * H)
    vis, col = light(m, t, lite, base)
    drawn = []
    for f, idx in enumerate(FACES):
        if not vis[f]:
            continue
        fill_quad(buf, [screen_pts[i] for i in idx], col[f])
        drawn.append(f)
    return buf, drawn, col
