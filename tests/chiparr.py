"""A score onto six channels, the way a chip musician would spend them.

transcribe.py reduces audio to four lines. This plays them:

    ch0   bass, one note at a time, moved up an octave if it is below
          what a speaker will reproduce anyway - and the KICK, which steals
          this channel for five frames. A kick and a bass note land on the
          same beat in nearly every bar, so spending a second channel on the
          pair buys nothing; stealing is what a chip musician does instead
    ch1   lead
    ch2   the lead an octave up, quieter - the same frequency byte with
          the octave register one higher, so it costs nothing to work out.
          It drops out above oct_top: a square wave at 2.6 kHz is not
          thickening the lead, it is whistling over it
    ch3   the chord, ARPEGGIATED: one note of the triad every few
          frames, which is how three notes fit in one channel and is the
          oldest trick in chip music. It RESTS while the lead plays: bass
          plus lead plus lead-octave is already three voices, and a fourth
          running under them is the difference between an arrangement and
          a wall. The arpeggio is there to fill the lead's gaps
    ch4   the snare's tone, under its noise - and nothing else, so most
          frames it is silent
    ch5   percussion noise, on a FIXED noise rate so it does not depend
          on channel 3's tone generator, which the arpeggio is using

Every part gets a per-note envelope in frames, because a flat level
sounds like an organ and a decay sounds like an instrument. The
percussion decays in three to six frames, the arpeggio in two, the bass
and lead hold with a slight fall.
"""
import math

import numpy as np

import arrange as A

CLOCK = 8000000.0
A4 = 440.0


def pick(f):
    """Nearest (octave, frequency byte) for a frequency."""
    best = None
    for octave in range(8):
        n = 511 - (CLOCK / 512.0) * (1 << octave) / f
        if -1.0 <= n <= 256.0:
            nn = int(round(min(255.0, max(0.0, n))))
            got = (CLOCK / 512.0) * (1 << octave) / (511 - nn)
            err = abs(math.log(got / f))
            if best is None or err < best[0]:
                best = (err, octave, nn)
    return (best[1], best[2]) if best else (0, 0)


def midi_hz(m):
    return A4 * 2 ** ((m - 69) / 12.0)


TRIAD = {"": (0, 4, 7), "m": (0, 3, 7)}


class Out:
    """Per-frame state for six channels, then the register writes."""

    def __init__(self, n):
        self.n = n
        self.oct = np.zeros((6, n), int)
        self.byte = np.zeros((6, n), int)
        self.lvl = np.zeros((6, n), int)
        self.noise = np.zeros((6, n), int)       # 0 off, else mode+1
        self.sounded = np.zeros((6, n), bool)

    def tone(self, c, i, hz, level):
        if i < 0 or i >= self.n or level <= 0 or hz <= 0:
            return
        o, b = pick(hz)
        self.oct[c, i], self.byte[c, i] = o, b
        self.lvl[c, i] = max(self.lvl[c, i], min(15, level))
        self.sounded[c, i] = True

    def force(self, c, i, hz, level):
        """Like tone(), but it takes the channel over rather than sharing."""
        if i < 0 or i >= self.n:
            return
        o, b = pick(hz)
        self.oct[c, i], self.byte[c, i] = o, b
        self.lvl[c, i] = min(15, max(0, level))
        self.noise[c, i] = 0
        self.sounded[c, i] = level > 0

    def hiss(self, c, i, mode, level):
        if i < 0 or i >= self.n or level <= 0:
            return
        self.noise[c, i] = mode + 1
        self.lvl[c, i] = max(self.lvl[c, i], min(15, level))
        self.sounded[c, i] = True

    def registers(self):
        frames = []
        state = [None] * 32
        for i in range(self.n):
            want = {}
            fen = nen = 0
            for c in range(6):
                if self.noise[c, i]:
                    nen |= 1 << c
                elif self.sounded[c, i]:
                    fen |= 1 << c
                want[c] = self.lvl[c, i] * 0x11
                want[0x08 + c] = self.byte[c, i]
            want[0x14] = fen
            want[0x15] = nen
            modes = [0, 0]
            for c in range(6):
                if self.noise[c, i]:
                    modes[c // 3] = self.noise[c, i] - 1
            want[0x16] = modes[0] | (modes[1] << 4)
            want[0x10] = self.oct[0, i] | (self.oct[1, i] << 4)
            want[0x11] = self.oct[2, i] | (self.oct[3, i] << 4)
            want[0x12] = self.oct[4, i] | (self.oct[5, i] << 4)
            out = []
            for r in (0x14, 0x15, 0x16, 0x10, 0x11, 0x12, 0x08, 0x09, 0x0A,
                      0x0B, 0x0C, 0x0D, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05):
                if state[r] != want[r]:
                    out.append((r, want[r]))
                    state[r] = want[r]
            frames.append(out)
        if frames:
            frames[0] = list(A.INIT) + frames[0]
        return frames


def decay(level, k, fall):
    """A level k frames into a note."""
    return int(round(max(0, level - fall * k)))


def build(sc, bass_lvl=13, lead_lvl=12, oct_lvl=6, arp_lvl=9,
          arp_step=4, drum_lvl=13, bass_min=60.0, kick_len=5,
          oct_top=1800.0):
    """A transcription to six channels of chip."""
    n = sc["frames"]
    o = Out(n)

    for start, length, pitch in sc["bass"]:
        hz = midi_hz(pitch)
        while hz < bass_min:                 # nothing reproduces 37 Hz, and
            hz *= 2                          # the chip's bottom octave is mud
        for k in range(length):
            o.tone(0, start + k, hz, decay(bass_lvl, k, 0.12))

    for start, length, pitch in sc["lead"]:
        hz = midi_hz(pitch)
        for k in range(length):
            lv = decay(lead_lvl, k, 0.06)
            o.tone(1, start + k, hz, lv)
            if hz * 2 <= oct_top:
                o.tone(2, start + k, hz * 2, max(0, lv - (lead_lvl - oct_lvl)))

    lead_on = np.zeros(n, bool)             # so the arpeggio can get out of
    for start, length, _p in sc["lead"]:     # the lead's way entirely
        lead_on[start:start + length] = True
    for start, length, root, kind in sc["chords"]:
        notes = [48 + root + s for s in TRIAD[kind]]
        for k in range(0, length, arp_step):
            hz = midi_hz(notes[(k // arp_step) % len(notes)])
            for j in range(arp_step):
                i = start + k + j
                if i < 0 or i >= n or lead_on[i]:
                    continue
                o.tone(3, i, hz, decay(arp_lvl, j, 1.5))

    for i, kind, vel in sc["drums"]:
        lv = int(round(drum_lvl * (0.55 + 0.45 * vel)))
        if kind == "kick":
            for k in range(kick_len):        # a tone swept down, which is
                f = 150.0 * (0.55 ** (k / float(kick_len - 1)))   # a kick,
                o.force(0, i + k, f, decay(lv, k, 2.2))      # on the bass
        elif kind == "snare":
            for k in range(5):
                o.tone(4, i + k, 190.0, decay(lv - 3, k, 2.0))
                o.hiss(5, i + k, 1, decay(lv, k, 2.2))
        else:
            for k in range(3):
                o.hiss(5, i + k, 0, decay(lv - 4, k, 3.0))
    return o


def arrange_score(sc, **kw):
    return build(sc, **kw).registers()
