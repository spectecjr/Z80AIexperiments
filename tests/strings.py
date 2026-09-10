"""The string pad, as a specification: what strings.z80s must write.

Six channels, spent the way a string machine spends them: a triad, and
a second copy of it a hair out of tune.

    ch0 ch2 ch4    the three notes of the chord
    ch1 ch3 ch5    the same three, three frequency units above

Three units is about one hertz down here, so each pair beats once a
second - which is the whole of what makes an ensemble sound like more
than one player. Nothing else in the routine produces it: at 50 frames
a second the CPU could draw a 1 Hz tremolo, but it would be one
tremolo, in step across the chord, and that sounds like a Leslie rather
than a section.

The vibrato is shared but not in phase. One 12-entry sine, laid down
twice so the index never has to wrap (twist.z80s's trick), read at
+0, +4 and +8 for the three notes - so they wander against each other
for nothing at all.

Chords change legato: the notes move and the level does not, so there
is one attack at the beginning and one release at the end, which is
what a pad is.
"""

DET = 3                 # the second copy, in frequency-register units
VIB_LEN = 12            # 50/12 = 4.17 Hz
VIB_DEPTH = 2           # about 10 cents down here
VIB_SPREAD = 4          # how far apart the three notes' vibrato phases are

ATT = [0, 1, 2, 3, 4, 5, 6, 7, 7, 8, 8, 8, 9, 9, 9, 9, 9, 9, 9, 10]
SUS = 10
REL = [10, 10, 9, 9, 8, 8, 7, 7, 6, 6, 5, 5, 4, 4, 3, 3, 3, 2, 2, 2,
       1, 1, 1, 1, 1, 0, 0, 0, 0, 0]

# D natural minor: i - VI - III - VII - i, low, under a flute
CHORDS = [(["D3", "F3", "A3"], 120),
          (["Bb2", "D3", "F3"], 120),
          (["F3", "A3", "C4"], 120),
          (["C3", "E3", "G3"], 120),
          (["D3", "F3", "A3"], 170)]

PITCH = {"Bb2": 116.54, "C3": 130.81, "D3": 146.83, "E3": 164.81,
         "F3": 174.61, "G3": 196.00, "A3": 220.00, "C4": 261.63}


def pick(f):
    for octave in range(8):
        if 15625.0 * (1 << octave) / 511 <= f <= 15625.0 * (1 << octave) / 256:
            return octave, int(round(511 - 15625.0 * (1 << octave) / f))
    raise ValueError("%.1f Hz is off the chip" % f)


def hz(n, octave):
    return 15625.0 * (1 << octave) / (511 - n)


def vibrato():
    """One cycle, laid down twice so +8 never runs off the end."""
    import math
    one = [int(round(math.sin(2 * math.pi * k / VIB_LEN) * VIB_DEPTH))
           for k in range(VIB_LEN)]
    return one + one


VIB = vibrato()

# each chord as the routine holds it: three (frequency byte, octave byte)
# and how many frames it lasts
CHORD = [([(pick(PITCH[n])[1], pick(PITCH[n])[0] | (pick(PITCH[n])[0] << 4))
           for n in notes], dur) for notes, dur in CHORDS]
TOTAL = sum(dur for _, dur in CHORDS)

assert all(n + DET + VIB_DEPTH <= 255 and n - VIB_DEPTH >= 0
           for notes, _ in CHORD for n, _ in notes)

INIT = [(0x1C, 0x02), (0x1C, 0x01),
        (0x14, 0x3F),           # tone on all six
        (0x15, 0x00),           # and no noise anywhere
        (0x16, 0x00),
        (0x18, 0x00), (0x19, 0x00),
        (0x00, 0x00), (0x01, 0x00), (0x02, 0x00),
        (0x03, 0x00), (0x04, 0x00), (0x05, 0x00)]


def dup(a):
    a = max(0, min(15, a))
    return a | (a << 4)


class Strings:
    """One call to frame() a 50 Hz frame; play() starts the progression."""

    def __init__(self):
        self.cp = len(CHORD)
        self.left = 0
        self.total = 0
        self.k = 0          # frames since the progression started
        self.vp = 0
        self.level = None   # what the amplitude registers hold
        self.notes = None

    def play(self):
        self.cp = 0
        self.left = 0
        self.total = TOTAL
        self.k = 0
        self.vp = 0
        self.level = None

    def fetch(self):
        if self.cp >= len(CHORD):
            return
        self.notes, self.left = CHORD[self.cp]
        self.cp += 1

    def frame(self):
        if not self.left:
            self.fetch()
        if not self.left:
            return []
        out = []
        if self.left == CHORD[self.cp - 1][1]:      # the chord's first frame
            out += [(0x10 + i, o) for i, (_, o) in enumerate(self.notes)]
        for i, (n, _) in enumerate(self.notes):
            v = n + VIB[self.vp + i * VIB_SPREAD]
            out += [(0x08 + i * 2, v), (0x09 + i * 2, v + DET)]
        if self.total <= len(REL):
            level = REL[len(REL) - self.total]
        elif self.k < len(ATT):
            level = ATT[self.k]
        else:
            level = SUS
        if level != self.level:
            self.level = level
            out += [(r, dup(level)) for r in range(6)]
        self.left -= 1
        self.total -= 1
        self.k = min(255, self.k + 1)
        self.vp = (self.vp + 1) % VIB_LEN
        return out

    def playing(self):
        return self.left or self.cp < len(CHORD)
