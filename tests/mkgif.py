#!/usr/bin/env python3
"""Record the renderers running on the emulated Z80 as animated GIFs.

GIF is a good fit for a MODE 4 screen: sixteen colours and a palette,
which is what the SAM has, so the nibbles are palette indices already
and nothing is quantised.

    pip install pillow numpy
    python3 tests/mkgif.py [outdir]

Each frame is held for the whole number of 50ths of a second it costs
on the emulated Z80, so the GIF runs at the rate the routine would
really manage against the display, judder and all, rather than at its
average.
"""
import sys

import numpy as np
from PIL import Image

from bench import Bench


TICK = 20               # one display frame on a 50 Hz SAM, in ms
TFRAME = 6000000 // 50  # and in T-states of a 6 MHz Z80


def held(ts):
    """How long a frame is actually on screen, waiting for the flyback.

    A routine that syncs to the display cannot show a frame for part of
    a display frame: whatever it costs, it is held for the whole number
    of 50ths of a second it fits into. So a frame is not 1/8.4 of a
    second because that is the average cost - it is 120ms when it fits
    in six display frames and 140ms when it needs seven, and the
    unevenness is what the eye actually sees.
    """
    return [TICK * max(1, -(-int(t) // TFRAME)) for t in ts]


def write_gif(path, frames, palette, durs):
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
                 duration=durs, disposal=1, optimize=True)
    return len(open(path, "rb").read())


def check_gif(path, frames, palette, durs):
    """Read it back with a decoder that had no part in writing it.

    Pillow merges runs of identical frames and adds their delays
    together, and it renumbers the palette, so both sides are spread
    out into display frames and compared as colours.
    """
    from PIL import ImageSequence
    pal = np.array(palette, dtype=np.uint8)
    want = []
    for f, d in zip(frames, durs):
        want += [pal[f]] * (d // TICK)
    got = []
    total = 0
    for f in ImageSequence.Iterator(Image.open(path)):
        d = f.info.get("duration", TICK)
        total += d
        got += [np.array(f.convert("RGB"))] * max(1, round(d / TICK))
    bad = sum(1 for g, w in zip(got, want) if not np.array_equal(g, w))
    bad += abs(len(got) - len(want))
    return len(got), bad, total / 1000.0


def report(path, size, n, durs, secs, got, bad):
    hold = {}
    for d in durs:
        hold[d] = hold.get(d, 0) + 1
    print("  %-18s %3d frames, %.1f Hz, %.2fs, %6.1f KB, %d of %d wrong"
          % (path, n, n / (sum(durs) / 1000.0), secs, size / 1024, bad, got))
    print("  %-18s %s" % ("", ", ".join(
        "%d at %dms" % (hold[d], d) for d in sorted(hold))))

def sam_rgb(v):
    """A SAM palette byte back to RGB, the inverse of mkchqdata.sam."""
    br = (v >> 3) & 1
    out = []
    for hi, lo in ((6, 2), (5, 1), (4, 0)):         # green, red, blue
        lvl = (((v >> hi) & 1) << 2) | (((v >> lo) & 1) << 1) | br
        out.append(lvl * 255 // 7)
    g, r, b = out
    return (r, g, b)


def copper(frames, pars, fog):
    """Flatten per-scanline palettes into one indexed image and palette.

    A routine that flips two palette entries a scanline shows more
    colours at once than the sixteen a MODE 4 screen has, so the frames
    are remapped here into a palette of everything they use between
    them - which is what the screen would actually be showing.
    """
    pal, seen = [], {}

    def slot(rgb):
        if rgb not in seen:
            seen[rgb] = len(pal)
            pal.append(rgb)
        return seen[rgb]

    out = []
    for f, par in zip(frames, pars):
        g = np.zeros(f.shape, np.uint8)
        for y in range(f.shape[0]):
            a, b = fog[2 * y], fog[2 * y + 1]
            if par[y]:
                a, b = b, a
            g[y][f[y] == 1] = slot(sam_rgb(a))
            g[y][f[y] == 2] = slot(sam_rgb(b))
        out.append(g)
    if len(pal) > 256:
        raise SystemExit("copper: %d colours, more than a GIF holds"
                         % len(pal))
    return out, pal


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
    frames, ts = [], []
    for _ in range(n):
        t, _ = b.call_regs(s["demo_frame"])
        into = b.peek(s["rndl_back"], 1)[0]
        t2, _ = b.call_regs(s["rndl_frame"])
        ts.append(t + t2)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/lit_cube.gif" % outdir
    durs = held(ts)
    size = write_gif(p, frames, CUBE_PAL, durs)
    got, bad, secs = check_gif(p, frames, CUBE_PAL, durs)
    report(p, size, n, durs, secs, got, bad)


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
    frames, ts = [], []
    for t in range(n):
        cx = int(45 * math.sin(2 * math.pi * t / 250))   # a wander that
        cz = int(35 * math.cos(2 * math.pi * t / 188))   # keeps corners
        ca = (t * 2 + 64) & 255                          # in view
        b.poke(s["r3d_cx"], (cx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["r3d_cz"], (cz & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["r3d_ca"], bytes([ca]))
        into = b.peek(s["r3d_back"], 1)[0]
        t, _ = b.call_regs(s["r3d_frame"])
        ts.append(t)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/room.gif" % outdir
    durs = held(ts)
    size = write_gif(p, frames, ROOM_PAL, durs)
    got, bad, secs = check_gif(p, frames, ROOM_PAL, durs)
    report(p, size, n, durs, secs, got, bad)


MAZE_PAL = [(0, 0, 0), (58, 58, 68), (118, 120, 132), (88, 90, 100),
            (150, 152, 164), (0, 0, 0), (0, 0, 0), (0, 0, 0),
            (104, 42, 32), (0, 0, 0), (168, 74, 52), (0, 0, 0),
            (0, 0, 0), (0, 0, 0), (38, 38, 52), (94, 74, 52)]


def maze(outdir, seconds=12, harness="harness_wolf.asm", name="maze"):
    """wolf3d, whichever viewport the harness was built for.

    The camera walks itself: a step forward each frame, and where the
    cell ahead is solid it turns on the spot until it is not.
    """
    import math
    b = Bench(harness, org=0)
    s = b.syms
    b.call_regs(s["w3d_init"])
    mp = b.peek(s["w3d_map"], 256)
    px, py, ang, spin = 3.5, 3.5, 40, 3
    b.call_regs(s["w3d_frame"])                 # so the pace is known
    rate = 1000.0 / held([b.call_regs(s["w3d_frame"])[0]])[0]
    n = int(seconds * rate)
    frames, ts = [], []
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
        t, _ = b.call_regs(s["w3d_frame"])
        ts.append(t)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/%s.gif" % (outdir, name)
    durs = held(ts)
    size = write_gif(p, frames, MAZE_PAL, durs)
    got, bad, secs = check_gif(p, frames, MAZE_PAL, durs)
    report(p, size, n, durs, secs, got, bad)


def chequer(outdir, seconds=6):
    """chequer at its measured rate: 92,404 T-states a frame, 50 Hz.

    Forward all the way and weaving sideways. The palette flips the
    board's depth stripes and grades the whole picture with distance,
    so what is drawn is two colour indices and nothing else - see
    chequer.md.
    """
    import math
    b = Bench("harness_chq.asm", org=0)
    s = b.syms
    b.call_regs(s["chq_init"])
    fog = b.peek(s["chq_fog"], 2 * 192)
    n = seconds * 50
    frames, pars, ts = [], [], []
    for t in range(n):
        camx = int(1400 * math.sin(2 * math.pi * t / 190))
        camz = (t * 26) & 0xFFFF
        b.poke(s["chq_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["chq_camz"], camz.to_bytes(2, "little"))
        into = b.peek(s["chq_back"], 1)[0]
        tt, _ = b.call_regs(s["chq_frame"])
        ts.append(tt)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
        pars.append(list(b.peek(s["chq_par"], 192)))
    idx, pal = copper(frames, pars, fog)
    p = "%s/chequer.gif" % outdir
    durs = held(ts)
    size = write_gif(p, idx, pal, durs)
    got, bad, secs = check_gif(p, idx, pal, durs)
    report(p, size, n, durs, secs, got, bad)


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "/tmp"
    cube(d)
    room(d)
    maze(d)
    maze(d, harness="harness_wolf96.asm", name="maze96")
    maze(d, harness="harness_wolfwide.asm", name="mazewide")
    chequer(d)
