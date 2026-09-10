#!/usr/bin/env python3
"""Check the disassembler against routines whose answers are known.

    python3 tests/test_chipdis.py

chipdis.py reads a register log and says what the chip is doing. The
only honest way to test that is to point it at players whose scores are
in this repo and ask whether it recovers what the score says - so this
runs five of them on the emulator, captures the log off the OUT hook,
and checks the findings against the source.
"""
import os
import sys

from bench import Bench
import chipdis
import saareg

HERE = os.path.dirname(os.path.abspath(__file__))


def log_of(harness, init, play, frame, model_frames):
    """Run a routine on the emulator and capture its register log."""
    b = Bench(harness, org=0)
    cap = saareg.capture(b)
    frames = []
    b.fast_timed_call(b.syms[init], 0, 0)
    frames.append(cap["pairs"][:])
    cap["pairs"] = []
    b.fast_timed_call(b.syms[play], 0, 0)
    cap["pairs"] = []
    for _ in range(model_frames):
        b.fast_timed_call(b.syms[frame], 0, 0)
        frames.append(cap["pairs"][:])
        cap["pairs"] = []
    return frames


def check(name, got, want, ok):
    mark = "ok " if ok else "BAD"
    print("    %s %-34s %s" % (mark, name, got if ok else
                               "%s, wanted %s" % (got, want)))
    return 0 if ok else 1


def main():
    bad = 0

    # --- the flute: notes, vibrato, and a harmonic stack -------------
    import shaku as K
    frames = log_of("harness_shaku.asm", "sk_init", "sk_play", "sk_frame", 610)
    tracks, chip = saareg.tracks(frames)
    a = chipdis.analyse(tracks, 50, chip)
    saareg.write_log("/tmp/shaku.sreg", frames)
    print("  shaku.z80s")
    ch0 = a["channels"][0]
    names = [chipdis.note_name(n.median_hz())[0] for n in ch0["notes"]
             if n.frames > 3]
    want = [K.NAMES[n] for n, _ in K.PHRASE if n != K.REST]
    bad += check("notes recovered", "%d: %s" % (len(names), " ".join(names)),
                 " ".join(want), names == want)
    cents = max(abs(chipdis.note_name(n.median_hz())[1]) for n in ch0["notes"]
                if n.frames > 3)
    bad += check("all within 25 cents of a note", "%.0f cents" % cents, "<25",
                 cents < 25)
    vibbed = [n for n in ch0["notes"] if n.vib]
    best = max(vibbed, key=lambda n: n.frames) if vibbed else None
    rate = best.vib["hz"] if best else 0
    depth = best.vib["cents"] if best else 0
    # read off the longest note; the depth is a mean over that note and the
    # vibrato ramps in over four cycles, so rather less than full depth
    bad += check("vibrato found", "%.2f Hz, +-%.0f cents" % (rate, depth),
                 "%.2f Hz, some way under +-24" % (50.0 / K.VIB_LEN),
                 abs(rate - 50.0 / K.VIB_LEN) < 0.1 and 12 < depth < 24)
    stacks = {(s["a"], s["b"]): s["ratio"] for s in a["stacks"]}
    bad += check("2f and 4f channels found", str(sorted(stacks.items())),
                 "ch1 = 2f of ch0, ch2 = 4f of ch0",
                 stacks.get((0, 1)) == "2f" and stacks.get((0, 2)) == "4f")
    bad += check("the breath is mode 3 noise", chip.get("noise gen 1", "-"),
                 "clocked by ch3", "clocked by ch3" in chip.get("noise gen 1", ""))

    # --- the pad: three detuned pairs, written as a divider offset ----
    import strings as T
    frames = log_of("harness_strings.asm", "st_init", "st_play", "st_frame", 650)
    tracks, chip = saareg.tracks(frames)
    a = chipdis.analyse(tracks, 50, chip)
    print("  strings.z80s")
    pairs = {(p["a"], p["b"]): p for p in a["pairs"]}
    bad += check("three pairs found", str(sorted(pairs)),
                 "(0,1) (2,3) (4,5)",
                 set(pairs) == {(0, 1), (2, 3), (4, 5)})
    divs = sorted(set(p["divider"] for p in pairs.values()))
    bad += check("the detune, as it was written", "dividers differ by %s" % divs,
                 "-%d" % T.DET, divs == [-T.DET])
    beat = sum(p["beat"] for p in pairs.values()) / len(pairs)
    bad += check("and what it beats at", "%.2f Hz" % beat, "about 1 Hz",
                 0.4 < beat < 2.0)

    # --- the crow: a 40 Hz pair, which is the whole trick -------------
    frames = log_of("harness_crow.asm", "crow_init", "crow_call",
                    "crow_frame", 120)
    tracks, chip = saareg.tracks(frames)
    a = chipdis.analyse(tracks, 50, chip)
    print("  crow.z80s")
    p01 = [p for p in a["pairs"] if (p["a"], p["b"]) == (0, 1)]
    bad += check("the roughness pair",
                 "%.0f Hz, called %s" % (p01[0]["beat"], p01[0]["kind"])
                 if p01 else "not found",
                 "30..55 Hz, roughness",
                 bool(p01) and 30 < p01[0]["beat"] < 55
                 and p01[0]["kind"] == "roughness")

    # --- the thunder: no tones at all, and channels ganged ------------
    import thunder as TH
    frames = log_of("harness_thunder.asm", "sm_init", "sm_play",
                    "sm_frame", TH.FRAMES)
    tracks, chip = saareg.tracks(frames)
    a = chipdis.analyse(tracks, 50, chip)
    saareg.write_log("/tmp/thunder.sreg", frames)
    print("  storm.z80s over the thunder score")
    bad += check("nothing is a tone", chip.get("tone on", "?"), "nothing",
                 chip.get("tone on") == "nothing")
    bad += check("both generators ganged three ways",
                 "; ".join(chip.get("ganging %d" % g, "-") for g in (0, 1)),
                 "46 levels each",
                 all("46 levels" in chip.get("ganging %d" % g, "")
                     for g in (0, 1)))
    rates = chip.get("noise gen 0", "")
    bad += check("the rumble's clock reaches the floor", rates,
                 "about 300 down to 124 shifts a second",
                 any("%d " % v in rates for v in (123, 124, 125, 126)))

    # --- both voices at once: the stack survives sharing the chip -----
    frames = log_of("harness_ensemble.asm", "en_init", "en_play",
                    "en_frame", 650)
    tracks, chip = saareg.tracks(frames)
    a = chipdis.analyse(tracks, 50, chip)
    print("  ensemble.z80s")
    stacks = {(s["a"], s["b"]): s["ratio"] for s in a["stacks"]}
    bad += check("the flute's octave pair", str(sorted(stacks.items())),
                 "ch2 = 2f of ch1", stacks.get((1, 2)) == "2f")
    kinds = [c["kind"] for c in a["channels"]]
    bad += check("one noise channel, five tones", str(kinds),
                 "noise then five tones",
                 kinds[0] == "noise" and kinds[1:] == ["tone"] * 5)

    print()
    print("  %-46s %d" % ("checks that failed", bad))
    ok = bad == 0
    print("\n%s" % ("ALL TESTS PASSED" if ok else "FAILURES: %d" % bad))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
