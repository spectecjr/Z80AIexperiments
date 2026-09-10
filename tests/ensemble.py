"""Both voices at once, three oscillators each - the specification.

    ch0     the flute's breath: noise generator 0 in mode 3, which
            clocks it from CHANNEL 0's tone generator - and channel 0
            has its tone disabled, so that generator is free to be a
            3.2 kHz clock and nothing else. That is why the breath is
            on channel 0 rather than anywhere else: mode 3 always takes
            its clock from the first channel of the group.
    ch1     the flute, f
    ch2     the flute, 2f - the same frequency byte, an octave up
    ch3     the strings, the root
    ch4     the strings, the third
    ch5     the strings, the fifth

Losing three channels costs each voice its best trick, and they are
different tricks:

    THE FLUTE loses 4f, which was only brightness. It keeps the breath
    and the vibrato, which are what make it a flute.

    THE STRINGS lose the detuned twins - all three of them - so the
    one-hertz beating that made it a section is gone. What is left is
    the spread vibrato: one sine read at +0, +4 and +8, so the three
    notes still wander against each other, just at 4 Hz rather than 1.

THE OCTAVE REGISTERS ARE THE AWKWARD PART. Each holds two channels, a
nibble each, and the split down the middle of the chip falls inside
register 0x11: its low nibble is the flute's 2f and its high nibble is
the strings' root. Two voices that know nothing about each other have
to write one byte between them - so the tables hold each nibble
pre-shifted, and the frame ORs them together. That is the whole of the
interaction, and it is why this is one routine rather than two.
"""
import shaku as K
import strings as T

NOISE_OCT = K.NOISE_OCT         # the breath: octave 6, about 3.2 kHz
NOISE_N = K.NOISE_N
H2 = K.H2                       # the flute's 2f, this much under f
SUS = 8                         # the pad, quieter than it plays alone

INIT = [(0x1C, 0x02), (0x1C, 0x01),
        (0x14, 0x3E),           # tone on 1 2 3 4 5, not on the breath
        (0x15, 0x01),           # noise on channel 0
        (0x16, 0x03),           # generator 0 clocked by channel 0
        (0x18, 0x00), (0x19, 0x00),
        (0x08, NOISE_N),        # the breath's clock, set once
        (0x00, 0x00), (0x01, 0x00), (0x02, 0x00),
        (0x03, 0x00), (0x04, 0x00), (0x05, 0x00)]


def dup(a):
    a = max(0, min(15, a))
    return a | (a << 4)


class Flute:
    """shaku.py's state machine, reporting rather than writing."""

    def __init__(self):
        self.pp = len(K.PHRASE)
        self.left = self.k = self.vp = 0
        self.note = K.REST
        self.n = 0
        self.octave = 3
        self.ta = self.na = 0
        self.pitch = 0

    def play(self):
        self.pp = 0
        self.left = 0

    def fetch(self):
        if self.pp >= len(K.PHRASE):
            return
        self.note, self.left = K.PHRASE[self.pp]
        self.pp += 1
        self.k = self.vp = 0
        if self.note != K.REST:
            self.octave, self.n = K.NOTE[self.note]

    def frame(self):
        if not self.left:
            self.fetch()
        if not self.left or self.note == K.REST:
            self.ta = self.na = 0
            self.pitch = self.n
        else:
            if self.left <= len(K.REL):
                ta, na, po = K.REL[len(K.REL) - self.left]
            else:
                ta, na, po = K.ENV[min(self.k, len(K.ENV) - 1)]
            vib = K.VIN[self.k] if self.k < K.VIB_RAMP else K.VST[self.vp]
            self.ta, self.na = ta, na
            self.pitch = self.n + po + vib
        if self.left:
            self.left -= 1
            self.k = min(255, self.k + 1)
            self.vp = (self.vp + 1) % K.VIB_LEN

    def playing(self):
        return self.left or self.pp < len(K.PHRASE)


class Pad:
    """strings.py's, the same way."""

    def __init__(self):
        self.cp = len(T.CHORD)
        self.left = self.k = self.vp = 0
        self.total = 0
        self.notes = T.CHORD[0][0]
        self.level = 0
        self.pitch = [n for n, _ in self.notes]

    def play(self):
        self.cp = 0
        self.left = 0
        self.total = T.TOTAL
        self.k = self.vp = 0

    def fetch(self):
        if self.cp >= len(T.CHORD):
            return
        self.notes, self.left = T.CHORD[self.cp]
        self.cp += 1

    def frame(self):
        if not self.left:
            self.fetch()
        if not self.left:
            self.level = 0
            return
        self.pitch = [n + T.VIB[self.vp + i * T.VIB_SPREAD]
                      for i, (n, _) in enumerate(self.notes)]
        if self.total <= len(T.REL):
            self.level = min(SUS, T.REL[len(T.REL) - self.total])
        elif self.k < len(T.ATT):
            self.level = min(SUS, T.ATT[self.k])
        else:
            self.level = SUS        # the pad never gets louder than this
        self.left -= 1
        self.total -= 1
        self.k = min(255, self.k + 1)
        self.vp = (self.vp + 1) % T.VIB_LEN

    def playing(self):
        return self.left or self.cp < len(T.CHORD)


class Ensemble:
    def __init__(self):
        self.flute = Flute()
        self.pad = Pad()

    def play(self):
        self.flute.play()
        self.pad.play()

    def playing(self):
        return self.flute.playing() or self.pad.playing()

    def frame(self):
        """Fifteen registers, every frame, whatever is going on."""
        f, p = self.flute, self.pad
        f.frame()
        p.frame()
        octs = [o & 7 for _, o in p.notes]      # the chord's three octaves
        return [(0x10, NOISE_OCT | (f.octave << 4)),
                (0x11, (f.octave + 1) | (octs[0] << 4)),
                (0x12, octs[1] | (octs[2] << 4)),
                (0x09, f.pitch), (0x0A, f.pitch),
                (0x0B, p.pitch[0]), (0x0C, p.pitch[1]), (0x0D, p.pitch[2]),
                (0x00, dup(f.na)),              # breath
                (0x01, dup(f.ta)),              # f
                (0x02, dup(f.ta - H2)),         # 2f
                (0x03, dup(p.level)), (0x04, dup(p.level)),
                (0x05, dup(p.level))]
