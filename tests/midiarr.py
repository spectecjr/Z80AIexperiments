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


def detuned(hz, units, clock=C.CLOCK):
    """A frequency moved by whole divider units, the way the chip detunes.

    The SAA1099 makes a tone by dividing its clock by 511-n, so the only
    detune it can express is an integer change in n - and what that is worth
    in cents depends on where in the range the note sits. This returns the
    frequency that n+units would give, so the caller asks for a detune in
    the chip's own terms and the rest of the code keeps working in Hz.
    """
    if not units:
        return hz
    best = None
    for octave in range(8):
        n = 511 - (clock / 512.0) * (1 << octave) / hz
        if -1.0 <= n <= 256.0:
            nn = min(255, max(0, int(round(n)) + units))
            got = (clock / 512.0) * (1 << octave) / max(1, 511 - nn)
            err = abs(np.log(got / hz))
            if best is None or err < best[0]:
                best = (err, got)
    return best[1] if best else hz


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
    vel = np.zeros(n)
    for q in track.notes:
        a = int(round((q.start + offset) * rate))
        b = max(a + 1, int(round((q.end + offset) * rate)))
        for i in range(max(0, a), min(n, b)):
            if q.pitch == roll[i]:
                vel[i] = q.velocity
    out = []
    i = 0
    while i < n:
        if roll[i] <= 0:
            i += 1
            continue
        j = i
        while j < n and roll[j] == roll[i]:
            j += 1
        out.append((i, j - i, int(roll[i]), int(vel[i] or 100)))
        i = j
    return out


def build(tracks, n, rate=RATE, offset=0.0, bass_lvl=12, mel_lvl=15,
          oct_lvl=8, third_lvl=7, arp_lvl=6, arp_step=4, drum_lvl=12,
          bass_min=60.0, top=2600.0, kick_len=5, mel_octave=1,
          detune=2, vib_cents=14.0, vib_frames=10, vib_after=8,
          velocity=True, fill=True):
    """The score on six channels.

    `detune` is in divider units, not cents: the SAA1099 divides by 511-n,
    so two channels on the same note with n differing by one beat at a rate
    that depends on where in the range they sit - about 6 Hz at 500 Hz with
    a difference of one. That beating is most of what makes a chip chord
    sound like an instrument rather than an oscillator, and it is the one
    timbre control the hardware really has: there is no filter, and the
    envelope generators only shape amplitude at a rate this code already
    controls at 50 Hz.

    `velocity` scales a note's level by what was played. The bell carries 27
    distinct velocities from 92 to 127 and the organ 19 from 65 to 101, all
    of which was being thrown away for a fixed level per part.

    `fill` gives a resting channel to whatever else is sounding - the melody
    rests 59% of the time in this score, and a channel silent for that long
    is a channel wasted.
    """
    parts = classify(tracks)
    out = C.Out(n)

    def lay(ch, rows, level, fall, shift=0, cap=top, vib=False, det=0,
            vel=None, only_if_silent=False):
        for row in rows:
            start, length, pitch = row[0], row[1], row[2]
            v = row[3] if len(row) > 3 else 100
            hz = C.midi_hz(pitch + 12 * shift)
            while hz > cap:
                hz /= 2.0
            lv = level
            if velocity and vel is not False:
                lv = int(round(level * (0.55 + 0.45 * min(1.0, v / 110.0))))
            for k in range(length):
                i = start + k
                if not (0 <= i < n):
                    continue
                if only_if_silent and out.sounded[ch, i]:
                    continue
                f = hz
                if vib and length >= vib_after and k >= vib_after:
                    d = vib_cents * min(1.0, (k - vib_after) / float(vib_after))
                    f = hz * 2 ** (d * np.sin(2 * np.pi * (k - vib_after)
                                              / vib_frames) / 1200.0)
                if det:
                    f = detuned(f, det)
                out.tone(ch, i, f, C.decay(lv, k, fall))

    for t in parts["bass"]:
        for row in notes_in_frames(t, n, rate, offset):
            start, length, pitch = row[0], row[1], row[2]
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
    lay(1, mel, mel_lvl, 0.05, shift=mel_octave, vib=True)
    # the melody an octave up, quietly: a square plus its own octave is the
    # oldest way to make one channel sound like an instrument
    lay(2, mel, oct_lvl, 0.05, shift=mel_octave + 1)

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
        # ch4 doubles the ARPEGGIO in unison, a divider or two away, rather
        # than carrying a line of its own. A detune only beats against the
        # same note: two channels on two different notes are just two notes,
        # and the disassembler found no detuned pair at all when ch4 held
        # the harmony's top line instead. One line thickened sounds fuller
        # than two lines bare, and with a median of three distinct pitches
        # in the score against five tone channels there is room to spend.
        arp_rows = []
        for i in range(0, n, arp_step):
            row = live[i] if i < len(live) else []
            if row:
                arp_rows.append((i, arp_step, int(row[(i // arp_step)
                                                     % len(row)])))
        lay(4, arp_rows, third_lvl, 1.2, det=detune)
        if fill:
            # the second voice of the harmony wherever the melody is not
            # using its octave channel
            second = [(i, 1, int(live[i][0])) for i in range(n)
                      if len(live[i]) > 1]
            lay(2, second, oct_lvl - 2, 0.0, only_if_silent=True)
    for t in pads[1:2]:
        if fill:
            lay(4, notes_in_frames(t, n, rate, offset), third_lvl - 2, 0.02,
                only_if_silent=True)

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
            elif q.pitch in (41, 43, 45, 47, 48, 50):
                # a tom is pitched, and reading it as noise throws away the
                # only drum in the kit that plays a note. The map gives
                # roughly the right pitch per GM tom number.
                f = 90.0 * 2 ** ((q.pitch - 41) / 12.0)
                for k in range(6):
                    out.force(4, i + k, f * (0.92 ** k),
                              C.decay(lv - 1, k, 1.8))
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
