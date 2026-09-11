#!/usr/bin/env python3
"""A MIDI score onto six SAA1099 channels, with the notes exactly right.

    python3 tests/midiarr.py score.mid [source.wav]

This exists to separate two kinds of error that have been confounded all
along. An arrangement made from audio carries both the transcription's
mistakes and the cost of reducing a mix to six square waves; one made from
the score carries only the second. The difference between them is what
better listening would buy, and everything below it is the hardware.

The part-to-channel map is the one `chiparr.py` uses, filled from named
tracks instead of from trackers:

    ch0  the bass, and the kick steals it
    ch1  the melody
    ch2  the melody's octave, or a second melodic part
    ch3  the chord, arpeggiated from whatever pad is sounding
    ch4  a third part
    ch5  percussion noise

Where more parts sound than there are channels, the ones left over are
folded into the arpeggio, which is what a chip musician does with a pad.
"""
import sys

import numpy as np

import arrange as A
import chiparr as C
import saa1099 as S
import smf

RATE = 50
# by name, in the order they matter. A drum track is matched by channel 10
# (index 9), which is where the standard puts percussion.
MELODY = ("bell", "lead", "melody")
BASS = ("contrabass", "sub", "bass", "moogish")
PAD = ("drawbars", "organ", "choir", "pad", "string")


def classify(tracks):
    """Name the parts: melody, bass, pads, drums, and anything else."""
    out = {"melody": [], "bass": [], "pad": [], "drums": [], "other": []}
    for t in tracks:
        if not t.notes:
            continue
        if 9 in t.channels:
            out["drums"].append(t)
            continue
        name = (t.name or "").lower()
        for key, words in (("melody", MELODY), ("bass", BASS), ("pad", PAD)):
            if any(w in name for w in words):
                out[key].append(t)
                break
        else:
            out["other"].append(t)
    # with no named melody, the highest-pitched non-pad part is the melody
    if not out["melody"]:
        pool = out["other"] or out["pad"]
        if pool:
            best = max(pool, key=lambda t: np.median([q.pitch
                                                      for q in t.notes]))
            out["melody"] = [best]
            for k in ("other", "pad"):
                if best in out[k]:
                    out[k].remove(best)
    return out


def polyphony(track, n, rate=RATE, offset=0.0):
    """Every pitch sounding in each frame, lowest first.

    A pad track is polyphonic and `notes_in_frames` keeps only its highest
    note, which throws the chord away - and the chord is exactly what the
    arpeggio channel exists to play. Measured on one score, the organ track
    holds 609 notes across G3 to A6 and is the whole harmony of the piece.
    """
    live = [[] for _ in range(n)]
    for q in track.notes:
        a = int(round((q.start + offset) * rate))
        b = max(a + 1, int(round((q.end + offset) * rate)))
        for i in range(max(0, a), min(n, b)):
            live[i].append(q.pitch)
    for row in live:
        row.sort()
    return live


def notes_in_frames(track, n, rate=RATE, offset=0.0):
    """A MIDI track as (start_frame, length_frames, pitch), monophonic:
    the highest note wins where it overlaps itself."""
    roll = np.zeros(n)
    for q in track.notes:
        a = int(round((q.start + offset) * rate))
        b = max(a + 1, int(round((q.end + offset) * rate)))
        for i in range(max(0, a), min(n, b)):
            if q.pitch > roll[i]:
                roll[i] = q.pitch
    out = []
    i = 0
    while i < n:
        if roll[i] <= 0:
            i += 1
            continue
        j = i
        while j < n and roll[j] == roll[i]:
            j += 1
        out.append((i, j - i, int(roll[i])))
        i = j
    return out


def build(tracks, n, rate=RATE, offset=0.0, bass_lvl=12, mel_lvl=15,
          oct_lvl=7, third_lvl=6, arp_lvl=5, arp_step=4, drum_lvl=12,
          bass_min=60.0, top=2600.0, kick_len=5, mel_octave=1):
    """The score on six channels."""
    parts = classify(tracks)
    out = C.Out(n)

    def lay(ch, rows, level, fall, shift=0, cap=top):
        for start, length, pitch in rows:
            hz = C.midi_hz(pitch + 12 * shift)
            while hz > cap:
                hz /= 2.0
            for k in range(length):
                i = start + k
                if 0 <= i < n:
                    out.tone(ch, i, hz, C.decay(level, k, fall))

    for t in parts["bass"]:
        for start, length, pitch in notes_in_frames(t, n, rate, offset):
            hz = C.midi_hz(pitch)
            while hz < bass_min:
                hz *= 2
            for k in range(length):
                if 0 <= start + k < n:
                    out.tone(0, start + k, hz, C.decay(bass_lvl, k, 0.12))

    mel = []
    for t in parts["melody"]:
        mel += notes_in_frames(t, n, rate, offset)
    mel.sort()
    # A bell's fundamental is low and its strike tone is octaves up, which is
    # why it reads as a high part and why the score's own pitches can sound
    # buried on a square wave. mel_octave lifts the written melody.
    lay(1, mel, mel_lvl, 0.05, shift=mel_octave)

    # The pads. The one with the most notes is the harmony - on the score
    # this was built for, the organ with 609 of them against 72 in each of
    # three choir tracks that turn out to be UNISONS of each other, not a
    # chord. So the arpeggio comes from the widest part's own polyphony, and
    # a unison pad goes on a channel as one sustained voice.
    pads = sorted(parts["pad"] + parts["other"],
                  key=lambda t: -len(t.notes))
    if pads:
        live = polyphony(pads[0], n, rate, offset)
        for i in range(0, n, arp_step):
            row = live[i] if i < len(live) else []
            if not row:
                continue
            pitch = row[(i // arp_step) % len(row)]
            for j in range(arp_step):
                if i + j < n:
                    out.tone(3, i + j, C.midi_hz(pitch),
                             C.decay(arp_lvl, j, 1.2))
        # and its top line as a sustained voice, which is what a drawbar
        # organ sounds like: the chord's top note held
        rows = [(i, 1, int(live[i][-1])) for i in range(n) if live[i]]
        lay(4, rows, third_lvl, 0.0)
    for t in pads[1:2]:
        lay(2, notes_in_frames(t, n, rate, offset), oct_lvl - 1, 0.03)

    for t in parts["drums"]:
        for q in sorted(t.notes, key=lambda z: z.start):
            i = int(round((q.start + offset) * rate))
            lv = int(round(drum_lvl * (0.5 + 0.5 * q.velocity / 127.0)))
            if q.pitch <= 38:                   # kick and low toms
                for k in range(kick_len):
                    f = 150.0 * (0.55 ** (k / float(kick_len - 1)))
                    out.force(0, i + k, f, C.decay(lv, k, 2.2))
            elif q.pitch in (42, 44, 46) or q.pitch >= 49:
                for k in range(3):
                    out.hiss(5, i + k, 0, C.decay(lv - 4, k, 3.0))
            else:
                for k in range(5):
                    out.hiss(5, i + k, 1, C.decay(lv, k, 2.2))
    return out, parts


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip())
        return 2
    tracks, _tpb, tempos, _sigs = smf.read(argv[1])
    end = max((q.end for t in tracks for q in t.notes), default=0.0)
    n = int(round(end * RATE)) + RATE
    out, parts = build(tracks, n)
    for k, v in parts.items():
        if v:
            print("  %-8s %s" % (k, ", ".join((t.name or "?") for t in v)))
    frames = out.registers()
    print("  %d frames, %.2f register pairs a frame"
          % (len(frames), sum(len(f) for f in frames) / float(len(frames))))
    au = A.render(frames, RATE)
    S.wav("/tmp/midiarr.wav", au, mono=True)
    print("  /tmp/midiarr.wav")
    if len(argv) > 2:
        import percept
        import soundfile as sf
        x, sr = sf.read(argv[2], dtype="float32")
        mono = x.mean(axis=1) if x.ndim > 1 else x
        got, _per = percept.compare(mono, au, sr, 1e9, percept.Model(sr))
        print("  fit against the recording: %.1f%%" % (100 * got))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
