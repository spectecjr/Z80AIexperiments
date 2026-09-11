#!/usr/bin/env python3
"""Two register logs against the score they are both meant to be playing.

    python3 tests/versus.py score.mid a.log b.log

An arrangement made from audio and one made from the score can be compared
directly, because the score says what either of them ought to contain. Per
20 ms frame it asks two questions of each:

    recall     of the pitches the score has sounding, how many does the
               arrangement play - exactly, or in some octave
    precision  of the pitches the arrangement plays, how many are in the
               score at all - exactly, or in some octave

Recall says what is missing. Precision says what is invented, and that is
the number an audio-driven arrangement tends to fail: a tracker reports
partials of notes as though they were notes, and they go on a channel.
"""
import sys

import numpy as np

import saareg
import smf

RATE = 50
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(p):
    return "%s%d" % (NAMES[int(p) % 12], int(p) // 12 - 1)


def to_midi(hz):
    return 69 + 12 * np.log2(hz / 440.0) if hz > 0 else 0.0


def score_rolls(tracks, n, rate=RATE, offset=0.0):
    """Every pitch sounding a frame, and the same per named part."""
    whole = [set() for _ in range(n)]
    parts = {}
    for t in tracks:
        if not t.notes or 9 in t.channels:
            continue
        rows = [set() for _ in range(n)]
        for q in t.notes:
            a = int(round((q.start + offset) * rate))
            b = max(a + 1, int(round((q.end + offset) * rate)))
            for i in range(max(0, a), min(n, b)):
                rows[i].add(q.pitch)
                whole[i].add(q.pitch)
        parts[t.name or "track %d" % t.index] = rows
    return whole, parts


def log_rolls(path, n):
    """Every pitch a log sounds a frame, and per channel."""
    frames, _hz = saareg.read_log(path)
    snaps = saareg.decode(frames)
    whole = [set() for _ in range(n)]
    per = [[set() for _ in range(n)] for _ in range(6)]
    for i in range(min(n, len(snaps))):
        s = snaps[i]
        for c in range(6):
            ch = s["ch"][c]
            if ch["tone"] and s["enabled"] and max(ch["amp"]) > 0 \
                    and ch["hz"] > 0:
                p = int(round(to_midi(ch["hz"])))
                whole[i].add(p)
                per[c][i].add(p)
    return whole, per


def match(a, b, octave=False):
    """How many of a are in b, and how many of a there are."""
    if octave:
        b = set(q % 12 for q in b)
        return sum(1 for q in a if q % 12 in b), len(a)
    return sum(1 for q in a if q in b), len(a)


def compare(truth, got):
    n = min(len(truth), len(got))
    rh = rt = ph = pt = rho = pho = 0
    for i in range(n):
        h, t = match(truth[i], got[i]); rh += h; rt += t
        h, _ = match(truth[i], got[i], True); rho += h
        h, t = match(got[i], truth[i]); ph += h; pt += t
        h, _ = match(got[i], truth[i], True); pho += h
    return {"recall": rh / max(1, rt), "recall_oct": rho / max(1, rt),
            "precision": ph / max(1, pt), "precision_oct": pho / max(1, pt),
            "played": pt / max(1, n), "wanted": rt / max(1, n)}


def main(argv):
    if len(argv) < 4:
        print(__doc__.strip())
        return 2
    tracks, _tpb, _tempos, _sigs = smf.read(argv[1])
    n = int(max(q.end for t in tracks for q in t.notes) * RATE) + RATE
    whole, parts = score_rolls(tracks, n)
    logs = [(argv[i], log_rolls(argv[i], n)) for i in (2, 3)]

    print("  the score sounds %.2f pitches a frame"
          % (sum(len(s) for s in whole) / float(n)))
    print()
    print("  %-22s %7s %8s %8s %9s %9s"
          % ("", "plays", "recall", "+octave", "precision", "+octave"))
    for name, (got, _per) in logs:
        r = compare(whole, got)
        print("  %-22s %6.2f %7.0f%% %7.0f%% %8.0f%% %8.0f%%"
              % (name.split("/")[-1], r["played"], 100 * r["recall"],
                 100 * r["recall_oct"], 100 * r["precision"],
                 100 * r["precision_oct"]))

    print()
    print("  by part, how much of it each arrangement plays (any octave)")
    print("  %-20s %10s %10s" % ("", logs[0][0].split("/")[-1],
                                 logs[1][0].split("/")[-1]))
    for pname, rows in sorted(parts.items(),
                              key=lambda kv: -sum(len(s) for s in kv[1])):
        line = "  %-20s" % pname[:20]
        for _name, (got, _per) in logs:
            r = compare(rows, got)
            line += " %9.0f%%" % (100 * r["recall_oct"])
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
