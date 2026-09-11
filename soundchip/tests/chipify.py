#!/usr/bin/env python3
"""A recording, or a MIDI score, as an SAA1099 register log. One command.

    python3 tests/chipify.py song.mp3
    python3 tests/chipify.py song.mp3 --refit          # slower, closer
    python3 tests/chipify.py song.mid --audio song.mp3 # from the score
    python3 tests/chipify.py song.mp3 --melody struck  # a struck lead

Everything it needs is in this directory plus numpy and soundfile
(libsndfile 1.1 or later, for reading and writing MP3). Nothing else: the
SAA1099 is emulated in `saa1099.py`, MIDI is read by `smf.py`, and the
measurements come from `percept.py` and `cover.py`.

It writes four files beside the output name:

    NAME.wav    the chip, rendered
    NAME.mp3    the same, if libsndfile can write one
    NAME.log    the register log - (register, value) pairs a frame, which
                is the actual deliverable: 50 writes a second of SAA1099
                registers, playable on the hardware
    NAME.txt    what chipdis.py makes of that log, read back

and prints the measurements as it goes.

On time: a three-minute recording takes about a minute to transcribe and
arrange. `--refit` searches each two-second segment's octaves and levels
against the recording and takes twelve to twenty minutes more; it is worth
it, and it is the only slow part.

Written by Claude (Opus) for the Z80AIexperiments repo.
"""
import argparse
import os
import sys
import time

import numpy as np

RATE = 50


def say(*a):
    print(*a, flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="chipify",
        description="A recording or a MIDI score as SAA1099 registers.")
    ap.add_argument("source", help="an audio file, or a .mid score")
    ap.add_argument("--audio", help="the recording, when the source is MIDI: "
                                    "used only to measure the result")
    ap.add_argument("--out", help="output name (default: beside the source)")
    ap.add_argument("--refit", action="store_true",
                    help="search each segment against the recording (slow)")
    ap.add_argument("--segment", type=float, default=2.0,
                    help="refit segment length in seconds (default 2)")
    ap.add_argument("--melody", choices=("loudest", "struck"),
                    default="loudest",
                    help="which line becomes the lead. 'struck' suits a "
                         "recording whose tune is played on something hit "
                         "- a bell, a mallet - under a louder sustained "
                         "part; 'loudest' suits everything else")
    ap.add_argument("--detune", type=int, default=2,
                    help="chorus depth in divider units, 0 for none")
    ap.add_argument("--chorus-steals", action="store_true",
                    help="give a voice up for the chorus (fuller, and it "
                         "measured 12 points of coverage worse)")
    ap.add_argument("--start", type=float, default=0.0,
                    help="skip to this many seconds in")
    ap.add_argument("--length", type=float, default=0.0,
                    help="only this many seconds (0 = all of it)")
    args = ap.parse_args(argv)

    import soundfile as sf
    import arrange as A
    import chipdis
    import chiparr as C
    import saa1099 as S
    import saareg

    base = args.out or os.path.splitext(args.source)[0] + "-chip"
    is_midi = args.source.lower().endswith((".mid", ".midi"))
    t0 = time.time()

    audio_path = args.audio if is_midi else args.source
    mono = sr = None
    if audio_path:
        x, sr = sf.read(audio_path, dtype="float32")
        if args.start or args.length:
            a = int(args.start * sr)
            b = a + int(args.length * sr) if args.length else len(x)
            x = x[a:b]
        mono = x.mean(axis=1) if x.ndim > 1 else x
        say("  %s: %.1f s at %d Hz" % (os.path.basename(audio_path),
                                       len(mono) / float(sr), sr))

    if is_midi:
        import midiarr
        import smf
        tracks, _tpb, tempos, sigs = smf.read(args.source)
        notes = sum(len(t.notes) for t in tracks)
        if not notes:
            say("  this file has no notes in it - only %d tracks of "
                "metadata. Re-export with the note data included."
                % len(tracks))
            return 1
        bpm = 60e6 / tempos[0][1]
        say("  the score: %.2f bpm, %s, %d notes over %d tracks"
            % (bpm, "/".join(map(str, sigs[0][1:])) if sigs else "?",
               notes, len(tracks)))
        end = max(q.end for t in tracks for q in t.notes)
        n = int(round(end * RATE)) + RATE
        out, parts = midiarr.build(tracks, n, beat=60.0 * RATE / bpm,
                                   detune=args.detune)
        for k, v in parts.items():
            if v:
                say("    %-8s %s" % (k, ", ".join((t.name or "?")
                                                  for t in v)))
    else:
        import transcribe as T
        say("  transcribing...")
        sc = T.transcribe(x, sr, RATE, melody=args.melody)
        say("  %.2f bpm, grid %.3f frames, %d bass notes, %d melody notes, "
            "%d chords, %d drum hits"
            % (sc["bpm"], sc["grid"][1], len(sc["bass"]), len(sc["lead"]),
               len(sc["chords"]), len(sc["drums"])))
        out = C.build(sc, detune=args.detune,
                      chorus_steals=args.chorus_steals)

    frames = out.registers()
    say("  %d frames, %.2f register pairs a frame"
        % (len(frames), sum(len(f) for f in frames) / float(len(frames))))

    if args.refit and mono is not None:
        import cover
        import percept
        import refit
        say("  refitting each %.0f s segment (this is the slow part)"
            % args.segment)
        sf.write(base + "-ref.wav", mono, sr)
        peaks = cover.source_peaks(base + "-ref.wav", RATE)
        os.remove(base + "-ref.wav")
        refit.refit(out, mono, sr, RATE, args.segment,
                    model=percept.Model(sr), peaks=peaks)
        frames = out.registers()

    au = A.render(frames, RATE)
    S.wav(base + ".wav", au, mono=True)
    saareg.write_log(base + ".log", frames, RATE)
    try:
        z, _ = sf.read(base + ".wav", dtype="float32")
        if z.ndim == 1:
            z = np.stack([z, z], axis=1)
        sf.write(base + ".mp3", z, 44100, format="MP3",
                 compression_level=0.0)
    except Exception as exc:                    # libsndfile without MP3
        say("  (no mp3: %s)" % exc)

    got, hz = saareg.read_log(base + ".log")
    tracks2, chip = saareg.tracks(got)
    text = chipdis.report(chipdis.analyse(tracks2, hz, chip),
                          os.path.basename(base))
    open(base + ".txt", "w").write(text + "\n")

    if mono is not None:
        import cover
        import percept
        m = min(len(mono), len(au))
        fit, _per = percept.compare(mono[:m], au[:m], sr, 1e9,
                                    percept.Model(sr))
        sf.write(base + "-ref.wav", mono, sr)
        hit, tot = cover.coverage(cover.source_peaks(base + "-ref.wav", RATE),
                                  base + ".log", rate=RATE)
        os.remove(base + "-ref.wav")
        say("  fit %.1f%%, peaks covered %.1f%%"
            % (100 * fit, 100.0 * hit / max(1, tot)))
    say("  %.0f s. Wrote %s.wav, .mp3, .log and .txt"
        % (time.time() - t0, base))
    return 0


if __name__ == "__main__":
    sys.exit(main())
