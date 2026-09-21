#!/usr/bin/env python3
"""Boot build/chequer10.sbt on SimCoupe and check what it put on the screen.

    SIMCOUPE=/path/to/simcoupe python3 tests/simshot10.py [seconds ...]

`tests/test_sbt10.py` runs the same image on the bench's Z80 with a
model of the paging and the frame interrupt, and that settles whether
the loader and the driver are right. This settles the rest of the
machine: the real ROM loads the file, the real ASIC pages and displays
it, and the real memory contention decides how long a frame takes.

Each screen is matched against `tests/chequer10.py` - the model the
bench test compares against - for every frame of the flight, so a match
identifies which frame it is as well as proving it right.

**And it times the demo on the machine.** Not by watching the clock while
it runs - the flight loops every 200 frames, and a pair of screens far
enough apart to time reliably is a pair that cannot tell one lap from
two. Instead it builds two images that draw a known number of frames and
then halt, runs each under SimCoupe's `-exitonhalt`, and takes the
difference: the boot and the 377K load cancel, and what is left is
frames. `tests/sam_tick.asm` does the same trick for the HOST - count
display frames and halt - so the emulator's own speed is measured rather
than assumed, and the demo's rate can be corrected by it.

Needs SimCoupe, xdotool, and an X display; it starts an Xvfb if DISPLAY
is unset.
"""
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

os.environ.setdefault("HARRIER_MINP", "1")
os.environ.setdefault("HARRIER_HZ", "95")
os.environ.setdefault("HARRIER_CAMH", "308")
os.environ.setdefault("DESERT_ROWS", "20")
os.environ.setdefault("HARRIER_SKY", "15")
os.environ.setdefault("DESERT_SKY", "15")
os.environ.setdefault("JET_W", "24")
os.environ.setdefault("JET_H", "48")
os.environ.setdefault("CHQ_SWAP", "0xBB")
os.environ.setdefault("JET_PAL", "board4")
os.environ.setdefault("DESERT_PAL", "board4")

import numpy as np                                      # noqa: E402
from PIL import Image                                   # noqa: E402

import chequer10 as C                                   # noqa: E402
from mkdemo10 import palette, path as flight, RATE      # noqa: E402

SIMCOUPE = os.environ.get("SIMCOUPE", "simcoupe")
MAXI = 255                      # SimCoupe's maxintensity, its default
W, H = 256, 192
LOAD = 14.0                     # seconds the image takes to load and start
FRAME_T = 119808                # a display frame on a 6 MHz SAM
PAL_HZ = 50.08                  # and how many of them a second


def rgb_of_sam():
    """The RGB SimCoupe shows for each of the 128 SAM palette bytes."""
    out = {}
    for i in range(128):
        r = ((i & 0x02) << 0) | ((i & 0x20) >> 3) | ((i & 0x08) >> 3)
        g = ((i & 0x04) >> 1) | ((i & 0x40) >> 4) | ((i & 0x08) >> 3)
        b = ((i & 0x01) << 1) | ((i & 0x10) >> 2) | ((i & 0x08) >> 3)
        out[i] = tuple(int(v / 7.0 * MAXI + 0.5) for v in (r, g, b))
    return out


def screen(path):
    """A screenshot as one colour INDEX a pixel, which is what the model gives."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    sx, sy = w // W, h // H
    if sx < 1 or sy < 1:
        sys.exit("%s is %dx%d: run SimCoupe with -visiblearea 0" % (path, w, h))
    a = np.asarray(im)[:H * sy:sy, :W * sx:sx]
    pal = palette()
    back = {}
    for i, v in enumerate(pal):
        back.setdefault(rgb_of_sam()[v], i)     # first index wins a colour
    out = np.zeros((H, W), np.int16)
    seen = {}
    for y in range(H):
        for x in range(W):
            k = tuple(int(v) for v in a[y, x])
            if k not in seen:
                seen[k] = back.get(k, -1)
            out[y, x] = seen[k]
    return out


def want(script, t):
    """The colour indices the model draws for frame t of the flight."""
    camx, camz, hz, px, py, pose, tk, tx, ty = script[t % len(script)]
    trees = [(tk[j], tx[j], ty[j]) for j in range(len(tk))]
    buf = bytes(C.frame(camx - 0x10000 if camx > 0x7FFF else camx,
                        camz, hz, px, py, pose, trees))
    a = np.frombuffer(buf, dtype=np.uint8).reshape(H, W // 2)
    out = np.empty((H, W), np.uint8)
    out[:, 0::2] = a >> 4
    out[:, 1::2] = a & 15
    return out


def same(got, w, pal):
    """How many pixels differ, colour for colour rather than index for index.

    Two palette entries can hold the same colour - the pilot's black and
    a shadow, say - and a screenshot cannot tell them apart, so the
    comparison is of what is SHOWN.
    """
    lut = np.array([pal[i] for i in range(16)], dtype=np.int16)
    return int(np.count_nonzero(lut[w] != np.where(got < 0, -1, lut[got])))


def timed(sbt, env, limit=400):
    """Run an image that halts, and return the wall seconds it took."""
    t0 = time.time()
    r = subprocess.run([SIMCOUPE, sbt, "-autoboot", "yes", "-sound", "no",
                        "-exitonhalt", "yes", "-visiblearea", "0",
                        "-filter", "no"],
                       env=env, timeout=limit,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode:
        sys.exit("SimCoupe returned %d on %s" % (r.returncode, sbt))
    return time.time() - t0


def host_speed(env, lo=250, hi=750):
    """How fast this host runs the emulator, as a fraction of real time.

    Two runs of `sam_tick.asm`, which counts display frames and halts.
    The difference is `hi - lo` frames of emulated time against however
    long the host took over them, with the boot and the load cancelling.
    """
    out = []
    for n in (lo, hi):
        sbt = "/tmp/tick%d.sbt" % n
        r = subprocess.run(["sjasmplus", "--raw=" + sbt, "-DDEMO_TICKS=%d" % n,
                            "-I" + ROOT, os.path.join(HERE, "sam_tick.asm")],
                           capture_output=True, text=True)
        if r.returncode:
            sys.exit(r.stdout + r.stderr)
        out.append(timed(sbt, env))
    return ((hi - lo) / PAL_HZ) / (out[1] - out[0])


def pace(env, n=200):
    """Seconds a frame, from two builds that stop after a known count."""
    from mksbt10 import build
    out = []
    for k in (1, n):
        sbt = "/tmp/chequer10_halt%d.sbt" % k
        build(sbt, quiet=True, defines={"DEMO_HALT": k, "DEMO_NOKEYS": 1})
        out.append(timed(sbt, env))
    return (out[1] - out[0]) / (n - 1)


def display():
    """An X display to run SimCoupe on, its own Xvfb if there is none."""
    env = dict(os.environ)
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    if env.get("DISPLAY"):
        return env, None
    env["DISPLAY"] = ":99"
    xvfb = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1024x768x24"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    time.sleep(2)
    return env, xvfb


def run(secs, outdir, env):
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        if f.endswith(".png"):
            os.remove(os.path.join(outdir, f))
    sbt = os.path.join(ROOT, "build", "chequer10.sbt")
    sim = subprocess.Popen(
        [SIMCOUPE, sbt, "-autoboot", "yes", "-sound", "no",
         "-visiblearea", "0", "-outpath", outdir],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shots, start = [], time.time()
    try:
        for s in secs:
            time.sleep(max(0, start + s - time.time()))
            subprocess.run(["xdotool", "mousemove", "100", "100"], env=env)
            subprocess.run(["xdotool", "key", "Print"], env=env)
            at = time.time() - start
            time.sleep(1.5)
            png = sorted(f for f in os.listdir(outdir) if f.endswith(".png"))
            if len(png) != len(shots) + 1:
                sys.exit("SimCoupe wrote no screenshot at %gs" % s)
            shots.append((at, os.path.join(outdir, png[-1])))
    finally:
        sim.terminate()
        sim.wait(timeout=10)
    return shots


def main():
    if not shutil.which(SIMCOUPE) and not os.path.exists(SIMCOUPE):
        sys.exit("no SimCoupe: set SIMCOUPE to the emulator binary")
    if not shutil.which("xdotool"):
        sys.exit("no xdotool, which is how the screenshot key is pressed")
    secs = [float(a) for a in sys.argv[1:]] or [LOAD + 8, LOAD + 20]

    from mksbt10 import build
    build(quiet=True)
    env, xvfb = display()
    try:
        shots = run(secs, "/tmp/simshot10", env)
        speed = host_speed(env)
        secs_a_frame = pace(env)
    finally:
        if xvfb:
            xvfb.terminate()

    script = flight()
    pal = palette()
    print()
    seen = []
    for at, png in shots:
        got = screen(png)
        best, bad = None, None
        for t in range(len(script)):
            n = same(got, want(script, t), pal)
            if bad is None or n < bad:
                best, bad = t, n
            if n == 0:
                break
        seen.append((at, best, bad))
        print("  %-16s %5.1fs in: frame %3d of the flight, %d pixels wrong"
              % (os.path.basename(png), at, best, bad))
    print()
    hz = 1.0 / secs_a_frame * (1.0 / speed if speed < 0.98 else 1.0)
    print("  %-40s %.0f%% of real time"
          % ("this host ran the emulator at", 100 * speed))
    print("  %-40s %.1f ms, so %.1f Hz"
          % ("a frame on the machine", 1000 * secs_a_frame, hz))
    print("  %-40s %.2f, and the path is stepped for %.1f"
          % ("display frames a frame", PAL_HZ / hz, RATE / 1))
    bad = sum(b for _, _, b in seen)
    print()
    print("ALL TESTS PASSED" if bad == 0 else "%d pixels differ" % bad)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
