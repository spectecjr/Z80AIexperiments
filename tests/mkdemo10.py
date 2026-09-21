#!/usr/bin/env python3
"""The palette and the flight path chequer10 runs on a machine.

    python3 tests/mkdemo10.py        # writes demo10data.z80s

The bench pokes the camera, the horizon, the pilot and the three tree
slots into the resident block for each frame and calls `cq10_frame`;
`tests/mkgif.py` does the same to record the GIF. On the machine
nothing is there to poke them, so the whole flight is a **table**:
seventeen bytes a frame, in the order the state sits in memory, played
by `demo10.z80s`.

That is not a shortcut around the work - it is the work moved. Where a
tree goes is a perspective division and a size decision, and the answer
is the same every time the demo runs, so it is worth 17 bytes rather
than a routine.

    camx, camz   2 bytes each, the camera
    hz           which horizon, 0 (tallest board) to 77
    px, py, pose the pilot
    tk, tx, ty   three bytes each, the tree slots: size, byte, row

THE RATE IS PART OF THE PATH. The camera's step is per frame, so a demo
that draws 20 frames a second has to move a quarter further each frame
than one drawing 25 to cover the same ground in the same time. RATE is
what the machine manages once contention is counted, and the path is
generated for it - see the note on DFRAMES below.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
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

import chequer10 as C10                            # noqa: E402
import jetpack as J                                # noqa: E402
from mkchqdata import sam                          # noqa: E402
from mkgif import corners                          # noqa: E402

# THE RATE IS A MEASUREMENT. `tests/test_sbt10.py` runs the shipped
# image and prices a frame through `tests/sam.py`'s contention model -
# the one `costs.md` §1b rests on - and a frame of this demo costs
# between 1.5 and 2.9 display frames depending on how much board the
# horizon is showing. The mean is about 2.5, so the path steps 2.5
# display frames' worth a frame and the ground goes past at the speed
# the GIF shows it at on average, judder and all.
DFRAMES = 2.5                   # display frames a frame, measured
RATE = 50.0 / DFRAMES           # so 20 frames a second
SECONDS = 10                    # one lap of the screen, and the table
NFRAMES = int(SECONDS * RATE)   # loops on it

FAR, NEAR = 6800, 650           # a tree's life, in depth
ACROSS = (-330, 310, -130, 250, -210, 150)      # and where it is planted


def palette():
    """The sixteen CLUT entries, which is mkgif's chequer10 palette.

    Nothing in this demo moves one: chequer9 gave up the fog gradient
    that chequer4's board had, and what that buys is a demo whose
    palette is set once and never touched again.
    """
    pal = [0] * 16
    for i, rgb in J.PAL.items():
        if i < 16:
            pal[i] = sam(*rgb)
    pal[1] = sam(7, 7, 5)               # the board's four sands, as two
    pal[2] = sam(6, 6, 4)               # pairs
    pal[10] = sam(5, 5, 3)
    pal[9] = sam(7, 5, 3)
    pal[13] = sam(2, 5, 2)              # the desert's green and its
    pal[14] = sam(4, 2, 0)              # shadow, which the tree uses too
    pal[15] = sam(2, 4, 4)              # and the sky
    return pal


def path(n=NFRAMES, rate=RATE):
    """Every frame of the flight: mkgif's `_chequer10`, as a list.

    The camera goes round the four corners of the screen behind the
    pilot, the horizon follows how high he is, and three trees are
    planted in the world ahead and grow through the eight sizes until
    their boxes no longer fit.
    """
    m = len(C10.HORIZONS)
    step = int(round(80 * 25 / rate))
    cam = []
    for t in range(n):
        fx, fy = corners(t / n, exact=True)
        cam.append((int((fx - 56) * 20),
                    min(m - 1, max(0, round((m - 1) * fy / 144))), fx, fy))
    out, last, sown = [], 56, 0
    trees = [(FAR - j * (FAR - NEAR) // C10.SLOTS, None)
             for j in range(C10.SLOTS)]
    for t in range(n):
        camx, hz, fx, fy = cam[t]
        camz = step * t
        px, py = round(fx), round(fy)
        for j, (d, x) in enumerate(trees):
            if x is None or d < NEAR:
                d = FAR if x is not None else d
                x = cam[min(n - 1, t + (d - NEAR) // step)][0] \
                    + ACROSS[sown % len(ACROSS)]
                sown += 1
                trees[j] = (d, x)
        here = []
        for d, x in trees:
            at = C10.place(hz, camx, camz, x, camz + d)
            here.append((d, at if at else (255, 0, 0)))
        here.sort(key=lambda p: -p[0])
        pose = 1 + (1 if px > last else -1 if px < last else 0)
        out.append((camx & 0xFFFF, camz & 0xFFFF, hz, px, py, pose,
                    [a[0] for _, a in here], [a[1] for _, a in here],
                    [a[2] for _, a in here]))
        last = px
        trees = [(d - step, x) for d, x in trees]
    return out


def script(frames):
    """The table as bytes: seventeen a frame, memory order."""
    out = bytearray()
    for camx, camz, hz, px, py, pose, tk, tx, ty in frames:
        out += camx.to_bytes(2, "little") + camz.to_bytes(2, "little")
        out += bytes([hz, px, py, pose]) + bytes(tk) + bytes(tx) + bytes(ty)
    return bytes(out)


def defb(vals, per=17):
    return "\n".join("        DEFB " + ", ".join(str(v) for v in vals[i:i + per])
                     for i in range(0, len(vals), per))


def main(path_out):
    frames = path()
    tab = script(frames)
    parts = [
        "; Generated by tests/mkdemo10.py - do not edit by hand.",
        "; The palette and the flight path, for demo10.z80s.",
        "\nDEMO_FRAMES:    EQU %d          ; frames of flight, and it loops"
        % len(frames),
        "DEMO_STEP:      EQU %d          ; world units of camz a frame, which"
        % int(round(80 * 25 / RATE)),
        "                                ; is %.1f display frames' worth"
        % DFRAMES,
        "\ndemo_pal:       ; the CLUT, entry 0 first - and never touched again\n"
        + defb(palette(), 16),
        "\ndemo_script:    ; camx, camz, hz, px, py, pose, tk*3, tx*3, ty*3\n"
        + defb(list(tab)),
        "demo_end:",
    ]
    open(path_out, "w").write("\n".join(parts) + "\n")
    print("wrote %s: %d frames, %d bytes of script, %.1f Hz, %.0f seconds"
          % (path_out, len(frames), len(tab), RATE, len(frames) / RATE))
    print("        horizons %d..%d, camz +%d a frame"
          % (min(f[2] for f in frames), max(f[2] for f in frames),
             int(round(80 * 25 / RATE))))


if __name__ == "__main__":
    root = os.path.dirname(HERE)
    main(os.path.join(root, "demo10data.z80s"))
