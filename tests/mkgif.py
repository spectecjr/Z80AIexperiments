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


SWING = 640             # how far the camera slides either way, world units
SWING_SECS = 8.0        # and how long a whole swing takes
WALK = 26               # forward, world units a 50th of a second


def stroll(t, hz=50):
    """Where the camera is on frame t of the chequered floor demos.

    A square is 256 world units, so this is a slide of two and a half
    squares either way taking eight seconds, and a walk forwards of
    five squares a second. At the bottom of the screen, where a square
    is 64 pixels across, the board slides sideways at most 3 pixels a
    frame; it was 12, which reads as a lurch rather than a camera.
    """
    import math
    camx = int(SWING * math.sin(2 * math.pi * t / (SWING_SECS * hz)))
    camz = int(t * WALK * 50 / hz) & 0xFFFF
    return camx, camz


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


def copper(frames, pars, fog, haze=None):
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
            if haze is not None:
                g[y][f[y] == 3] = slot(sam_rgb(haze[y]))
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


def portal(outdir, seconds=12):
    """portal at its measured rate: 400,481 T-states a frame, 15 Hz.

    room3d's renderer driven through doors: a lap of the ring corridor
    of a nine cell maze, looking around between the doors. Compare
    demo/room.gif, which is the same raster drawing one room.
    """
    import math
    import portal as P
    from test_portal import path
    b = Bench("harness_portal.asm", org=0)
    s = b.syms
    b.call_regs(s["p_init"])
    n = int(seconds * 15)
    frames, ts = [], []
    for t in range(n):
        cx, cz, ca = path(t, n)
        b.poke(s["r3d_cx"], (cx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["r3d_cz"], (cz & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["r3d_ca"], bytes([ca]))
        b.poke(s["p_here"], bytes([P.sector_for((cx, cz, ca))]))
        into = b.peek(s["r3d_back"], 1)[0]
        tt, _ = b.call_regs(s["p_frame"])
        ts.append(tt)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/portal.gif" % outdir
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


def chequer(outdir, seconds=8):
    """chequer at its measured rate: 92,335 T-states a frame, 50 Hz.

    Forward all the way and weaving sideways. The palette flips the
    board's depth stripes and grades the whole picture with distance,
    so what is drawn is two colour indices and nothing else - see
    chequer.md.
    """
    b = Bench("harness_chq.asm", org=0)
    s = b.syms
    b.call_regs(s["chq_init"])
    fog = b.peek(s["chq_fog"], 2 * 192)
    n = seconds * 50
    frames, pars, ts = [], [], []
    for t in range(n):
        camx, camz = stroll(t)
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


def twist(outdir, seconds=6):
    """twist at its measured rate: 102,376 T-states a frame, 50 Hz.

    The ribbon is one backdrop index and eight shades, so the gradient
    behind it is palette work rather than pixels - the same as chequer
    - and it is applied here the way the line interrupt would.
    """
    b = Bench("harness_twist.asm", org=0)
    s = b.syms
    b.call_regs(s["tw_init"])
    bg = list(b.peek(s["tw_bg"], 192))
    ramp = list(b.peek(s["tw_ramp"], 14))
    pal = [(0, 0, 0)] * 16
    for i, v in enumerate(ramp):
        pal[2 + i] = sam_rgb(v)
    rows = {}
    for v in set(bg):
        rows[v] = len(pal)
        pal.append(sam_rgb(v))
    n = seconds * 50
    frames, ts = [], []
    import math
    for t in range(n):
        # the waves travel down the ribbon while the whole thing turns,
        # and the turn itself eases back and forth
        b.poke(s["tw_ang"], bytes([(-t * 2) & 255]))
        b.poke(s["tw_delta"],
               bytes([int(t * 1.5 + 40 * math.sin(2 * math.pi * t / 260))
                      & 255]))
        into = b.peek(s["tw_back"], 1)[0]
        tt, _ = b.call_regs(s["tw_frame"])
        ts.append(tt)
        f = unpack(b.peek(BUF[into], 128 * 192))
        for y in range(192):                # the backdrop's own colour
            f[y][f[y] == 1] = rows[bg[y]]
        frames.append(f)
    p = "%s/twist.gif" % outdir
    durs = held(ts)
    size = write_gif(p, frames, pal, durs)
    got, bad, secs = check_gif(p, frames, pal, durs)
    report(p, size, n, durs, secs, got, bad)


def harrier(outdir, seconds=8):
    """harrier at its measured rate: 221,451 T-states a frame, 25 Hz.

    The same floor as chequer, with every boundary on its exact pixel
    instead of a four pixel grid. Compare demo/chequer.gif.
    """
    b = Bench("harness_hr.asm", org=0)
    s = b.syms
    b.call_regs(s["hr_init"])
    fog = b.peek(s["hr_fog"], 2 * 192)
    haze = b.peek(s["hr_hazec"], 192)
    n = int(seconds * 25)
    frames, pars, ts = [], [], []
    for t in range(n):
        camx, camz = stroll(t, 25)
        b.poke(s["hr_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["hr_camz"], camz.to_bytes(2, "little"))
        into = b.peek(s["hr_back"], 1)[0]
        tt, _ = b.call_regs(s["hr_frame"])
        ts.append(tt)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
        pars.append(list(b.peek(s["hr_par"], 192)))
    idx, pal = copper(frames, pars, fog, haze)
    p = "%s/harrier.gif" % outdir
    durs = held(ts)
    size = write_gif(p, idx, pal, durs)
    got, bad, secs = check_gif(p, idx, pal, durs)
    report(p, size, n, durs, secs, got, bad)


def chequer3(outdir, seconds=8):
    """chequer3 at its measured rate: 110,806 T-states a frame, 50 Hz.

    harrier's screen - every boundary on its exact pixel - drawn out of
    compiled runs instead of a dispatch a square, in half the time.
    Compare demo/harrier.gif, which is the same board at 25 Hz.
    """
    b = Bench("harness_chq3.asm", org=0)
    s = b.syms
    b.call_regs(s["chq3_init"])
    fog = b.peek(s["chq3_fog"], 2 * 192)
    haze = b.peek(s["chq3_hazec"], 192)
    n = int(seconds * 50)
    frames, pars, ts = [], [], []
    for t in range(n):
        camx, camz = stroll(t)
        b.poke(s["chq3_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["chq3_camz"], camz.to_bytes(2, "little"))
        into = b.peek(s["chq3_back"], 1)[0]
        tt, _ = b.call_regs(s["chq3_frame"])
        ts.append(tt)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
        pars.append(list(b.peek(s["chq3_par"], 192)))
    idx, pal = copper(frames, pars, fog, haze)
    p = "%s/chequer3.gif" % outdir
    durs = held(ts)
    size = write_gif(p, idx, pal, durs)
    got, bad, secs = check_gif(p, idx, pal, durs)
    report(p, size, n, durs, secs, got, bad)


PRISM_PAL = ([(32 * i, 32 * i, 30 * i) for i in range(8)]
             + [(36 * i, 6 * i, 6 * i) for i in range(8)])


def chequer4(outdir, seconds=8):
    """chequer4 at its measured rate: 114,656 T-states a frame, 50 Hz.

    chequer3's board with the depth stripes drawn in the pixels rather
    than flipped in the palette, which is why nothing here rebuilds a
    parity table: the palette below is one fixed gradient a scanline,
    the same on every frame of the demo. Compare demo/chequer3.gif,
    which is the same picture the other way round.
    """
    b = Bench("harness_chq4.asm", org=0)
    s = b.syms
    b.call_regs(s["chq4_init"])
    fog = b.peek(s["chq4_fog"], 2 * 192)
    haze = b.peek(s["chq4_hazec"], 192)
    n = int(seconds * 50)
    frames, ts = [], []
    for t in range(n):
        camx, camz = stroll(t)
        b.poke(s["chq4_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["chq4_camz"], camz.to_bytes(2, "little"))
        into = b.peek(s["chq4_back"], 1)[0]
        tt, _ = b.call_regs(s["chq4_frame"])
        ts.append(tt)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    still = [[0] * 192] * n                     # the palette does not move
    idx, pal = copper(frames, still, fog, haze)
    p = "%s/chequer4.gif" % outdir
    durs = held(ts)
    size = write_gif(p, idx, pal, durs)
    got, bad, secs = check_gif(p, idx, pal, durs)
    report(p, size, n, durs, secs, got, bad)


def entropypre(outdir, seconds=14):
    """The traced Entropy logo, precomputed: 220,823 T-states, 27.2 Hz.

    Nine convex pieces against the provisional shape's seven, because
    the sigma's bar ends are cut back to points and its left edge is
    notched. 184 bytes of table a frame rather than 144, which no
    longer fits above the screen buffers - eleven frames of point live
    down in the low 8K and a table of pointers says which is where.
    """
    b = Bench("harness_entropypre.asm", org=0)
    s = b.syms
    b.call_regs(s["pp_init"])
    n = int(seconds * 27.2)
    frames, ts = [], []
    for t in range(n):
        into = b.peek(s["rndl_back"], 1)[0]
        tt, _ = b.call_regs(s["pp_frame"])
        ts.append(tt)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/entropypre.gif" % outdir
    durs = held(ts)
    size = write_gif(p, frames, PRISM_PAL, durs)
    got, bad, secs = check_gif(p, frames, PRISM_PAL, durs)
    report(p, size, n, durs, secs, got, bad)


def prismpre(outdir, seconds=14):
    """prismpre at its measured rate: 204,625 T-states a frame, 29.3 Hz.

    The same logo as prism, frame for frame, with the spin, the
    transform, the lighting and the sort read out of a 9,216-byte
    table instead of worked out. What that buys is 220,000 T-states a
    frame; what it costs is the loop - 64 frames, so one turn an axis
    rather than prism's two, three and one per 256.
    """
    b = Bench("harness_prismpre.asm", org=0)
    s = b.syms
    b.call_regs(s["pp_init"])
    n = int(seconds * 29.3)
    frames, ts = [], []
    for t in range(n):
        into = b.peek(s["rndl_back"], 1)[0]
        tt, _ = b.call_regs(s["pp_frame"])
        ts.append(tt)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/prismpre.gif" % outdir
    durs = held(ts)
    size = write_gif(p, frames, PRISM_PAL, durs)
    got, bad, secs = check_gif(p, frames, PRISM_PAL, durs)
    report(p, size, n, durs, secs, got, bad)


STAR_PAL = [(32 * i, 32 * i, 30 * i) for i in range(8)] + [(0, 0, 0)] * 8


def balls(outdir, seconds=8):
    """Vector balls: 108,270 T-states a frame, 55.4 Hz, 20 of them."""
    b = Bench("harness_balls.asm", org=0)
    s = b.syms
    b.call_regs(s["bl_init"])
    n = int(seconds * 50)
    frames, ts = [], []
    for t in range(n):
        into = b.peek(s["bl_back"], 1)[0]
        tt, _ = b.call_regs(s["bl_frame"])
        ts.append(tt)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/balls.gif" % outdir
    durs = held(ts)
    size = write_gif(p, frames, STAR_PAL, durs)
    got, bad, secs = check_gif(p, frames, STAR_PAL, durs)
    report(p, size, n, durs, secs, got, bad)


def stars(outdir, seconds=8):
    """A 3D starfield: 197,813 T-states a frame, 30.3 Hz, 192 stars."""
    b = Bench("harness_stars.asm", org=0)
    s = b.syms
    b.call_regs(s["st_init"])
    n = int(seconds * 30.3)
    frames, ts = [], []
    for t in range(n):
        into = b.peek(s["st_back"], 1)[0]
        tt, _ = b.call_regs(s["st_frame"])
        ts.append(tt)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/stars.gif" % outdir
    durs = held(ts)
    size = write_gif(p, frames, STAR_PAL, durs)
    got, bad, secs = check_gif(p, frames, STAR_PAL, durs)
    report(p, size, n, durs, secs, got, bad)


def prism(outdir, seconds=14):
    """prism at its measured rate: 446,602 T-states a frame, 13.4 Hz.

    A logo cut into seven convex quads and extruded, drawn with
    renderlit's rasteriser and face table: an extruded quad has the
    same eight vertices and six quad faces a cube has. The shape is
    provisional - a description of the Entropy logo rather than the
    artwork.
    """
    b = Bench("harness_prism.asm", org=0)
    s = b.syms
    b.call_regs(s["pr_init"])
    n = int(seconds * 13.4)
    frames, ts = [], []
    for t in range(n):
        into = b.peek(s["rndl_back"], 1)[0]
        tt, _ = b.call_regs(s["pr_frame"])
        ts.append(tt)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/prism.gif" % outdir
    durs = held(ts)
    size = write_gif(p, frames, PRISM_PAL, durs)
    got, bad, secs = check_gif(p, frames, PRISM_PAL, durs)
    report(p, size, n, durs, secs, got, bad)


CUBES_PAL = ([(36 * i, 13 * i, 9 * i) for i in range(8)]
             + [(9 * i, 15 * i, 36 * i) for i in range(8)])


def cubes(outdir, seconds=12):
    """cubes at its measured rate: 419,478 T-states a frame, 13.5 Hz.

    Four lit cubes bouncing in a room, with gravity, off the walls and
    off each other. Compare demo/cube.gif, which is one of them with
    no room and no gravity.
    """
    b = Bench("harness_cubes.asm", org=0)
    s = b.syms
    b.call_regs(s["cb_init"])
    n = int(seconds * 13.5)
    frames, ts = [], []
    for t in range(n):
        into = b.peek(s["rndl_back"], 1)[0]
        tt, _ = b.call_regs(s["cb_frame"])
        ts.append(tt)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/cubes.gif" % outdir
    durs = held(ts)
    size = write_gif(p, frames, CUBES_PAL, durs)
    got, bad, secs = check_gif(p, frames, CUBES_PAL, durs)
    report(p, size, n, durs, secs, got, bad)


ROTO_PAL = ([(0, 0, 0)]
            + [(30 + 30 * i, 10 + 12 * i, 60 + 26 * i) for i in range(7)]
            + [(40 + 28 * i, 30 + 26 * i, 20 + 10 * i) for i in range(8)])


def roto(outdir, seconds=6):
    """roto at its measured rate: 449,272 T-states a frame, 13.4 Hz.

    u steps in 8.8 and v in 4.12, because v's row wants to be in the
    top nibble of its high byte - see roto.md.
    """
    import math
    b = Bench("harness_roto.asm", org=0)
    s = b.syms
    b.call_regs(s["rz_init"])
    rate = 1000.0 / held([b.call_regs(s["rz_frame"])[0]])[0]
    n = int(seconds * rate)
    frames, ts = [], []
    for t in range(n):
        a = 2 * math.pi * t / 190
        z = 0.20 + 0.16 * math.sin(2 * math.pi * t / 97)    # texels a byte
        du = int(-256 * z * math.cos(a))                    # leftwards
        dvv = int(4096 * z * math.sin(a))
        dux = int(256 * z * math.sin(a))                    # one row down
        dvx = int(4096 * z * math.cos(a))
        ur = int(2048 + 900 * math.sin(2 * math.pi * t / 143))
        vr = int(2048 + 900 * math.cos(2 * math.pi * t / 111))
        for nm, v in (("rz_ur", ur), ("rz_vr", vr), ("rz_du", du),
                      ("rz_dv", dvv), ("rz_dux", dux), ("rz_dvx", dvx)):
            b.poke(s[nm], (v & 0xFFFF).to_bytes(2, "little"))
        into = b.peek(s["rz_back"], 1)[0]
        tt, _ = b.call_regs(s["rz_frame"])
        ts.append(tt)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/roto.gif" % outdir
    durs = held(ts)
    size = write_gif(p, frames, ROTO_PAL, durs)
    got, bad, secs = check_gif(p, frames, ROTO_PAL, durs)
    report(p, size, n, durs, secs, got, bad)


VOX_PAL = ([(0, 0, 0), (58, 78, 130)]
           + [(18 + i * 9, 40 + i * 11, 22 + i * 5) for i in range(14)])


def vox(outdir, seconds=8):
    """vox at its measured rate: 323,952 T-states a frame, 18.5 Hz.

    A flight over the map: forward along the heading, turning slowly.
    px is 8.8 in map cells and py is 4.12, so the same speed is a
    different number in each - see vox.md.
    """
    import math
    b = Bench("harness_vox.asm", org=0)
    s = b.syms
    b.call_regs(s["vx_init"])
    rate = 1000.0 / held([b.call_regs(s["vx_frame"])[0]])[0]
    n = int(seconds * rate)
    px, py = 0x0800, 0x8000
    frames, ts = [], []
    for t in range(n):
        ang = 0.6 + 1.7 * math.sin(2 * math.pi * t / 210)
        v = 0.055
        px = int(px + v * 256 * math.cos(ang)) & 0xFFFF
        py = int(py + v * 4096 * math.sin(ang)) & 0xFFFF
        dx0 = int(1.0 * 256 * math.cos(ang - 0.5)) & 0xFFFF
        dy0 = int(1.0 * 4096 * math.sin(ang - 0.5)) & 0xFFFF
        sx = int(1.0 * 256 * (math.cos(ang + 0.5)
                              - math.cos(ang - 0.5)) / 63) & 0xFFFF
        sy = int(1.0 * 4096 * (math.sin(ang + 0.5)
                               - math.sin(ang - 0.5)) / 63) & 0xFFFF
        for nm, v2 in (("vx_px", px), ("vx_py", py), ("vx_dx0", dx0),
                       ("vx_dy0", dy0), ("vx_sx", sx), ("vx_sy", sy)):
            b.poke(s[nm], v2.to_bytes(2, "little"))
        into = b.peek(s["vx_back"], 1)[0]
        tt, _ = b.call_regs(s["vx_frame"])
        ts.append(tt)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/vox.gif" % outdir
    durs = held(ts)
    size = write_gif(p, frames, VOX_PAL, durs)
    got, bad, secs = check_gif(p, frames, VOX_PAL, durs)
    report(p, size, n, durs, secs, got, bad)


def chequer2(outdir, seconds=8):
    """chequer2 at its measured rate: 104,232 T-states a frame, 50 Hz.

    The same floor as chequer with the phase exact to the pixel, so the
    board slides sideways smoothly instead of in four-pixel steps.
    Compare demo/chequer.gif.
    """
    b = Bench("harness_chq2.asm", org=0)
    s = b.syms
    b.call_regs(s["chq2_init"])
    fog = b.peek(s["chq_fog"], 2 * 192)
    n = seconds * 50
    frames, pars, ts = [], [], []
    for t in range(n):
        camx, camz = stroll(t)
        b.poke(s["chq2_camx"], (camx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["chq2_camz"], camz.to_bytes(2, "little"))
        into = b.peek(s["chq2_back"], 1)[0]
        tt, _ = b.call_regs(s["chq2_frame"])
        ts.append(tt)
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
        pars.append(list(b.peek(s["chq2_par"], 192)))
    idx, pal = copper(frames, pars, fog)
    p = "%s/chequer2.gif" % outdir
    durs = held(ts)
    size = write_gif(p, idx, pal, durs)
    got, bad, secs = check_gif(p, idx, pal, durs)
    report(p, size, n, durs, secs, got, bad)


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "/tmp"
    cube(d)
    cubes(d)
    stars(d)
    balls(d)
    prism(d)
    prismpre(d)
    entropypre(d)
    room(d)
    portal(d)
    maze(d)
    maze(d, harness="harness_wolf96.asm", name="maze96")
    maze(d, harness="harness_wolfwide.asm", name="mazewide")
    chequer(d)
    chequer2(d)
    harrier(d)
    chequer3(d)
    chequer4(d)
    twist(d)
    roto(d)
    vox(d)
