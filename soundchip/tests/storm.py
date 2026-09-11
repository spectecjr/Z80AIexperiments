"""The storm, as a specification: what storm.z80s must write.

Distant thunder and then rain, out of the two noise generators and
nothing else - there is not a tone enabled anywhere in this routine.

WHY THE NOISE GENERATOR CAN BE A RUMBLE. In mode 3 the LFSR is clocked
by a tone generator instead of one of the three fixed rates, and a tone
generator goes down to 31 Hz. Clock the noise at 250 shifts a second
and what comes out is a random square wave whose energy is all below
about 125 Hz - which is a rumble, not a hiss. Sweeping that clock from
190 Hz down to 68 Hz over seven seconds is thunder rolling away and
losing its top end to the air, which is exactly what distance does to
it.

The same generator at 5 kHz is rain. Nothing else changes.

WHY THREE CHANNELS A LAYER. An amplitude register is four bits, and
sixteen steps is not enough to fade a seven-second rumble without
hearing the steps. All three channels of a group carry the SAME noise
generator, so their outputs are identical and simply add: three
channels at level five are exactly level fifteen, and the levels in
between give **46 steps instead of 16**. th_spread holds the three
bytes for each of them, so the routine looks up rather than divides.

    ch0 ch1 ch2   noise generator 0, clocked by channel 0's tone
    ch3 ch4 ch5   noise generator 1, clocked by channel 3's tone

Both layers are scores of segments - frames, where the clock starts and
ends, where the level starts and ends - interpolated in 8.8 by two
adds a frame. The generator turns Hz into the chip's bytes and splits
any segment that crosses an octave boundary, so the score can be
written in Hz and levels and stay readable.
"""

MAXLVL = 45             # three channels of fifteen
SUB = 8                 # fixed point: 8.8 accumulators

# frames, clock Hz at the start and end, level 0..1 at the start and end
THUNDER = [
    (20, 220, 205, 0.00, 0.55),         # the front of it arrives
    (25, 205, 190, 0.55, 0.35),
    (35, 190, 170, 0.35, 1.00),         # the main swell
    (30, 170, 158, 1.00, 0.60),
    (40, 158, 144, 0.60, 0.82),         # and then it rolls
    (35, 144, 132, 0.82, 0.42),
    (45, 132, 120, 0.42, 0.62),
    (40, 120, 109, 0.62, 0.26),
    (45, 109,  96, 0.26, 0.34),
    (35,  96,  87, 0.34, 0.12),
    (40,  87,  78, 0.12, 0.00),         # the tail
    (30, 5400, 5400, 0.00, 0.00),       # silent: the layer changes job
    (100, 5400, 5100, 0.00, 0.30),      # and comes back as the rain's hiss
    (100, 5100, 5500, 0.30, 0.34),
    (80, 5500, 5600, 0.34, 0.00),       # and it passes
]

RAIN = [
    (120, 1600, 1600, 0.00, 0.00),      # nothing yet
    (120, 1600, 1450, 0.00, 0.26),      # it starts under the thunder
    (140, 1450, 1700, 0.26, 0.34),
    (160, 1700, 1400, 0.34, 0.29),      # and washes about
    (80, 1400, 1550, 0.29, 0.34),
    (80, 1550, 1650, 0.34, 0.00),       # away over the fields
]

INIT = [(0x1C, 0x02), (0x1C, 0x01),
        (0x14, 0x00),           # not one tone anywhere
        (0x15, 0x3F),           # noise on all six channels
        (0x16, 0x33),           # both generators clocked by their own
        (0x18, 0x00), (0x19, 0x00),
        (0x00, 0x00), (0x01, 0x00), (0x02, 0x00),
        (0x03, 0x00), (0x04, 0x00), (0x05, 0x00)]


def pick(f):
    """Octave and frequency byte, whichever pair lands nearest.

    The octaves do not quite meet - the top of one is 61.04 * 2^k and
    the bottom of the next 61.15 * 2^k - so a frequency can fall in the
    crack between them, and the nearest byte is the honest answer.
    """
    best = None
    for octave in range(8):
        n = 511 - 15625.0 * (1 << octave) / f
        if -1.0 <= n <= 256.0:
            n = int(round(min(255.0, max(0.0, n))))
            err = abs(hz(n, octave) - f)
            if best is None or err < best[0]:
                best = (err, octave, n)
    if best is None:
        raise ValueError("%.1f Hz is off the chip" % f)
    return best[1], best[2]


def hz(n, octave):
    return 15625.0 * (1 << octave) / (511 - n)


def octave_of(f):
    return pick(f)[0]


def split(seg):
    """Cut a segment wherever it would cross an octave boundary.

    A frequency byte only spans one octave, so a sweep from 126 Hz to
    116 Hz has to become two segments meeting at the 122 Hz boundary:
    the first ends at byte 0 of the octave above, the second starts at
    byte 255 of the one below. The score is written in Hz and this does
    the chip's bookkeeping.
    """
    frames, f0, f1, l0, l1 = seg
    out = []
    while True:
        o0 = octave_of(f0)
        if octave_of(f1) == o0 or frames <= 1:
            out.append((frames, f0, f1, l0, l1))
            return out
        down = f1 < f0
        edge = 15625.0 * (1 << o0) / (511.0 if down else 256.0)
        part = (f0 - edge) / float(f0 - f1)
        n = max(1, min(frames - 1, int(round(frames * part))))
        lm = l0 + (l1 - l0) * n / float(frames)
        out.append((n, f0, edge, l0, lm))
        frames -= n
        l0 = lm
        f0 = 15625.0 * (1 << (o0 - 1)) / 256.0 if down \
            else 15625.0 * (1 << (o0 + 1)) / 511.0


def compile_score(score):
    """Segments as the routine holds them: octave, start byte, and the
    per-frame steps in 8.8 for the byte and the level."""
    out = []
    for seg in score:
        for frames, f0, f1, l0, l1 in split(seg):
            octave, n0 = pick(f0)
            n1 = pick(f1)[1]
            assert pick(f1)[0] == octave, "%.1f..%.1f Hz straddles" % (f0, f1)
            v0 = int(round(l0 * MAXLVL))
            v1 = int(round(l1 * MAXLVL))
            nstep = ((n1 - n0) << SUB) // frames
            vstep = ((v1 - v0) << SUB) // frames
            out.append((frames, octave, n0, nstep, v0, vstep))
    return out


TH = compile_score(THUNDER)
RN = compile_score(RAIN)


def spread(level):
    """A 0..45 level as three amplitude bytes, both nibbles each."""
    level = max(0, min(MAXLVL, level))
    a = [(level + 2) // 3, (level + 1) // 3, level // 3]
    return [v | (v << 4) for v in a]


SPREAD = [spread(v) for v in range(MAXLVL + 1)]


class Layer:
    """One noise generator: a score, a clock and a level."""

    def __init__(self, score, base):
        self.score = score
        self.base = base        # 0 for channels 0-2, 3 for 3-5
        self.sp = len(score)
        self.left = 0
        self.n = self.v = 0
        self.octave = 0

    def play(self):
        self.sp = 0
        self.left = 0

    def fetch(self):
        if self.sp >= len(self.score):
            return
        frames, octave, n0, nstep, v0, vstep = self.score[self.sp]
        self.sp += 1
        self.left = frames
        self.octave = octave
        self.n = n0 << SUB
        self.nstep = nstep
        self.v = v0 << SUB
        self.vstep = vstep

    def frame(self):
        if not self.left:
            self.fetch()
        if not self.left:
            return []
        out = [(0x10 + (self.base // 2),
                self.octave << (4 * (self.base & 1))),
               (0x08 + self.base, (self.n >> SUB) & 0xFF)]
        out += [(self.base + i, b)
                for i, b in enumerate(SPREAD[max(0, min(MAXLVL,
                                                        self.v >> SUB))])]
        self.n += self.nstep
        self.v += self.vstep
        self.left -= 1
        return out

    def playing(self):
        return self.left or self.sp < len(self.score)


class Storm:
    """Two layers of noise, whatever the scores make them."""

    def __init__(self, a=None, b=None):
        self.a = Layer(a if a is not None else TH, 0)
        self.b = Layer(b if b is not None else RN, 3)

    def play(self):
        self.a.play()
        self.b.play()

    def playing(self):
        return self.a.playing() or self.b.playing()

    def frame(self):
        return self.a.frame() + self.b.frame()
