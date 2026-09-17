#!/usr/bin/env python3
"""Generate chequer8's board: the same routine over a viewport of its own.

    python3 tests/mkchq8data.py

chequer5's board is the bottom half of the screen, because its camera
puts the horizon at row 96. chequer8 wants the bottom 40% - more sky for
the desert to stand in - so it has a viewport of its own: the horizon at
row 114 and the camera 308 world units up rather than 380, which keeps a
square 64 pixels wide at the bottom of the screen where chequer5 has it.
77 scanlines of board, still drawn all the way down to one pixel
squares.

Nothing about the routine changes; the tables do. The run bank is the
same runs - a run is a function of a square's width and nothing else -
but the bands, the compiled bodies, the swap masks and the viewport
constants all come out different, so they are generated into a set of
their own: chequer8equ, chequer8msk0/1, chequer8c0/1/2.

The generators take the viewport from the environment, so this is three
subprocesses and no duplicated code.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VIEW = {"HARRIER_HZ": "114",    # the horizon: 77 rows of board, 40% of
        "HARRIER_CAMH": "308",  # the screen, and 64 pixels a square at
        "HARRIER_MINP": "1",    # the bottom of it
        "CHQ_SET": "8"}


def main():
    env = dict(os.environ, **VIEW)
    for script in ("mkchq4data.py", "mkchq5body.py"):
        r = subprocess.run([sys.executable, os.path.join(HERE, script)],
                           env=env)
        if r.returncode:
            raise SystemExit("%s failed" % script)


if __name__ == "__main__":
    main()
