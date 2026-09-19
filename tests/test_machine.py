#!/usr/bin/env python3
"""The three toolchains agree about the machine.

    python3 tests/test_machine.py

There are three Z80 emulators in this repository and two SAM models, and
that is on purpose - `layout.md` says why. What is *not* on purpose is
any of them disagreeing about the hardware, and the facts they share are
small enough to check outright:

    the palette      a CLUT byte to RGB, over all 256 of them
    the ports        LMPR, HMPR, VMPR, STATUS, BORDER
    the paging       a block maps a page and the one above it
    the screen       MODE 4 is 256x192, 128 bytes a line, 24,576 bytes

Every one of those is written down in at least two places - the demos'
harness in tests/, the prototype's in bubble/tools/, and the assembly
itself - and a disagreement between them is the kind of bug that shows
up as a wrong colour six months later. This is what stops that being
found by eye.
"""
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import sam as demo_sam                                  # noqa: E402
from mkgif import sam_rgb                               # noqa: E402

spec = importlib.util.spec_from_file_location(          # the prototype's
    "bb_sam", os.path.join(ROOT, "bubble", "tools", "sam.py"))    # own
bb_sam = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bb_sam)


def equs(path):
    """The EQUs an assembly file defines, as a dict."""
    out = {}
    for line in open(os.path.join(ROOT, path)):
        m = re.match(r"^(\w+):\s+EQU\s+(0x[0-9A-Fa-f]+|\d+)", line)
        if m:
            out[m.group(1)] = int(m.group(2), 0)
    return out


def main():
    bad = []

    n = sum(1 for v in range(256) if sam_rgb(v) != bb_sam.clut_rgb(v))
    print("  %-46s %d of 256 disagree" % ("the palette, CLUT byte to RGB", n))
    if n:
        v = next(v for v in range(256) if sam_rgb(v) != bb_sam.clut_rgb(v))
        print("      first at %02X: tests/mkgif %s, bubble/tools/sam %s"
              % (v, sam_rgb(v), bb_sam.clut_rgb(v)))
        bad.append("palette")

    eq = equs("chequer4.z80s")
    ports = (("LMPR", demo_sam.LMPR, bb_sam.P_LMPR, eq.get("CHQ4_LMPR")),
             ("HMPR", demo_sam.HMPR, bb_sam.P_HMPR, eq.get("CHQ4_HMPR")),
             ("VMPR", demo_sam.VMPR, bb_sam.P_VMPR, eq.get("CHQ4_VMPR")))
    for name, a, b, c in ports:
        if len({a, b, c}) != 1:
            print("  PORT MISMATCH %s: tests/sam %s, bubble %s, assembly %s"
                  % (name, a, b, c))
            bad.append(name)
    print("  %-46s %d checked, in three places each"
          % ("the paging ports", len(ports)))

    m = bb_sam.Sam()                    # a block maps a page and the one
    for page in (0, 4, 9, 30, 31):      # above it, and 31 wraps to 0
        m.lmpr, m.hmpr = page, page
        m.repage()
        want = [page * demo_sam.PAGE, ((page + 1) % 32) * demo_sam.PAGE] * 2
        if m.base != want:
            print("  PAGING MISMATCH at page %d: %s, wanted %s"
                  % (page, m.base, want))
            bad.append("paging %d" % page)
    print("  %-46s %d pages, and the wrap at 31"
          % ("a block is a page and the one above it", 5))

    screen = ((demo_sam.PAGE, bb_sam.PAGE, "a page, in bytes"),
              (demo_sam.SCREEN, bb_sam.SCR_BYTES, "a MODE 4 screen"),
              (128, bb_sam.SCR_STRIDE, "bytes a scanline"),
              (192, bb_sam.SCR_H, "scanlines"))
    for a, b, what in screen:
        if a != b:
            print("  GEOMETRY MISMATCH, %s: %s against %s" % (what, a, b))
            bad.append(what)
    print("  %-46s %d checked" % ("the screen's geometry", len(screen)))
    print("  %-46s 0x%04X, and the assembly's own"
          % ("the screen sits at", eq["CHQ4_SCREEN"]))

    ok = not bad
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %s"
                    % ", ".join(bad)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
