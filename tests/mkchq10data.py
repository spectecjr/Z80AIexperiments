#!/usr/bin/env python3
"""Generate chequer10's data: chequer9's board, and a tree to stand on it.

    python3 tests/mkchq10data.py

The board, the masks, the desert and the pilot are chequer9's and are
generated from chequer9's settings - a horizon that moves between 10%
of the screen and 50% of it, four colours on the board, a 24x48 pilot -
so this is mkchq9data.py with one more generator after it.

The tree goes in the page past the pilot's, which is where the map has
it: the chunks are laid out two pages at a time round the buffers, so
the eleventh chunk of chequer10's bank is page 24.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mkchq9data as C9                                 # noqa: E402

TREE = {"TREE_FIRST": "24"}     # past the pilot's pages in the map


def main():
    C9.main()
    env = dict(os.environ, **C9.VIEW, **TREE)
    r = subprocess.run([sys.executable, os.path.join(HERE, "mktree.py")],
                       env=env)
    if r.returncode:
        raise SystemExit("mktree.py failed")


if __name__ == "__main__":
    main()
