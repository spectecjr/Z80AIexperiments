#!/usr/bin/env python3
"""Record the renderers running on the emulated Z80 as animated GIFs.

GIF is a good fit for a MODE 4 screen: sixteen colours and a palette,
which is what the SAM has, so the nibbles are palette indices already
and nothing is quantised.

    pip install pillow numpy
    python3 tests/mkgif.py [outdir]
"""
import sys

import numpy as np
from PIL import Image

from bench import Bench


def write_gif(path, frames, palette, ms):
    """frames: a list of (H, W) uint8 arrays of palette indices."""
    pal = []
    for r, g, b in palette:
        pal += [r, g, b]
    pal += [0] * (768 - len(pal))
    imgs = []
    for f in frames:
        im = Image.frombytes("P", (f.shape[1], f.shape[0]), f.tobytes())
        im.putpalette(pal)
        imgs.append(im)
    imgs[0].save(path, save_all=True, append_images=imgs[1:], loop=0,
                 duration=ms, disposal=1, optimize=True)
    return len(open(path, "rb").read())


def check_gif(path, frames, palette, ms):
    """Read it back with a decoder that had no part in writing it.

    Pillow merges runs of identical frames and adds their delays
    together, and it renumbers the palette, so the comparison is by
    colour and the decoded frames are spread back out by their delays.
    """
    from PIL import ImageSequence
    pal = np.array(palette, dtype=np.uint8)
    got = []
    total = 0
    for f in ImageSequence.Iterator(Image.open(path)):
        d = f.info.get("duration", ms)
        total += d
        got += [np.array(f.convert("RGB"))] * max(1, round(d / ms))
    bad = sum(1 for g, w in zip(got, frames) if not np.array_equal(g, pal[w]))
    return len(got), bad, total / 1000.0

def unpack(raw):
    """A MODE 4 buffer into one byte a pixel."""
    b = np.frombuffer(raw, dtype=np.uint8).reshape(192, 128)
    img = np.empty((192, 256), np.uint8)
    img[:, 0::2] = b >> 4
    img[:, 1::2] = b & 15
    return img


BUF = {0x80: 0x8000, 0x20: 0x2000}

CUBE_PAL = ([(32 * i, 10 * i, 8 * i) for i in range(8)]
            + [(8 * i, 13 * i, 32 * i) for i in range(8)])

ROOM_PAL = ([(0, 0, 0)]
            + [(28 + 32 * i, 12 + 13 * i, 9 + 8 * i) for i in range(6)]
            + [(72, 60, 44)]
            + [(10 + 11 * i, 15 + 15 * i, 32 + 32 * i) for i in range(6)]
            + [(24, 24, 42)]
            + [(255, 255, 255)])


def cube(outdir, seconds=10):
    """renderlit at its measured rate: 112,221 T-states a frame, 50 Hz."""
    b = Bench("harness_renderlit.asm", org=0)
    s = b.syms
    b.call_regs(s["demo_init"])
    b.call_regs(s["rndl_init"])
    n = seconds * 50
    frames = []
    for _ in range(n):
        b.call_regs(s["demo_frame"])
        into = b.peek(s["rndl_back"], 1)[0]
        b.call_regs(s["rndl_frame"])
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/lit_cube.gif" % outdir
    size = write_gif(p, frames, CUBE_PAL, 20)
    got, bad, secs = check_gif(p, frames, CUBE_PAL, 20)
    print("  %-18s %3d frames, 50 Hz, %.2fs, %6.1f KB, %d of %d wrong"
          % (p, n, secs, size / 1024, bad, got))


def room(outdir, seconds=10):
    """room3d at its measured rate: 237,161 T-states a frame, 25 Hz.

    That is the average; a view with three or four walls in it costs
    nearer 300,000 and would drop to about 20 Hz on real hardware.
    """
    import math
    b = Bench("harness_room.asm", org=0)
    s = b.syms
    b.call_regs(s["r3d_init"])
    n = seconds * 25
    frames = []
    for t in range(n):
        cx = int(45 * math.sin(2 * math.pi * t / 250))   # a wander that
        cz = int(35 * math.cos(2 * math.pi * t / 188))   # keeps corners
        ca = (t * 2 + 64) & 255                          # in view
        b.poke(s["r3d_cx"], (cx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["r3d_cz"], (cz & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["r3d_ca"], bytes([ca]))
        into = b.peek(s["r3d_back"], 1)[0]
        b.call_regs(s["r3d_frame"])
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/room.gif" % outdir
    size = write_gif(p, frames, ROOM_PAL, 40)
    got, bad, secs = check_gif(p, frames, ROOM_PAL, 40)
    print("  %-18s %3d frames, 25 Hz, %.2fs, %6.1f KB, %d of %d wrong"
          % (p, n, secs, size / 1024, bad, got))


MAZE_PAL = [(0, 0, 0), (58, 58, 68), (118, 120, 132), (88, 90, 100),
            (150, 152, 164), (0, 0, 0), (0, 0, 0), (0, 0, 0),
            (104, 42, 32), (0, 0, 0), (168, 74, 52), (0, 0, 0),
            (0, 0, 0), (0, 0, 0), (38, 38, 52), (94, 74, 52)]


def maze(outdir, seconds=12):
    """wolf3d at its measured rate: 713,368 T-states a frame, 8.4 Hz.

    The camera walks itself: a step forward each frame, and where the
    cell ahead is solid it turns on the spot until it is not.
    """
    import math
    b = Bench("harness_wolf.asm", org=0)
    s = b.syms
    b.call_regs(s["w3d_init"])
    mp = b.peek(s["w3d_map"], 256)
    px, py, ang, spin = 3.5, 3.5, 40, 3
    n = int(seconds * 8.4)
    frames = []
    for _ in range(n):
        dx = math.cos(2 * math.pi * ang / 256)
        dy = math.sin(2 * math.pi * ang / 256)
        for _ in range(64):                     # turn until the way ahead
            ax = px + dx * 0.55                 # is clear, then walk
            ay = py + dy * 0.55
            if not mp[(int(ay) & 15) * 16 + (int(ax) & 15)]:
                break
            ang = (ang + spin) & 255
            dx = math.cos(2 * math.pi * ang / 256)
            dy = math.sin(2 * math.pi * ang / 256)
        else:
            spin = -spin
        px += dx * 0.055
        py += dy * 0.055
        b.poke(s["w3d_px"], int(px * 256).to_bytes(2, "little"))
        b.poke(s["w3d_py"], int(py * 256).to_bytes(2, "little"))
        b.poke(s["w3d_ang"], bytes([ang & 255]))
        into = b.peek(s["w3d_back"], 1)[0]
        b.call_regs(s["w3d_frame"])
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/maze.gif" % outdir
    size = write_gif(p, frames, MAZE_PAL, 120)
    got, bad, secs = check_gif(p, frames, MAZE_PAL, 120)
    print("  %-18s %3d frames, 8.4 Hz, %.2fs, %6.1f KB, %d of %d wrong"
          % (p, n, secs, size / 1024, bad, got))


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "/tmp"
    cube(d)
    room(d)
    maze(d)
