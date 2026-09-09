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
    """room3d at its measured rate: 291,953 T-states a frame, 20 Hz."""
    import math
    b = Bench("harness_room.asm", org=0)
    s = b.syms
    b.call_regs(s["r3d_init"])
    n = seconds * 20
    frames = []
    for t in range(n):
        cx = int(45 * math.sin(2 * math.pi * t / 200))   # a wander that
        cz = int(35 * math.cos(2 * math.pi * t / 150))   # keeps corners
        ca = (t * 3 + 64) & 255                          # in view
        b.poke(s["r3d_cx"], (cx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["r3d_cz"], (cz & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["r3d_ca"], bytes([ca]))
        into = b.peek(s["r3d_back"], 1)[0]
        b.call_regs(s["r3d_frame"])
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/room.gif" % outdir
    size = write_gif(p, frames, ROOM_PAL, 50)
    got, bad, secs = check_gif(p, frames, ROOM_PAL, 50)
    print("  %-18s %3d frames, 20 Hz, %.2fs, %6.1f KB, %d of %d wrong"
          % (p, n, secs, size / 1024, bad, got))


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "/tmp"
    cube(d)
    room(d)
