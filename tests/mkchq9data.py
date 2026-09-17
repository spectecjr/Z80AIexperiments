#!/usr/bin/env python3
"""Generate chequer9's board: one bank for every horizon it can have.

    python3 tests/mkchq9data.py

chequer8's horizon is row 114 and stays there. chequer9's moves between
row 114 and row 77 - 40% of the screen to 59% - so its tables are
generated from the *deepest* board it can ever have, the one whose
horizon is at row 76, and every shallower board is a piece of the same
tables:

    the bands       a square's width at row y is
                    round(S * (y - horizon) / CAMH), a function of the
                    row's distance from the horizon and nothing else,
                    so one band table serves every horizon - a taller
                    board starts further down it
    the runs        a function of a square's width, as they always were
    the masks       a scanline's depth is CAMH * FOCAL / (y - horizon),
                    the same function of the same distance: 128 rows
                    deep now rather than 77, and copied as far as the
                    horizon says
    the horizons    which of the 39 rows in the range are allowed, and
                    where each one enters the band table

The widest square goes to 96 pixels rather than 64, because pitching
the horizon up brings coarser ground into view: 4,656 compiled bodies
in six chunks against chequer8's 2,080 in three, which is the price of
a horizon that moves and is paid in memory.

The desert and the pilot come out of here too, because they have to
agree with the board about the viewport and about which pages are
spare: the band is 20 scanlines rather than chequer8's 32, which is
what buys the tall board its budget, and both of them sit past the
board's six chunks in the map.

The generators take all of that from the environment, so this is four
subprocesses and no duplicated code.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VIEW = {"HARRIER_HZ": "76",     # the deepest board: 115 scanlines, of
        "HARRIER_CAMH": "308",  # which 114 are ever drawn, and squares
        "HARRIER_MINP": "1",    # up to 96 pixels wide at the bottom
        "CHQ_SET": "9"}
SAND = {"DESERT_ROWS": "20",    # a shorter band than chequer8's, so that
        "DESERT_SET": "9",      # the tallest board still fits the frame,
        "DESERT_FIRST": "20"}   # and past the board's chunks in the map


def main():
    for script, extra in (("mkchq4data.py", {}), ("mkchq5body.py", {}),
                          ("mkdesertdata.py", SAND), ("mkjetmove.py", {})):
        env = dict(os.environ, **VIEW, **extra)
        r = subprocess.run([sys.executable, os.path.join(HERE, script)],
                           env=env)
        if r.returncode:
            raise SystemExit("%s failed" % script)


if __name__ == "__main__":
    main()
