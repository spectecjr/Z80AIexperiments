"""The crow, as a specification: what crow.z80s must write, and when.

A caw is eighteen 50 Hz frames of a five-oscillator voice plus a noise
channel, and a call is three of them with gaps. Everything below is in
Hz and 0-15 amplitudes; nof() turns a frequency into the byte the
SAA1099 wants, and the Z80's table (crowdata.z80s) is generated from
exactly these numbers by mkcrowdata.py.

The voice, and why each channel is there:

    ch0  f            the fundamental
    ch1  f - ~44 Hz   detuned against it: the pair beat at the rate a
                      crow's voice is rough at, which is the one thing
                      a chip with no envelopes and 50 Hz control cannot
                      do any other way
    ch2  2f           the second harmonic - an octave up is the same
                      frequency byte with the octave register one
                      higher, so it costs nothing to work out
    ch4  2f - ~47 Hz  detuned against ch2, so the harmonic is rough too
    ch5  4f           a little brightness on top
    ch3  noise        noise generator 1 in mode 3, which clocks it from
                      channel 3's own tone generator - so the rasp is
                      pitched, and sweeps down through the caw with
                      everything else

Nothing is sampled and nothing is streamed: the CPU writes twelve
registers a frame and the chip does the rest.
"""

OCT = 3                 # the caw lives in one octave, 245..488 Hz
NOCT = 6                # the noise clock in another, 1953..3906 Hz
D1 = 26                 # ch1 detune, in frequency-register units, and
D2 = 14                 # ch4 detune - both downwards, which is what keeps
                        # every byte the routine writes inside 0..255
H4 = 4                  # how much quieter 4f is than the rest
GAP = 12                # frames of silence between caws
SEED = 0xACE1

# one caw: fundamental Hz, noise clock Hz, tone amplitude, noise amplitude
CAW = [(380, 3800,  5, 15),      # the noisy "k" of it
       (415, 3400, 12, 14),
       (425, 3100, 15, 12),      # pitch peaks here and then sags
       (423, 2900, 15, 11),
       (419, 2800, 14, 10),
       (414, 2750, 14,  9),
       (410, 2700, 13,  9),
       (406, 2650, 13,  8),
       (402, 2600, 12,  8),
       (398, 2550, 12,  7),
       (394, 2500, 11,  7),
       (390, 2480, 10,  6),
       (386, 2460,  8,  6),
       (382, 2440,  6,  5),
       (378, 2420,  4,  4),
       (375, 2400,  2,  3),
       (373, 2400,  1,  1),
       (373, 2400,  0,  0)]

# a call: three caws, each transposed up by this much and this much
# quieter than the one the table holds
SEQ = [(20, 0), (30, 1), (8, 2)]

FRAMES = len(CAW)
CAWS = len(SEQ)


def nof(f, octave):
    """The frequency byte for a target Hz: f = 15625 * 2^oct / (511 - n)."""
    n = int(round(511 - 15625.0 * (1 << octave) / f))
    assert 0 <= n <= 255, "%.1f Hz is outside octave %d" % (f, octave)
    return n


def hz(n, octave):
    return 15625.0 * (1 << octave) / (511 - n)


# the table as the Z80 holds it: four bytes a frame
ENV = [(nof(f, OCT), nof(nc, NOCT), ta, na) for f, nc, ta, na in CAW]

# every byte the routine can ever write has to fit, at both ends: the
# highest is the top of the arc transposed up, the lowest is the bottom
# of it detuned down. The Z80 does no clamping, and this is why it need not.
assert max(n for n, _, _, _ in ENV) + max(t for t, _ in SEQ) + 3 <= 255
assert min(n for n, _, _, _ in ENV) - D1 >= 0

# what crow_init writes, in order
INIT = [(0x1C, 0x02),           # reset the generators
        (0x1C, 0x01),           # and enable the chip
        (0x14, 0x37),           # tone on channels 0, 1, 2, 4, 5
        (0x15, 0x08),           # noise on channel 3
        (0x16, 0x30),           # noise generator 1 clocked by channel 3
        (0x18, 0x00),           # no envelope generators
        (0x19, 0x00),
        (0x10, 0x33),           # octaves: ch0 3, ch1 3
        (0x11, 0x64),           #          ch2 4, ch3 6
        (0x12, 0x54),           #          ch4 4, ch5 5
        (0x00, 0x00), (0x01, 0x00), (0x02, 0x00),
        (0x03, 0x00), (0x04, 0x00), (0x05, 0x00)]


def dup(a):
    """An amplitude byte: the same 0-15 level in both nibbles."""
    a = max(0, min(15, a))
    return a | (a << 4)


class Crow:
    """The routine's state machine, one call to frame() a 50 Hz frame."""

    def __init__(self, seed=SEED):
        self.lfsr = seed
        self.ix = None          # frame within the caw; None between them
        self.gap = 0
        self.k = CAWS           # which caw of the call comes next
        self.tr = self.dr = 0

    def rnd(self):
        """stars.z80s's LFSR: taps 0, 2, 3, 5, one byte a call."""
        for _ in range(8):
            bit = ((self.lfsr >> 0) ^ (self.lfsr >> 2) ^ (self.lfsr >> 3)
                   ^ (self.lfsr >> 5)) & 1
            self.lfsr = (self.lfsr >> 1) | (bit << 15)
        return self.lfsr & 0xFF

    def start(self):
        """Begin the next caw of the call, if there is one."""
        if self.k >= CAWS:
            return
        t, d = SEQ[self.k]
        self.k += 1
        self.tr = t + (self.rnd() & 3)
        self.dr = d
        self.ix = 0

    def trigger(self):
        """Caw - three of them, and no two calls quite alike."""
        self.k = 0
        self.gap = 0
        self.start()

    def writes(self, ix):
        n0, n3, ta, na = ENV[ix]
        n = n0 + self.tr
        a = max(0, ta - self.dr)
        return [(0x08, n), (0x09, n - D1), (0x0A, n), (0x0B, n3),
                (0x0C, n - D2), (0x0D, n),
                (0x00, dup(a)), (0x01, dup(a)), (0x02, dup(a)),
                (0x03, dup(max(0, na - self.dr))),
                (0x04, dup(a)), (0x05, dup(a - H4))]

    def frame(self):
        """What this frame writes to the chip: twelve pairs, or nothing."""
        if self.gap:
            self.gap -= 1
            if not self.gap:
                self.start()
            return []
        if self.ix is None:
            return []
        out = self.writes(self.ix)
        self.ix += 1
        if self.ix == FRAMES:
            self.ix = None
            self.gap = GAP
        return out

    def sounding(self):
        return self.ix is not None or self.gap or self.k < CAWS
