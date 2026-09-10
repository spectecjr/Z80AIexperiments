#!/usr/bin/env python3
"""A model of chequer4.z80s - harrier's floor with the depth stripes in
the pixels instead of in the palette.

harrier.z80s and chequer3.z80s draw the whole board in two colour
indices and leave the alternation into the distance to the palette: a
copper swaps what those two indices mean on every scanline where the
depth crosses a square boundary. That swap moves with camz, so it is a
table the CPU rebuilds every frame and a palette write every scanline -
and on a SAM the fill cannot even allow it, because it runs with
interrupts off and the stack pointing at the screen.

The alternation is a phase, though. Adding one whole square to the
horizontal phase exchanges the two colours on that scanline, which is
exactly what the palette swap did:

    1 + (((x - 128 + phi + p) // p) & 1)  ==  swap(1 + (((x - 128 + phi) // p) & 1))

so the board can carry its own stripes and the palette can sit still.
main() checks that identity over every width and every phase; the rest
of the file is harrier's screen with the swap applied where the parity
says, which is what chequer4.z80s draws.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harrier as HR

W, H, STRIDE = HR.W, HR.H, HR.STRIDE
HZ, S, HAZE = HR.HZ, HR.S, HR.HAZE
PTAB, ZTAB, TOP = HR.PTAB, HR.ZTAB, HR.TOP
WIDTHS = sorted(set(p for p in PTAB if p))
SWAP = 0x33                     # exchanges index 1 and 2 in both nibbles


def line(p, phi, par):
    """One scanline: the depth parity is a square of phase, not a palette."""
    out = bytearray(STRIDE)
    for x in range(W):
        c = 1 + ((((x - 128 + phi) // p) + par) & 1)
        if x & 1:
            out[x >> 1] |= c
        else:
            out[x >> 1] = c << 4
    return out


def frame(camx, camz):
    """The screen. There is no parity to hand out: it is in the pixels."""
    buf, par = HR.frame(camx, camz)
    for y in range(TOP, H):
        if par[y]:
            for i in range(y * STRIDE, (y + 1) * STRIDE):
                buf[i] ^= SWAP
    return buf


def main():
    bad = 0
    for p in WIDTHS:
        for phi in range(p):
            a = line(p, phi, 1)
            b = line(p, phi + p, 0)
            c = bytes(x ^ SWAP for x in line(p, phi, 0))
            if a != b or a != c:
                bad += 1
                print("p=%d phi=%d: a square of phase is not a swap" % (p, phi))
    print("  %-46s %d widths, %d phases"
          % ("a square of phase == exchanging the colours",
             len(WIDTHS), sum(WIDTHS)))
    n = same = 0
    for camx in range(0, 256, 7):
        got = frame(camx, 1234)
        want, par = HR.frame(camx, 1234)
        for y in range(TOP, H):
            row = got[y * STRIDE:(y + 1) * STRIDE]
            ref = want[y * STRIDE:(y + 1) * STRIDE]
            n += 1
            if row == ref:
                same += 1
            elif row != bytes(x ^ SWAP for x in ref) or not par[y]:
                bad += 1
    print("  %-46s %d of %d rows carry a swap"
          % ("and it is applied exactly where the parity was",
             n - same, n))
    print("\n%s" % ("ALL TESTS PASSED" if not bad else "FAILURES: %d" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
