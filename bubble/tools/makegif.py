#!/usr/bin/env python3
"""
makegif.py - run the assembled prototype on the SAM emulator in tools/
and record what it actually draws as an animated GIF.

Nothing here reimplements the game: every pixel comes out of the real
MODE 4 framebuffer after the real Z80 code has rendered into it. The only
thing the host supplies is keypresses, because there is nobody at the
keyboard.

Run: python3 bubble/tools/makegif.py [seconds] [scale]
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PIL import Image                                          # noqa: E402
from sam import Machine                                        # noqa: E402

IMAGE = os.path.join(HERE, "..", "build", "bb.bin")
OUT = os.path.join(HERE, "..", "build", "bubble-bobble-sam.gif")

FPS = 50                                                       # SAM field rate
EVERY = 2                                                      # 25 fps in the GIF

# Keyboard rows as the prototype reads them: bb_read_input selects
# $DFFE (P O I U Y) and $7FFE (SPACE SYM M N B), active low.
ROW_POIUY, ROW_SPACE = 5, 7
K_RIGHT, K_LEFT = 0x01, 0x02                                   # P, O
K_JUMP, K_FIRE = 0x01, 0x04                                    # SPACE, M


def script(frame):
    """A plausible bit of play: pace the floor, fire on the move, and
    jump for the platforms now and then."""
    right = left = jump = fire = False
    phase = frame % 500

    if phase < 150:
        right = True
        fire = (phase % 40) < 6 and phase > 20
        jump = phase in (95, 96)
    elif phase < 190:
        jump = phase in (150, 151, 152)
        right = phase < 175
    elif phase < 330:
        left = True
        fire = (phase % 45) < 6
        jump = phase in (250, 251)
    elif phase < 380:
        fire = (phase % 30) < 8
    elif phase < 440:
        right = True
        jump = phase in (400, 401, 402)
    else:
        left = True
        fire = (phase % 35) < 5

    rows = [0xFF] * 9
    if left:
        rows[ROW_POIUY] &= ~K_LEFT & 0xFF
    if right:
        rows[ROW_POIUY] &= ~K_RIGHT & 0xFF
    if jump:
        rows[ROW_SPACE] &= ~K_JUMP & 0xFF
    if fire:
        rows[ROW_SPACE] &= ~K_FIRE & 0xFF
    return rows


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    scale = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    total = int(seconds * FPS)

    m = Machine(open(IMAGE, "rb").read())
    boot = m.boot()
    print("booted in %d instructions" % boot)

    pal = None
    frames = []
    t0 = time.time()
    instr = 0
    peak = 0
    for f in range(total):
        m.sam.keys = script(f)
        n = m.run_frame()
        instr += n
        peak = max(peak, n)
        if f % EVERY:
            continue
        if pal is None:
            pal = m.sam.palette()
        img = Image.frombytes("P", (256, 192), m.sam.framebuffer())
        img.putpalette(pal)
        if scale != 1:
            img = img.resize((256 * scale, 192 * scale), Image.NEAREST)
        frames.append(img)
        if len(frames) % 100 == 0:
            print("  %d/%d fields, %.0fs elapsed"
                  % (f, total, time.time() - t0))

    print("ran %d fields, %d instructions (%d mean, %d peak per field) in %.0fs"
          % (total, instr, instr // total, peak, time.time() - t0))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    frames[0].save(OUT, save_all=True, append_images=frames[1:],
                   duration=int(1000 * EVERY / FPS), loop=0,
                   optimize=True, disposal=1)
    print("wrote %s (%.1f MB, %d frames at %d ms)"
          % (os.path.normpath(OUT), os.path.getsize(OUT) / 1e6,
             len(frames), int(1000 * EVERY / FPS)))


if __name__ == "__main__":
    main()
