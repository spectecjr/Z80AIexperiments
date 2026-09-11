"""A score onto six channels, the way a chip musician would spend them.

transcribe.py reduces audio to a bass line, a lead, two more melodic
voices, a chord and a drum part. This plays them - all of them, every
frame. That is the whole design rule, and it is the second version of it:

    EVERY PART IDENTIFIED GETS A CHANNEL, AND KEEPS IT.

The first version let parts yield to each other - the arpeggio rested
while the lead played, the drums took a channel of their own - and the
result measured 23.7% of the source's strong 200-2500 Hz peaks covered,
which is audibly thin. A part that goes quiet to make room for another
part is a part the arrangement has lost. So now nothing yields: a voice
with nothing to play holds its last note or falls back to a chord tone,
which is the chip version of reducing a line to a single tone rather than
dropping it.

    ch0   bass - and the KICK, which steals this channel for five frames.
          A kick and a bass note land on the same beat in nearly every bar,
          so spending a second channel on the pair buys nothing
    ch1   the lead, held through the gaps in the tracking
    ch2   the second voice. Where the tracker found none, the lead an
          octave up, so this channel is never silent under a lead
    ch3   the chord, ARPEGGIATED, ALWAYS. This is the mid register, and
          it is the part the first version threw away
    ch4   the third voice, falling back to a sustained chord tone
    ch5   percussion, noise only, at a fixed rate - NOT mode 3, which
          clocks from ch3's tone generator, and ch3 is running the
          arpeggio. A snare whose brightness follows the chord is not a
          snare

Four tone voices above the bass, then, against a median of six strong
partials in the source - so the arrangement is a reduction, but it is no
longer a sketch. Levels are set so the four do not sum past the mixer:
the lead leads, the inner voices sit under it, the arpeggio under those.
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


def build(sc, bass_lvl=13, lead_lvl=12, v2_lvl=9, v3_lvl=7, arp_lvl=7,
          arp_step=4, drum_lvl=12, bass_min=60.0, kick_len=5, hold=10,
          top=1900.0):
    """A transcription to six channels of chip, with nothing left out."""
    n = sc["frames"]
    o = Out(n)
    voices = sc.get("voices") or [[], []]

    def lay(ch, notes, level, fall, cap=top):
        """A part onto a channel, note by note."""
        on = np.zeros(n, bool)
        for start, length, pitch in notes:
            hz = midi_hz(pitch)
            while hz > cap:                     # a square at 3 kHz whistles
                hz /= 2.0                       # over the arrangement
            for k in range(length):
                i = start + k
                if 0 <= i < n:
                    o.tone(ch, i, hz, decay(level, k, fall))
                    on[i] = True
        return on

    bass_on = np.zeros(n, bool)
    for start, length, pitch in sc["bass"]:
        hz = midi_hz(pitch)
        while hz < bass_min:                 # nothing reproduces 37 Hz, and
            hz *= 2                          # the chip's bottom octave is mud
        for k in range(length):
            o.tone(0, start + k, hz, decay(bass_lvl, k, 0.12))
            if 0 <= start + k < n:
                bass_on[start + k] = True

    lead_on = lay(1, sc["lead"], lead_lvl, 0.06)
    v2_on = lay(2, voices[0] if len(voices) > 0 else [], v2_lvl, 0.05)
    v3_on = lay(4, voices[1] if len(voices) > 1 else [], v3_lvl, 0.05)

    # where the second voice found nothing, the lead an octave up. The
    # channel is there either way; it may as well thicken the lead
    for start, length, pitch in sc["lead"]:
        hz = midi_hz(pitch) * 2
        while hz > top:
            hz /= 2.0
        for k in range(length):
            i = start + k
            if 0 <= i < n and not v2_on[i]:
                o.tone(2, i, hz, decay(v2_lvl - 2, k, 0.05))

    # the chord, arpeggiated, every frame of every chord - and the third
    # voice holds a chord tone wherever the tracker gave it nothing, so
    # neither channel ever falls silent mid-phrase
    for start, length, root, kind in sc["chords"]:
        notes = [48 + root + s for s in TRIAD[kind]]
        for k in range(0, length, arp_step):
            hz = midi_hz(notes[(k // arp_step) % len(notes)])
            for j in range(arp_step):
                i = start + k + j
                if 0 <= i < n:
                    o.tone(3, i, hz, decay(arp_lvl, j, 1.2))
        fill = midi_hz(notes[2])                # the fifth, up where it
        for k in range(length):                 # will not mud the root
            i = start + k
            if 0 <= i < n and not v3_on[i]:
                o.tone(4, i, fill * 2, max(0, v3_lvl - 3))

    # a part whose tracking drops out for a moment holds instead of
    # flickering: a note that stops for four frames and starts again is
    # heard as a fault, not as phrasing
    for ch, on in ((1, lead_on), (2, v2_on), (4, v3_on)):
        gap = 0
        for i in range(1, n):
            if o.sounded[ch, i]:
                gap = 0
                continue
            if o.sounded[ch, i - 1] or gap:
                gap += 1
                if gap <= hold:
                    o.oct[ch, i] = o.oct[ch, i - 1]
                    o.byte[ch, i] = o.byte[ch, i - 1]
                    lv = int(o.lvl[ch, i - 1]) - 1
                    if lv > 0:
                        o.lvl[ch, i] = lv
                        o.sounded[ch, i] = True
                    else:
                        gap = hold + 1
                else:
                    gap = hold + 1

    for i, kind, vel in sc["drums"]:
        lv = int(round(drum_lvl * (0.55 + 0.45 * vel)))
        if kind == "kick":
            for k in range(kick_len):        # a tone swept down, which is
                f = 150.0 * (0.55 ** (k / float(kick_len - 1)))   # a kick,
                o.force(0, i + k, f, decay(lv, k, 2.2))      # on the bass
        elif kind == "snare":
            for k in range(5):
                o.hiss(5, i + k, 1, decay(lv, k, 2.2))
        else:
            for k in range(3):
                o.hiss(5, i + k, 0, decay(lv - 4, k, 3.0))
    return o


def arrange_score(sc, **kw):
    return build(sc, **kw).registers()
