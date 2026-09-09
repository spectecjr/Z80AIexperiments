#!/usr/bin/env python3
"""A model of chequer3.z80s - the Space Harrier floor, both exact.

chequer2.z80s draws a scanline as one compiled run of PUSHes with the
phase exact to the pixel, but a square's width is still a whole number
of PUSHes, so the board's vertical edges come out as staircases.
harrier.z80s puts both on the pixel and pays a dispatch per square.

This draws harrier's screen, bit for bit, out of compiled runs: one
run per square width per odd pixel of phase, entered where the phase
says. Three things buy that:

  the entry     the phase runs 0..p-1 and a PUSH is four pixels, so
                k = phase >> 2 picks where in the run to start and
                needs no wrapping at all

  the stack     the two remaining pixels of phase are one byte, so
                starting SP one byte down the row shifts the whole run
                two pixels and halves the number of runs

  six values    a run pushes one of BC, DE, HL, AF, IX and IY - two
                colours and up to four boundaries, which is what an
                odd width needs, since its boundaries walk through all
                four offsets inside a PUSH
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harrier as HR

W, H, STRIDE = HR.W, HR.H, HR.STRIDE
HZ, S, HAZE = HR.HZ, HR.S, HR.HAZE
PTAB, ZTAB, TOP = HR.PTAB, HR.ZTAB, HR.TOP
WIDTHS = sorted(set(p for p in PTAB if p))


def kmax(p):
    """How many PUSHes of phase a run has to hold: 0 <= phase < p."""
    return ((p - 1) >> 2) + 1


def runlen(p):
    return kmax(p) + 63


def pattern(p, t):
    """The run for a square p wide at phase t: four pixels a PUSH.

    Entered k from its head, PUSH j covers the four pixels whose
    (x - 128 + phase) are 4*(N - j - 1) + t and the three after it,
    with N picked so that k = kmax - 1 - (phase >> 2) is always in the
    run - that is what makes the entry a subtraction and not a modulo.
    """
    n = kmax(p) + 31
    return [[1 + ((((4 * (n - j - 1) + t + q)) // p) & 1) for q in range(4)]
            for j in range(runlen(p))]


def entry(p, camx):
    """Where this camera enters the run: (PUSH, run, stack shift)."""
    phi = ((camx % S) * p) // S
    return kmax(p) - 1 - (phi >> 2), phi & 1, (phi >> 1) & 1


def edge(p, phi):
    """The row's last byte, which a shifted run does not reach."""
    return ((1 + (((126 + phi) // p) & 1)) << 4) | (1 + (((127 + phi) // p) & 1))


def line(p, k, t, s):
    """One scanline as 128 MODE 4 bytes."""
    pat = pattern(p, t)
    out = bytearray(STRIDE)
    for m in range(64):
        px = pat[k + m]
        b = 126 - 2 * m - s
        if b >= 0:
            out[b] = (px[0] << 4) | px[1]
        out[b + 1] = (px[2] << 4) | px[3]
    return out


def frame(camx, camz):
    """The screen, and the parity the copper flips the palette by."""
    buf = bytearray(b"\x11" * (STRIDE * H))
    for y in range(HZ + 1, TOP):
        buf[y * STRIDE:(y + 1) * STRIDE] = bytes([HAZE * 0x11]) * STRIDE
    par = [0] * H
    for y in range(HZ + 1, H):
        par[y] = ((ZTAB[y] + camz) >> 8) & 1
        p = PTAB[y]
        if p:
            k, t, s = entry(p, camx)
            row = line(p, k, t, s)
            if s:
                row[STRIDE - 1] = edge(p, ((camx % S) * p) // S)
            buf[y * STRIDE:(y + 1) * STRIDE] = row
    return buf, par


def main():
    bad = 0
    for camx in range(0, 1024, 7):
        for camz in (0, 1234):
            got, gpar = frame(camx, camz)
            want, wpar = HR.frame(camx, camz)
            if got != want:
                d = [i for i in range(len(want)) if got[i] != want[i]]
                print("camx %d: %d bytes differ, first %d (y=%d x=%d)"
                      % (camx, len(d), d[0], d[0] // STRIDE,
                         (d[0] % STRIDE) * 2))
                bad += 1
            if gpar != wpar:
                print("camx %d: parity differs" % camx)
                bad += 1
    print("%d runs, %d bytes of pattern"
          % (2 * len(WIDTHS), sum(2 * runlen(p) for p in WIDTHS)))
    print("chequer3 against harrier: %s" % ("MISMATCH" if bad else "identical"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
