"""A Philips SAA1099 as the SAM Coupe wires it up, for listening to.

This is a renderer, not a verified model: the Z80 side of a sound
routine is checked bit for bit (every OUT it makes, in order, against
the routine's own model), and then the stream of register writes is
played through this to get a .wav. What the chip does with those writes
is taken from MAME's saa1099.cpp, and the places where that involves a
judgement call are listed in crow.md.

    clock           8 MHz on a SAM Coupe
    tone            f = 15625 * 2^octave / (511 - n), 31 Hz to 7.81 kHz
    noise           an 18-bit LFSR, x^18 + x^11 + x, seeded with 1 and
                    shifted right: rand = (rand >> 1) ^ 0x20400 when the
                    bit shifted out is 1. Shifted at 31250 >> mode Hz
                    for modes 0..2, and by the tone generator of channel
                    0 (or 3) for mode 3 - which triggers it once per
                    half cycle, so at twice that channel's audible
                    frequency
    mixer           per channel: tone alone or noise alone gives the
                    amplitude when the bit is 1; with both enabled the
                    output is tone * (2 - noise), so full amplitude on a
                    tone 1 with the noise low, half on a tone 1 with the
                    noise high, and nothing when the tone is low

Registers: 0x00-0x05 amplitude (low nibble left, high nibble right),
0x08-0x0D frequency, 0x10-0x12 octave (two channels a byte, low nibble
first), 0x14 frequency enable, 0x15 noise enable, 0x16 noise mode (two
bits a generator, generator 1 in bits 4-5), 0x18-0x19 envelope,
0x1C bit 0 sound enable and bit 1 reset.
"""
import numpy as np

CLOCK = 8000000         # the SAM's crystal for the SAA
RATE = 44100            # what comes out
OVER = 4                # rendered at OVER * RATE, then filtered down

ADDR_PORT = 511         # OUT 511,reg then OUT 255,value
DATA_PORT = 255


def lfsr_bits():
    """One whole period of the noise generator's output bit.

    SAASound's generator, which is what SimCoupe plays: x^18 + x^11 + x
    as a right-shifting LFSR seeded with 1, the output being the bit
    shifted out. 2^18-1 bits, cached because it is the same sequence
    every time.
    """
    if not hasattr(lfsr_bits, "seq"):
        n = (1 << 18) - 1
        out = np.empty(n, dtype=np.uint8)
        rand = 1
        for i in range(n):
            out[i] = rand & 1
            rand = ((rand >> 1) ^ 0x20400) if (rand & 1) else (rand >> 1)
        lfsr_bits.seq = out
    return lfsr_bits.seq


class SAA1099:
    def __init__(self, clock=CLOCK, rate=RATE, over=OVER):
        self.clock = clock
        self.rate = rate * over
        self.reg = [0] * 32
        self.amp = [(0, 0)] * 6         # (left, right), 0..15
        self.freq = [0] * 6             # the frequency byte
        self.octave = [0] * 6
        self.fen = 0                    # frequency enable bits
        self.nen = 0                    # noise enable bits
        self.nmode = [0, 0]
        self.enabled = False
        self.phase = np.zeros(6)        # square wave phase, in cycles
        self.nphase = np.zeros(2)       # noise phase, in LFSR shifts
        self.out = []

    # --- the chip's own arithmetic -------------------------------

    def tone_hz(self, ch):
        """The audible square wave frequency of one channel."""
        return 15625.0 * (1 << self.octave[ch]) / (511 - self.freq[ch]) \
            * (self.clock / 8000000.0)

    def noise_hz(self, gen):
        """How often the noise LFSR shifts."""
        mode = self.nmode[gen]
        if mode == 3:                   # clocked by channel 0 or 3
            return 2.0 * self.tone_hz(gen * 3)
        return (self.clock / 256.0) / (1 << mode)

    # --- the bus -------------------------------------------------

    def write(self, reg, val):
        reg &= 0x1F
        val &= 0xFF
        self.reg[reg] = val
        if reg <= 0x05:
            self.amp[reg] = (val & 15, val >> 4)
        elif 0x08 <= reg <= 0x0D:
            self.freq[reg - 0x08] = val
        elif 0x10 <= reg <= 0x12:
            ch = (reg - 0x10) * 2
            self.octave[ch] = val & 7
            self.octave[ch + 1] = (val >> 4) & 7
        elif reg == 0x14:
            self.fen = val & 0x3F
        elif reg == 0x15:
            self.nen = val & 0x3F
        elif reg == 0x16:
            self.nmode = [val & 3, (val >> 4) & 3]
        elif reg in (0x18, 0x19):
            if val & 0x80:
                raise NotImplementedError(
                    "envelope generator %d enabled; this model does not "
                    "have one (see crow.md)" % (reg - 0x18))
        elif reg == 0x1C:
            self.enabled = bool(val & 1)
            if val & 2:                 # reset: generators to zero
                self.phase[:] = 0
                self.nphase[:] = 0

    def port(self, addr, val):
        """An OUT as the Z80 makes it: 511 selects, 255 writes."""
        if addr == ADDR_PORT:
            self.sel = val
        elif addr == DATA_PORT:
            self.write(getattr(self, "sel", 0), val)

    # --- rendering -----------------------------------------------

    def run(self, seconds):
        """Render `seconds` at the current register settings."""
        n = int(round(seconds * self.rate))
        left = np.zeros(n)
        right = np.zeros(n)
        if not self.enabled:
            self.out.append((left, right))
            return
        t = np.arange(n)
        seq = lfsr_bits()
        noise = []
        for g in (0, 1):
            step = self.noise_hz(g) / self.rate
            idx = (self.nphase[g] + t * step).astype(np.int64) % len(seq)
            noise.append(seq[idx])
            self.nphase[g] = (self.nphase[g] + n * step) % len(seq)
        for ch in range(6):
            fen = (self.fen >> ch) & 1
            nen = (self.nen >> ch) & 1
            al, ar = self.amp[ch]
            step = self.tone_hz(ch) / self.rate
            ph = self.phase[ch] + t * step
            self.phase[ch] = (self.phase[ch] + n * step) % 1.0
            if not (al or ar) or not (fen or nen):
                continue
            tone = (np.floor(ph * 2).astype(np.int64) & 1).astype(np.uint8)
            nz = noise[ch // 3]
            if nen and fen:             # both on: the noise halves the
                lvl = np.where(nz, tone * 2, tone)       # tone, per SAASound
            elif nen:
                lvl = nz
            else:
                lvl = tone
            gain = np.where(lvl == 0, 0.0, 1.0 / np.maximum(lvl, 1))
            left += gain * al
            right += gain * ar
        self.out.append((left, right))

    def samples(self):
        """Everything rendered so far, at RATE, stereo, float."""
        left = np.concatenate([a for a, _ in self.out])
        right = np.concatenate([b for _, b in self.out])
        return np.stack([decimate(left), decimate(right)], axis=1)


def decimate(x, over=OVER):
    """Down to RATE through a windowed-sinc, so the squares do not alias."""
    taps = 8 * over + 1
    k = np.arange(taps) - taps // 2
    h = np.sinc(k / float(over)) * np.hanning(taps)
    h /= h.sum()
    return np.convolve(x, h, mode="same")[::over]


def dcblock(x, rate=RATE, hz=25.0):
    """The chip's output is unipolar; the SAM's audio out is not."""
    a = np.exp(-2 * np.pi * hz / rate)
    y = np.empty_like(x)
    prev_x = 0.0
    prev_y = 0.0
    for i in range(len(x)):             # one pole, one zero
        y[i] = prev_y * a + x[i] - prev_x
        prev_x = x[i]
        prev_y = y[i]
    return y


def wav(path, stereo, rate=RATE, peak=0.89):
    """Write float stereo to a 16-bit wav, normalised to `peak`."""
    import wave
    s = np.stack([dcblock(stereo[:, 0]), dcblock(stereo[:, 1])], axis=1)
    m = np.abs(s).max()
    if m > 0:
        s = s * (peak / m)
    data = (np.clip(s, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(data.tobytes())
    return m
