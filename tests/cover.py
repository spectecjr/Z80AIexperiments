#!/usr/bin/env python3
"""How much of a recording an arrangement of it actually covers.

    python3 tests/cover.py source.wav arrangement.log

"Too thin" is a judgement, and it was the right one twice about
`chiparr.py`. This turns it into a number, so the next change to the
arranger can be argued about with measurements instead of adjectives.

The number: of the strong spectral peaks in the source between 200 Hz and
2.5 kHz - strong meaning within 12 dB of the loudest peak in that band in
that frame - what fraction has some sounding chip voice within 60 cents of
it. The chip's voices count their ODD HARMONICS as well as their
fundamentals, because a square wave really does produce them and a source
peak at 3f really is covered by a voice at f.

Measured with it, on a 197 s recording reduced to six channels:

    parts that yield to each other      37.6%
    parts that never yield              57.8%

The ceiling is set by the channel count: five tone voices against a median
of six strong partials a frame, some of which are a reverb tail or a
cymbal that no square wave stands in for.
"""
import sys

import numpy as np
import soundfile as sf

import saareg

LO, HI = 200.0, 2500.0
REL = 0.25                      # a peak counts if it is within 12 dB of
ODD = (1, 3, 5, 7, 9)           # the frame's loudest peak in the band


def source_peaks(path, rate=50, lo=LO, hi=HI, rel=REL, n_fft=4096):
    """The strong peaks of each frame of the source, in Hz."""
    x, sr = sf.read(path, dtype="float32")
    m = x.mean(axis=1) if x.ndim > 1 else x
    hop = sr // rate
    w = np.hanning(n_fft)
    fr = np.fft.rfftfreq(n_fft, 1.0 / sr)
    a, b = int(np.searchsorted(fr, lo)), int(np.searchsorted(fr, hi))
    out = []
    for i in range(0, len(m) - n_fft, hop):
        S = np.abs(np.fft.rfft(m[i:i + n_fft] * w))[a:b]
        if not S.size:
            break
        t = rel * S.max()
        out.append([fr[a + j] for j in range(2, len(S) - 2)
                    if S[j] == max(S[j - 2:j + 3]) and S[j] > t])
    return out


def coverage(peaks, logpath, cents=60.0, harmonics=ODD):
    """Of those peaks, how many a sounding chip voice stands within."""
    frames, _hz = saareg.read_log(logpath)
    snaps = saareg.decode(frames)
    hit = tot = 0
    for i, pk in enumerate(peaks):
        if i >= len(snaps):
            break
        s = snaps[i]
        base = [c["hz"] for c in s["ch"]
                if c["tone"] and s["enabled"] and max(c["amp"]) > 0
                and c["hz"] > 0]
        vs = [f * h for f in base for h in harmonics]
        for f in pk:
            tot += 1
            if any(abs(1200 * np.log2(v / f)) < cents for v in vs):
                hit += 1
    return hit, tot


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip())
        return 2
    hit, tot = coverage(source_peaks(argv[1]), argv[2])
    print("  %-34s %d of %d  =  %.1f%%"
          % ("peaks covered within 60 cents", hit, tot,
             100.0 * hit / max(1, tot)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
