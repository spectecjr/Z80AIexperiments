"""The shakuhachi, as a specification: what shaku.z80s must write.

A 1.8-shaku flute plays D F G A C D - the notes the five holes give -
and what makes it sound like bamboo rather than an organ is breath.
Three things carry that here, and none of them is a sample:

    THE BREATH IS A NOISE CHANNEL. Noise generator 1 in mode 3, clocked
    by channel 3's tone generator rather than a fixed rate, sits under
    the note the whole time - loud at the attack, a third of the tone
    afterwards. It is most of the instrument.

    THE VIBRATO IS THE FRAME RATE. A shakuhachi's yuri is about 4 Hz,
    and 4 Hz at 50 frames a second is twelve frames a cycle - so unlike
    the crow's roughness, this one the CPU can draw. It comes in over
    four cycles, from nothing to +-25 cents, which is what a player
    does with their head rather than their fingers.

    THE PITCH SAGS AS THE BREATH GOES. The release table drops the note
    six units over its last frames - meri, the flattening that comes of
    dropping the chin - and the attack table starts three units under
    and rises into the note.

The tone is three channels: f, 2f and 4f, at 0, -2 and -6 levels. An
octave up is the same frequency byte with the octave register one
higher, so all three take one number.
"""

REST = 255

# D4 F4 G4 A4 C5 D5 F5 - the pentatonic the instrument is bored for
SCALE = [293.66, 349.23, 392.00, 440.00, 523.25, 587.33, 698.46]
NAMES = ["D4", "F4", "G4", "A4", "C5", "D5", "F5"]

NOISE_N, NOISE_OCT = 198, 6     # the breath: about 3.2 kHz, and it never moves
VIB_LEN = 12                    # 50/12 = 4.17 Hz
VIB_RAMP = 48                   # four cycles to reach full depth
VIB_DEPTH = 6                   # frequency-register units, about 25 cents
H2, H4 = 2, 6                   # 2f and 4f, this much quieter than f

# tone level, noise level, pitch offset - by frame from the note's start,
# and held at the last row for as long as the note lasts
ENV = ([(0,  9, -3), (2, 12, -3), (5, 13, -2), (8, 12, -2), (10, 10, -1),
        (11,  8, -1), (12,  7,  0), (12,  6,  0), (13,  6,  0), (13,  5, 0)]
       + [(13, 5, 0)] * 22)

# and by frames remaining, at the end of it
REL = [(12, 5, 0), (11, 5, 0), (9, 4, -1), (7, 4, -2), (5, 3, -3),
       (3, 3, -4), (2, 2, -5), (1, 1, -6), (0, 0, 0)]

#         note, frames
PHRASE = [(0, 80), (REST, 10), (1, 30), (2, 60), (REST, 8), (3, 35),
          (4, 75), (REST, 12), (5, 50), (4, 26), (3, 40), (2, 30),
          (1, 34), (0, 95), (REST, 25)]


def pick(f):
    """The octave and frequency byte for a note: 30.6*2^oct .. 61.0*2^oct."""
    for octave in range(8):
        if 15625.0 * (1 << octave) / 511 <= f <= 15625.0 * (1 << octave) / 256:
            return octave, int(round(511 - 15625.0 * (1 << octave) / f))
    raise ValueError("%.1f Hz is off the chip" % f)


def hz(n, octave):
    return 15625.0 * (1 << octave) / (511 - n)


NOTE = [pick(f) for f in SCALE]


def vibrato():
    """Two tables: the ramp in, then one steady cycle for ever after."""
    import math
    ramp = [int(round(math.sin(2 * math.pi * k / VIB_LEN) * VIB_DEPTH
                      * min(1.0, k / float(VIB_RAMP)))) for k in range(VIB_RAMP)]
    steady = [int(round(math.sin(2 * math.pi * k / VIB_LEN) * VIB_DEPTH))
              for k in range(VIB_LEN)]
    return ramp, steady


VIN, VST = vibrato()

# nothing the routine writes may leave 0..255, and it does not check
assert all(0 <= n + VIB_DEPTH <= 255 for _, n in NOTE)
assert all(0 <= n + min(p for _, _, p in ENV + REL) - VIB_DEPTH
           for _, n in NOTE)

INIT = [(0x1C, 0x02), (0x1C, 0x01),
        (0x14, 0x07),           # tone on channels 0, 1, 2
        (0x15, 0x08),           # noise on channel 3
        (0x16, 0x30),           # noise generator 1 clocked by channel 3
        (0x18, 0x00), (0x19, 0x00),
        (0x0B, NOISE_N),        # the breath's colour, set once
        (0x00, 0x00), (0x01, 0x00), (0x02, 0x00),
        (0x03, 0x00), (0x04, 0x00), (0x05, 0x00)]

QUIET = [(0x00, 0), (0x01, 0), (0x02, 0), (0x03, 0)]


def dup(a):
    a = max(0, min(15, a))
    return a | (a << 4)


class Shaku:
    """One call to frame() a 50 Hz frame; play() starts the phrase."""

    def __init__(self):
        self.pp = len(PHRASE)   # nothing to play
        self.left = 0
        self.note = REST
        self.k = 0
        self.vp = 0

    def play(self):
        self.pp = 0
        self.left = 0

    def fetch(self):
        if self.pp >= len(PHRASE):
            return
        self.note, self.left = PHRASE[self.pp]
        self.pp += 1
        self.k = 0
        self.vp = 0

    def frame(self):
        if not self.left:
            self.fetch()
        if not self.left:
            return []                       # the phrase is over
        out = []
        if self.note == REST:
            if self.k == 0:
                out = list(QUIET)
        else:
            octave, n = NOTE[self.note]
            if self.left <= len(REL):
                ta, na, po = REL[len(REL) - self.left]
            else:
                ta, na, po = ENV[min(self.k, len(ENV) - 1)]
            vib = VIN[self.k] if self.k < VIB_RAMP else VST[self.vp]
            n += po + vib
            if self.k == 0:     # the octaves, at the start of every note
                out += [(0x10, octave | ((octave + 1) << 4)),
                        (0x11, (octave + 2) | (NOISE_OCT << 4))]
            out += [(0x08, n), (0x09, n), (0x0A, n),
                    (0x00, dup(ta)), (0x01, dup(ta - H2)),
                    (0x02, dup(ta - H4)), (0x03, dup(na))]
        self.left -= 1
        self.k = min(255, self.k + 1)
        self.vp = (self.vp + 1) % VIB_LEN
        return out

    def playing(self):
        return self.left or self.pp < len(PHRASE)
