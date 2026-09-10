#!/usr/bin/env python3
"""Generate thunderdata.z80s - distant thunder alone, both layers of it.

    python3 tests/mkthunderdata.py

The same two-layer engine storm.z80s plays; only the score differs, so
this writes the same symbols and only one of the two data files goes
into a build.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thunder as T
from mkstormdata import emit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    emit(T.L0, T.L1, os.path.join(ROOT, "thunderdata.z80s"),
         "Distant thunder alone: the body underneath, the gravel over it.",
         "mkthunderdata.py")
