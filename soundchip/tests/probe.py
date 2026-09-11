#!/usr/bin/env python3
"""One line per register, rendered separately, so a person can say which
one is the tune.

    python3 tests/probe.py source.wav [start_seconds] [length_seconds]

`transcribe.track_viterbi` is called the "lead" tracker and it is nothing
of the kind: it follows the pitch with the strongest harmonic salience, and
in a real mix that is whichever part carries the most energy - usually
something in the middle. Asked for the top line of one recording it
returned a part centred on A4, G4 and D5, and the person who wrote the
recording said it was the bass and mids.

Nor is the melody the highest thing present: measured on the same
recording, the highest peak within 20 dB of the loudest sat at 2.3 to
5.9 kHz in every window tested, which is harmonics and cymbals.

So neither "loudest" nor "highest" finds a melody, and nothing in this
repo can tell which line a listener hears as the tune. What this does is
stop guessing: it tracks the best line in each of four registers, renders
each one alone on one channel, and leaves the question to whoever knows
the answer.
"""
import sys

import numpy as np

import arrange as A
import chiparr as C
import saa1099 as S
import transcribe as T

RATE = 50
BANDS = (("A", 200.0, 450.0), ("B", 420.0, 900.0),
         ("C", 850.0, 1700.0), ("D", 1600.0, 3200.0))
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(p):
    return "%s%d" % (NAMES[int(p) % 12], int(p) // 12 - 1)


def one_line(notes, n_frames, level=15, cap=2600.0,
             vib_cents=14.0, vib_frames=10, vib_after=8):
    """A note list alone on one channel, with the lead's own vibrato."""
    out = C.Out(n_frames)
    for start, length, pitch in notes:
        hz = C.midi_hz(pitch)
        while hz > cap:
            hz /= 2.0
        for k in range(length):
            i = start + k
            if not (0 <= i < out.n):
                continue
            f = hz
            if length >= vib_after and k >= vib_after:
                d = vib_cents * min(1.0, (k - vib_after) / float(vib_after))
                f = hz * 2 ** (d * np.sin(2 * np.pi * (k - vib_after)
                                          / vib_frames) / 1200.0)
            out.tone(1, i, f, level)
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip())
        return 2
    import soundfile as sf
    x, sr = sf.read(argv[1], dtype="float32")
    start = float(argv[2]) if len(argv) > 2 else 0.0
    secs = float(argv[3]) if len(argv) > 3 else 75.0
    x = x[int(start * sr):int((start + secs) * sr)]
    sf.write("/tmp/probe_source.wav", x, sr)
    mono = x.mean(axis=1) if x.ndim > 1 else x
    mag, fr = T.stft(mono, sr, 4096, sr // RATE)
    mag /= max(1e-12, mag.max())
    harm, _perc = T.hpss(mag)
    print("  %.0f s from %.0f s" % (secs, start))
    for tag, lo, hi in BANDS:
        f0 = T.track_viterbi(harm, fr, lo, hi)
        notes = T.legato(T.notes_of(f0, RATE, (0, 7), 3))
        if not notes:
            print("  %s  %4.0f-%4.0f Hz   nothing" % (tag, lo, hi))
            continue
        l = np.array([q for _s, q, _p in notes])
        p = np.array([q for _s, _l, q in notes])
        out = one_line(notes, len(harm))
        S.wav("/tmp/probe_%s.wav" % tag, A.render(out.registers(), RATE),
              mono=True)
        print("  %s  %4.0f-%4.0f Hz   %3d notes, median %.2f s, %s..%s, "
              "moves %.1f semitones a note  -> /tmp/probe_%s.wav"
              % (tag, lo, hi, len(notes), np.median(l) / float(RATE),
                 note_name(p.min()), note_name(p.max()),
                 np.abs(np.diff(p)).mean() if len(p) > 1 else 0.0, tag))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
