#!/usr/bin/env python3
"""
bbverify.py - reference model for the level, the autotiler and the wind
current, so the Z80 in bubble/ can be checked against something readable.

It reimplements, in Python, exactly what bb_level.z80s, bb_flow.z80s and
bb_bubble.z80s do, then:

  * prints each level's platform bitmap and its wind field as arrows
  * releases a bubble and traces it, confirming that it actually circulates
    rather than sticking in a corner or oscillating
  * reports how many cells the trace visits, which is the thing that makes
    a Bubble Bobble level feel alive

Run: python3 bubble/tools/bbverify.py [--trace]
"""

import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from bbgfx import make_levels, pack_level, MAP_W, MAP_H            # noqa: E402

DIR_U, DIR_UR, DIR_R, DIR_DR, DIR_D, DIR_DL, DIR_L, DIR_UL, DIR_NONE = range(9)
ARROW = "^/>\\v/<\\ ".replace("/", "/")
ARROW = ["^", "/", ">", "\\", "v", "/", "<", "\\", " "]
DX = [0, 1, 1, 1, 0, -1, -1, -1, 0]
DY = [-1, -1, 0, 1, 1, 1, 0, -1, 0]

BUB_ACCEL, BUB_VMAX, BUB_RISE = 12, 192, 24
CELL = 8


def unpack(packed):
    g = [[0] * MAP_W for _ in range(MAP_H)]
    for y in range(MAP_H):
        for byte in range(MAP_W // 8):
            v = packed[y * 4 + byte]
            for bit in range(8):
                g[y][byte * 8 + bit] = 1 if v & (0x80 >> bit) else 0
    return g


def solid(g, cx, cy):
    """Outside the map reads as solid, matching bb_cell_solid."""
    if not (0 <= cx < MAP_W and 0 <= cy < MAP_H):
        return 1
    return g[cy][cx]


def build_flow(g, sense=0):
    """The rule set from bb_flow.z80s, first match wins."""
    f = [[DIR_NONE] * MAP_W for _ in range(MAP_H)]
    for cy in range(MAP_H):
        for cx in range(MAP_W):
            if solid(g, cx, cy):
                continue
            u = solid(g, cx, cy - 1)
            r = solid(g, cx + 1, cy)
            d = solid(g, cx, cy + 1)
            l = solid(g, cx - 1, cy)
            if u and not r:
                v = DIR_R
            elif r and not d:
                v = DIR_D
            elif d and not l:
                v = DIR_L
            else:
                v = DIR_U
            if sense:
                v = (v + 4) & 7
            f[cy][cx] = v
    return f


def clamp(v, limit):
    return max(-limit, min(limit, v))


def trace_bubble(g, f, x0, y0, frames=1200):
    """The integrator from bb_bubble.z80s: 8.8 fixed point, per-axis
    collision, buoyancy on top of the wind term."""
    x, y = x0 << 8, y0 << 8
    vx = vy = 0
    visited, path = set(), []
    for _ in range(frames):
        cx, cy = ((x >> 8) + 8) >> 3, ((y >> 8) + 8) >> 3
        cx, cy = max(0, min(MAP_W - 1, cx)), max(0, min(MAP_H - 1, cy))
        d = f[cy][cx]
        vx = clamp(vx + DX[d] * BUB_ACCEL, BUB_VMAX)
        vy = clamp(vy + DY[d] * BUB_ACCEL - BUB_RISE, BUB_VMAX)

        nx = x + vx
        if solid(g, ((nx >> 8) + 8) >> 3, ((y >> 8) + 8) >> 3):
            vx = 0
        else:
            x = nx
        ny = y + vy
        if solid(g, ((x >> 8) + 8) >> 3, ((ny >> 8) + 8) >> 3):
            vy = 0
        else:
            y = ny

        c = (((x >> 8) + 8) >> 3, ((y >> 8) + 8) >> 3)
        visited.add(c)
        path.append(c)
    return visited, path


def show(g, f, path=None):
    marks = set(path or [])
    for cy in range(MAP_H):
        row = ""
        for cx in range(MAP_W):
            if g[cy][cx]:
                row += "#"
            elif (cx, cy) in marks:
                row += "o"
            else:
                row += ARROW[f[cy][cx]]
        print("   " + row)


def main():
    show_trace = "--trace" in sys.argv
    ok = True
    for n, grid in enumerate(make_levels()):
        g = unpack(pack_level(grid))            # round-trip the real packing
        f = build_flow(g)
        open_cells = sum(1 for cy in range(MAP_H) for cx in range(MAP_W)
                         if not g[cy][cx])

        # release from a low, open cell, the way the spawner does
        start = None
        for cy in range(MAP_H - 3, 0, -1):
            for cx in range(2, MAP_W - 2):
                if not g[cy][cx] and not g[cy][cx + 1]:
                    start = (cx * CELL, cy * CELL)
                    break
            if start:
                break

        visited, path = trace_bubble(g, f, *start)
        coverage = 100.0 * len(visited) / open_cells

        print("level %d: %d open cells, bubble released at %s" % (n, open_cells, start))
        print("         visits %d cells (%.0f%% of the open playfield)"
              % (len(visited), coverage))

        # A bubble that circulates keeps moving through new cells for a
        # long time; one that is stuck settles into a handful.
        if len(visited) < 12:
            print("         FAIL: bubble is stuck, the current is not closing")
            ok = False
        else:
            span_x = max(c[0] for c in visited) - min(c[0] for c in visited)
            span_y = max(c[1] for c in visited) - min(c[1] for c in visited)
            print("         travel span %d x %d cells" % (span_x, span_y))
            if span_x < 4 or span_y < 4:
                print("         FAIL: the path is not a loop, it is a line")
                ok = False
        if show_trace:
            show(g, f, path)
        print()

    print("wind current model:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
