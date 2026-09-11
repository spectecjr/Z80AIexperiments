#!/usr/bin/env python3
"""Check the part-based arranger: transcribe.py then chiparr.py.

    python3 tests/test_chiparr.py

arrange.py matches a spectrum. This path does something different: it
decides what the PARTS are - bass, lead, chords, drums - and plays those
on six channels. So the checks are musical, not spectral: the tempo, the
bass's actual notes, the key, whether the drums land on the grid, and
whether each channel ends up carrying the part it was given.

The source is mkdemosource.build(), an original cue at 96 bpm in D minor
whose every part is known, so each answer can be compared with the truth
rather than with taste. The last section checks two pitch trackers on
signals built to break them, including the one case that DID break the
bass tracker on real music: a note whose fundamental is 18 dB below its
second harmonic.
"""
import sys

import numpy as np

import chipdis
import chiparr as C
import mkdemosource
import saa1099 as S
import saareg
import transcribe as T

SR = 44100
RATE = 50
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_of(hz):
    m = int(round(69 + 12 * np.log2(hz / 440.0)))
    return "%s%d" % (NAMES[m % 12], m // 12 - 1)


def check(what, got, want, ok):
    print("  %-42s %-22s %s" % (what, got, "ok" if ok else "WANT " + want))
    return 0 if ok else 1


def partial(f, harmonics, n):
    """A tone built from named harmonics at named amplitudes."""
    t = np.arange(n) / float(SR)
    out = np.zeros(n)
    for h, a in harmonics:
        out += a * np.sin(2 * np.pi * f * h * t)
    return out


def trackers():
    """The two pitch trackers, on signals designed to fool them."""
    bad = 0
    n = SR * 3

    # a bass whose fundamental is 18 dB down on its second harmonic: this
    # is what a mix sounds like after the sub has been rolled off, and it
    # is what made the old autocorrelation tracker read C2 as C3
    x = partial(65.41, [(1, 0.125), (2, 1.0), (3, 0.26), (4, 0.65)], n)
    f = [v for v in T.track_bass(x, SR, RATE) if v > 0]
    got = float(np.median(f)) if f else 0.0
    bad += check("weak fundamental, strong 2nd harmonic",
                 "%.1f Hz %s" % (got, note_of(got) if got else "-"),
                 "65.4 Hz C2", got and abs(1200 * np.log2(got / 65.41)) < 50)

    # and the other direction: nothing below the note, so nothing may be
    # invented below it either
    x = partial(98.0, [(1, 1.0), (2, 0.5), (3, 0.33)], n)
    f = [v for v in T.track_bass(x, SR, RATE) if v > 0]
    got = float(np.median(f)) if f else 0.0
    bad += check("a plain sawtooth bass",
                 "%.1f Hz %s" % (got, note_of(got) if got else "-"),
                 "98.0 Hz G2", got and abs(1200 * np.log2(got / 98.0)) < 50)

    # silence must not produce a pitch
    f = [v for v in T.track_bass(np.zeros(n), SR, RATE) if v > 0]
    bad += check("silence", "%d voiced frames" % len(f), "0", len(f) == 0)
    return bad


def main():
    bad = 0
    print("  THE TRACKERS")
    bad += trackers()

    print()
    print("  THE CUE   (96 bpm, D minor, parts known)")
    x = mkdemosource.build()
    sc = T.transcribe(x, SR, RATE)

    bad += check("tempo", "%.1f bpm" % sc["bpm"], "96 bpm",
                 abs(sc["bpm"] - 96.0) < 4.0)

    # The cue's bass is a saw at D2 over a sine an octave below it, so D1
    # and D2 are both right answers about the note and the tracker may give
    # either - what must never happen is a different PITCH CLASS. (It gave
    # E1 once, two semitones out, because the candidate grid's floor sat at
    # 40 Hz and the octave search piled up against it.)
    bb = [T.from_midi(p) for _s, _l, p in sc["bass"]]
    med = float(np.median(bb)) if bb else 0.0
    cents = 1200 * np.log2(med / 36.71) if med else 999
    bad += check("bass note", "%.1f Hz %s" % (med, note_of(med) if med else "-"),
                 "D, at D1 or D2", med and min(abs(cents), abs(cents - 1200)) < 60)
    cover = sum(l for _s, l, _p in sc["bass"]) / float(sc["frames"])
    bad += check("bass covers the cue", "%.0f%% of frames" % (100 * cover),
                 "over 40%", cover > 0.40)

    # the cue's lead is D4 F4 A4 G4 F4 D4 C5 A4, twice
    want = ["D", "F", "A", "G", "F", "D", "C", "A"]
    got = [NAMES[int(round(p)) % 12] for _s, _l, p in sc["lead"]]
    run = any(got[i:i + 8] == want for i in range(max(0, len(got) - 7)))
    bad += check("the lead's motif, in order", " ".join(got[:10]),
                 " ".join(want), run)

    # the cue is in D minor, so the chord holding the most frames must be
    # D minor and every root found must be a degree of that scale. (Bb and
    # G both turn up for one window each, and both are diatonic: Bb is the
    # sixth, and the cue's last two bars really do put a G in the pad.)
    weight = {}
    for _s, l, r, k in sc["chords"]:
        weight[NAMES[r] + k] = weight.get(NAMES[r] + k, 0) + l
    top_chord = max(weight, key=weight.get)
    bad += check("the chord holding the most frames", top_chord, "Dm",
                 top_chord == "Dm")
    scale = {"D", "E", "F", "G", "A", "A#", "C"}
    roots = set(NAMES[r] for _s, _l, r, _k in sc["chords"])
    bad += check("every root is a degree of D minor", " ".join(sorted(roots)),
                 "inside " + " ".join(sorted(scale)), roots <= scale)

    off, step = sc["grid"]
    ongrid = sum(1 for i, _k, _v in sc["drums"] if (i - off) % step == 0)
    bad += check("drum hits on the sixteenth grid",
                 "%d of %d" % (ongrid, len(sc["drums"])), "all of them",
                 ongrid == len(sc["drums"]))

    # folding: the tracker's octave choices are not a melody's octaves
    raw = [p for _s, _l, p in sc["lead"]]
    fold = [p for _s, _l, p in C.fold_lead(sc["lead"])]
    d_raw = np.abs(np.diff(raw)) if len(raw) > 1 else np.array([0])
    d_fold = np.abs(np.diff(fold)) if len(fold) > 1 else np.array([0])
    bad += check("folding the lead removes its octave leaps",
                 "%d leaps over 7 semitones, was %d"
                 % ((d_fold > 7).sum(), (d_raw > 7).sum()),
                 "fewer than before", (d_fold > 7).sum() <= (d_raw > 7).sum())
    bad += check("and keeps every pitch class",
                 "%d of %d notes" % (sum(1 for a, b in zip(raw, fold)
                                         if (a - b) % 12 == 0), len(raw)),
                 "all of them",
                 all((a - b) % 12 == 0 for a, b in zip(raw, fold)))

    print()
    print("  THE SIX CHANNELS")
    frames = C.arrange_score(sc)
    writes = sum(len(f) for f in frames) / float(len(frames))
    bad += check("register writes a frame", "%.2f" % writes, "under 6",
                 writes < 6.0)

    saareg.write_log("/tmp/test_chiparr.log", frames, RATE)
    got, hz = saareg.read_log("/tmp/test_chiparr.log")
    tracks, chip = saareg.tracks(got)
    a = chipdis.analyse(tracks, hz, chip)

    # ch2 must be ch1 an octave up, and the disassembler must see that
    stacks = {(p["a"], p["b"]): p["ratio"] for p in a["stacks"]}
    bad += check("ch2 is the lead an octave up", str(stacks),
                 "ch2 = 2f of ch1", stacks.get((1, 2)) == "2f")

    ch = a["channels"]
    bad += check("ch5 is noise", ch[5]["kind"], "noise",
                 ch[5]["kind"] == "noise")

    # the kick steals ch0, so ch0 glides; nothing else should
    glides = [len(c["glides"]) for c in ch]
    bad += check("only ch0 glides (the kick sweeps)", str(glides),
                 "some on ch0, none elsewhere",
                 glides[0] > 0 and sum(glides[1:]) == 0)

    # the arpeggio must NOT rest - that is the whole rule. It rested under
    # the lead in the first version and the arrangement measured 23.7% of
    # the source's strong peaks covered, which is what thin sounds like
    chord_on = np.zeros(sc["frames"], bool)
    for st, l, _r, _k in sc["chords"]:
        chord_on[st:st + l] = True
    arp = np.array(tracks[3].amp[:sc["frames"]]) > 0
    want = int(chord_on[:len(arp)].sum())
    got_n = int((arp & chord_on[:len(arp)]).sum())
    bad += check("the arpeggio plays through every chord",
                 "%d of %d chord frames" % (got_n, want), "over 95%",
                 want and got_n > 0.95 * want)

    # and nothing else falls silent either: four tone voices above the bass
    # and whatever octave the tracker chose, the channel must play the note
    # where a speaker can reproduce it
    ch0 = [h for h, a, t in zip(tracks[0].hz, tracks[0].amp, tracks[0].tone)
           if a > 0 and t and h > 0]
    lo_hz = float(np.percentile(ch0, 10)) if ch0 else 0.0
    bad += check("ch0 plays the bass above 60 Hz",
                 "10th percentile %.1f Hz" % lo_hz, "over 60",
                 lo_hz > 60.0)

    m = min(len(t.amp) for t in tracks)
    amps = np.array([t.amp[:m] for t in tracks])
    tone = np.array([[bool(v) for v in t.tone[:m]] for t in tracks])
    sounding = ((amps > 0) & tone).sum(axis=0)
    bad += check("tone voices sounding a frame", "%.2f mean" % sounding.mean(),
                 "over 3.5", sounding.mean() > 3.5)
    # the lead has to WIN. At level 12 under a bass at 13 it did not, and a
    # lead that is not the loudest voice is a lead the listener reports as
    # missing even while it sounds in every frame
    lvl = np.array([[a if t else 0 for a, t in zip(tr.amp[:m], tr.tone[:m])]
                    for tr in tracks[:5]])
    lead_on2 = lvl[1] > 0
    wins = int(((lvl.argmax(axis=0) == 1) & lead_on2).sum())
    bad += check("the lead is the loudest tone voice",
                 "%.0f%% of the frames it sounds in"
                 % (100.0 * wins / max(1, int(lead_on2.sum()))),
                 "over 85%", wins > 0.85 * max(1, int(lead_on2.sum())))

    # a long note must still be sounding at the end of itself
    longest = max(sc["bass"], key=lambda q: q[1]) if sc["bass"] else None
    if longest:
        st, ln, _p = longest
        end = min(m - 1, st + ln - 1)
        bad += check("a %d-frame bass note at its end" % ln,
                     "level %d" % lvl[0][end], "over 0", lvl[0][end] > 0)

    bad += check("frames with two voices or fewer",
                 "%.1f%%" % (100.0 * (sounding <= 2).mean()), "under 15%",
                 (sounding <= 2).mean() < 0.15)

    # and it plays the right chord: the cue is D minor, so F not F#
    hzs = [h for h, amp in zip(tracks[3].hz, tracks[3].amp) if amp > 0]
    cls = {}
    for h in hzs:
        k = NAMES[int(round(69 + 12 * np.log2(h / 440.0))) % 12]
        cls[k] = cls.get(k, 0) + 1
    top3 = sorted(sorted(cls, key=cls.get, reverse=True)[:3])
    bad += check("the arpeggio's three commonest notes", " ".join(top3),
                 "A D F - the tonic triad", top3 == ["A", "D", "F"])

    out = S.render(frames, RATE) if hasattr(S, "render") else None
    if out is None:
        import arrange
        out = arrange.render(frames, RATE)
    peak = float(np.abs(out).max())
    bad += check("it makes a sound", "peak %.3f" % peak, "over 0.05",
                 peak > 0.05)

    print()
    print("  %-42s %d" % ("checks that failed", bad))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
