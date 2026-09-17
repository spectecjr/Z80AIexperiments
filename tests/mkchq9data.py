#!/usr/bin/env python3
"""Generate chequer9's board: one bank for every horizon it can have.

    python3 tests/mkchq9data.py

chequer8's horizon is row 114 and stays there. chequer9's moves between
row 172 and row 95 - the board taking 10% of the screen to 50% of it -
so its tables are generated from the *deepest* board it can ever have,
the one whose horizon is at row 95, and every shallower board is a
piece of the same tables:

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

The widest square goes to 80 pixels rather than 64, because pitching
the horizon up brings coarser ground into view - the board is half the
screen at its tallest. That is what a horizon that moves costs, and it
is paid in memory rather than in T-states.

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
VIEW = {"HARRIER_HZ": "95",     # the deepest board: 96 scanlines, half
        "HARRIER_CAMH": "308",  # the screen, and squares up to 80 pixels
        "HARRIER_MINP": "1",    # wide at the bottom of it
        "CHQ_SET": "9",
        "CHQ_ROWS0": "19",      # and the range of boards a horizon may
        "CHQ_ROWS1": "96",      # give: 10% of the screen to 50%
        "CHQ_DYNHZ": "1",       # every one of which gets a band list
        "CHQ_SWAP": "0xBB",     # four colours on the board: what
                                # exchanges its two carries a third bit,
                                # so the odd rows of squares come out in a
                                # darker pair
        "HARRIER_SKY": "15"}    # and a flat sky, in an index of its own:
                                # nothing in this demo changes a palette
                                # entry by scanline, because a SAM
                                # services those with a line interrupt
SAND = {"DESERT_ROWS": "20",    # a shorter band than chequer8's, so that
        "DESERT_SET": "9",      # the tallest board still fits the frame,
        "DESERT_FIRST": "18",   # and past the board's chunks in the map
        "DESERT_SKY": "15",     # with a flat sky, in an index of its own
        "DESERT_PAL": "board4"} # and its sand out of the board's own four
JET = {"JET_FIRST": "22",       # the pilot goes past the desert's, and
       "JET_W": "24",           # is 24x48 here rather than the 32x96 the
       "JET_H": "48",           # demos with a pilot who stands still use
       "JET_PAL": "board4"}     # and gives up a grey for the board's
                                # second pair


def main():
    for script, extra in (("mkchq4data.py", {}), ("mkchq5body.py", {}),
                          ("mkdesertdata.py", SAND),
                          ("mkjetmove.py", JET)):
        env = dict(os.environ, **VIEW, **extra)
        r = subprocess.run([sys.executable, os.path.join(HERE, script)],
                           env=env)
        if r.returncode:
            raise SystemExit("%s failed" % script)


if __name__ == "__main__":
    main()
