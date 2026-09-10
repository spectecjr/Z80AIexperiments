#!/usr/bin/env python3
"""Check the arranger on material whose right answer is known.

    python3 tests/test_arrange.py

A synthetic source with four sections - one tone, another tone, two at
once, then noise - and the arranger has to find them: the right
frequencies within a semitone, noise where the noise is, silence where
there is silence. Then the register log it produced is read back with
chipdis.py, which is the round trip: audio in, registers out, and the
disassembler recovers the notes that went in.
"""
import math
import sys

import numpy as np

import arrange as A
import chipdis
import saa1099 as S
import saareg

SR = 44100
A4, E5, CS5 = 440.0, 659.26, 554.37


def source():
    """Four sections of half a second, then silence."""
    n = int(0.5 * SR)
    t = np.arange(n) / float(SR)
    fade = np.minimum(1.0, np.minimum(t, 0.5 - t) * 200)
    parts = [np.sin(2 * np.pi * A4 * t) * fade,
             np.sin(2 * np.pi * E5 * t) * fade,
             (np.sin(2 * np.pi * A4 * t) + np.sin(2 * np.pi * CS5 * t))
             * 0.5 * fade,
             np.random.RandomState(3).randn(n) * 0.3 * fade,
             np.zeros(n)]
    x = np.concatenate(parts) * 0.8
    return np.stack([x, x], axis=1)


def main():
    bad = 0
    x = source()
    mono = x[:, 0]
    ed = A.band_edges()
    bank = A.Bank(ed)
    rate = 50
    unit = A.calibrate(bank, ed, rate)
    frames, chosen, info = A.arrange(x, SR, rate, 6, ed, bank, unit)
    print("  %-34s %d frames, %.1f register writes a frame"
          % ("arranged", len(frames),
             sum(len(f) for f in frames) / float(len(frames))))

    def section(i):
        """The atoms chosen in the middle of section i."""
        lo = int((i * 0.5 + 0.15) * rate)
        hi = int((i * 0.5 + 0.35) * rate)
        out = []
        for k in range(lo, min(hi, len(chosen))):
            out += chosen[k]
        return out

    def loudest(atoms, kind="tone"):
        best = None
        for a, lv in atoms:
            if bank.kind[a] == kind and (best is None or lv > best[1]):
                best = (a, lv)
        return best

    for i, want in ((0, A4), (1, E5)):
        got = loudest(section(i))
        f = bank.hz[got[0]] if got else 0
        off = 1200 * math.log(f / want, 2) if f else 999
        ok = abs(off) < 100
        bad += 0 if ok else 1
        print("    %s section %d: loudest atom %.1f Hz, wanted %.1f (%+.0f cents)"
              % ("ok " if ok else "BAD", i, f, want, off))

    # both tones at once, and the arranger should have found both
    both = section(2)
    hz = sorted(set(round(float(bank.hz[a])) for a, _ in both
                    if bank.kind[a] == "tone"))
    near = lambda w: any(abs(1200 * math.log(h / w, 2)) < 100 for h in hz)
    ok = near(A4) and near(CS5)
    bad += 0 if ok else 1
    print("    %s section 2: found both %.0f and %.0f in %s"
          % ("ok " if ok else "BAD", A4, CS5, hz[:6]))

    # noise where the noise is
    nz = [lv for a, lv in section(3) if bank.kind[a] != "tone"]
    ok = bool(nz) and max(nz) >= 4
    bad += 0 if ok else 1
    print("    %s section 3: noise atoms at levels %s"
          % ("ok " if ok else "BAD", sorted(nz, reverse=True)[:4]))

    # and nothing in the silence
    quiet = section(4)
    ok = not quiet
    bad += 0 if ok else 1
    print("    %s section 4: %d atoms in the silence"
          % ("ok " if ok else "BAD", len(quiet)))

    # the round trip: read the log back and see the notes come out
    saareg.write_log("/tmp/arrange_rt.sreg", frames, rate)
    back, hz_back = saareg.read_log("/tmp/arrange_rt.sreg")
    tracks, chip = saareg.tracks(back)
    an = chipdis.analyse(tracks, hz_back, chip)
    names = set()
    for c in an["channels"]:
        for nt in c["notes"]:
            if nt.frames >= 4:
                names.add(chipdis.note_name(nt.median_hz())[0])
    ok = "A4" in names and "E5" in names
    bad += 0 if ok else 1
    print("    %s round trip: chipdis reads back %s"
          % ("ok " if ok else "BAD",
             " ".join(sorted(names)[:10])))

    # and it should sound like the source, in the band domain
    out = A.render(frames, rate)
    c = A.compare(mono, out.mean(axis=1), SR, rate, ed)
    ok = c["dB_median"] < 9.0
    bad += 0 if ok else 1
    print("    %s %.2f dB median band error" % ("ok " if ok else "BAD",
                                                c["dB_median"]))

    print()
    print("  %-46s %d" % ("checks that failed", bad))
    print("\n%s" % ("ALL TESTS PASSED" if not bad else "FAILURES: %d" % bad))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
