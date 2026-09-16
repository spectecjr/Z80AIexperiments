#!/usr/bin/env python3
"""A model of chequer8: the same picture as chequer7, drawn differently.

Board, then the city over the sixteen rows above it, then the pilot over
both - which is chequer7's model exactly, and deliberately so: chequer8
changes how the pilot gets onto the screen, not what he looks like, so
the model it is checked against is the one that was already right.

What is different is underneath. chequer7 draws the pilot's top half
once per buffer and plays the rest from a stream; chequer8 draws all 96
rows of him every frame, from compiled code in a page of its own.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["HARRIER_MINP"] = "1"

from chequer7 import frame, W, H, STRIDE, TOP, PTAB     # noqa: F401,E402
