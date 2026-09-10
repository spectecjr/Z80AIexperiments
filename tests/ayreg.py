"""VGM and VGZ files as register logs, for the AY-3-8910 / YM2149.

A VGM file IS a register log - that is the whole format: writes to a
sound chip with waits in between, which is why chip tunes are a few
kilobytes. So the same disassembler that reads an SAA1099 log reads
one of these; only the register map changes.

    A channel's period is twelve bits across two registers, and
    f = clock / (16 * period).  The mixer at R7 is active LOW - a bit
    SET means that channel's tone or noise is OFF, which catches
    everybody once. R8-R10 hold a four-bit level, or bit 4 set to say
    "use the envelope generator instead", which is the AY's one real
    trick: run the envelope at audio rate and it stops being an
    envelope and becomes a sawtooth oscillator.

Clock is read from the header when it is there; a 128K Spectrum runs
its AY at 1,773,400 Hz.
"""
import gzip
import struct

SPECTRUM_AY = 1773400


def load(path):
    data = open(path, "rb").read()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    if data[:4] != b"Vgm ":
        raise ValueError("not a VGM file")
    return data


# how many bytes follow each command byte, where it is a fixed number
FIXED = {0x4F: 1, 0x50: 1, 0x61: 2, 0x62: 0, 0x63: 0, 0x66: 0,
         0x90: 4, 0x91: 4, 0x92: 5, 0x93: 10, 0x94: 1, 0x95: 4}


def operands(cmd):
    if cmd in FIXED:
        return FIXED[cmd]
    if 0x30 <= cmd <= 0x3F:
        return 1
    if 0x40 <= cmd <= 0x4E:
        return 2
    if 0x51 <= cmd <= 0x5F:
        return 2
    if 0x70 <= cmd <= 0x8F:
        return 0
    if 0xA0 <= cmd <= 0xBF:
        return 2
    if 0xC0 <= cmd <= 0xDF:
        return 3
    if 0xE0 <= cmd <= 0xFF:
        return 4
    return 0


def parse(path, hz=None):
    """Returns (frames, hz, info) - frames of (register, value) for the AY."""
    d = load(path)
    version = struct.unpack_from("<I", d, 0x08)[0]
    total = struct.unpack_from("<I", d, 0x18)[0]
    off = struct.unpack_from("<I", d, 0x34)[0] if version >= 0x150 else 0
    start = (0x34 + off) if off else 0x40
    clock = struct.unpack_from("<I", d, 0x74)[0] if version >= 0x151 \
        and len(d) > 0x78 else 0
    i = start
    t = 0                       # in 44100ths, which is what VGM counts in
    writes = []                 # (sample time, register, value)
    waits = {}
    while i < len(d):
        c = d[i]
        i += 1
        if c == 0x66:
            break
        if c == 0xA0:
            writes.append((t, d[i], d[i + 1]))
            i += 2
            continue
        if c == 0x61:
            n = struct.unpack_from("<H", d, i)[0]
            t += n
            waits[n] = waits.get(n, 0) + 1
            i += 2
            continue
        if c == 0x62:
            t += 735
            waits[735] = waits.get(735, 0) + 1
            continue
        if c == 0x63:
            t += 882
            waits[882] = waits.get(882, 0) + 1
            continue
        if 0x70 <= c <= 0x7F:
            t += (c & 15) + 1
            continue
        if c == 0x67:                           # a data block
            size = struct.unpack_from("<I", d, i + 2)[0]
            i += 6 + size
            continue
        i += operands(c)
    if hz is None:                              # what the file waits in
        common = max(waits.items(), key=lambda kv: kv[1])[0] if waits else 882
        hz = 44100.0 / common
        hz = 50 if abs(hz - 50) < 5 else (60 if abs(hz - 60) < 5 else hz)
    step = 44100.0 / hz
    n = int(t / step) + 1
    frames = [[] for _ in range(n)]
    for st, r, v in writes:
        frames[min(n - 1, int(st / step))].append((r, v))
    info = {"version": "%x.%02x" % (version >> 8, version & 0xFF),
            "clock": clock or SPECTRUM_AY, "samples": total,
            "seconds": t / 44100.0, "writes": len(writes), "hz": hz}
    return frames, hz, info


class State:
    def __init__(self, clock=SPECTRUM_AY):
        self.clock = clock
        self.reg = [0] * 16

    def apply(self, frame):
        for r, v in frame:
            if r < 16:
                self.reg[r] = v & 0xFF

    def period(self, ch):
        return self.reg[2 * ch] | ((self.reg[2 * ch + 1] & 0x0F) << 8)

    def hz(self, ch):
        p = self.period(ch)
        return self.clock / (16.0 * p) if p else 0.0

    def tone_on(self, ch):
        return not (self.reg[7] >> ch) & 1          # active low

    def noise_on(self, ch):
        return not (self.reg[7] >> (ch + 3)) & 1

    def level(self, ch):
        return self.reg[8 + ch] & 15

    def env_mode(self, ch):
        return bool(self.reg[8 + ch] & 0x10)

    def noise_hz(self):
        p = self.reg[6] & 0x1F
        return self.clock / (16.0 * p) if p else 0.0

    def env_hz(self):
        p = self.reg[11] | (self.reg[12] << 8)
        return self.clock / (256.0 * p) if p else 0.0

    def env_shape(self):
        return self.reg[13] & 15


SHAPES = {0: "\\___", 1: "\\___", 2: "\\___", 3: "\\___",
          4: "/|__", 5: "/|__", 6: "/|__", 7: "/|__",
          8: "\\\\\\\\ saw down, repeating", 9: "\\___ one decay",
          10: "\\/\\/ triangle down first", 11: "\\|-- decay then hold high",
          12: "//// saw up, repeating", 13: "/--- attack then hold high",
          14: "/\\/\\ triangle up first", 15: "/|__ one attack"}


def tracks(frames, clock=SPECTRUM_AY):
    """The three channels as chipdis Tracks, plus what the chip was set to."""
    import chipdis
    st = State(clock)
    hz = [[], [], []]
    amp = [[], [], []]
    tone = [[], [], []]
    noise = [[], [], []]
    env = [[], [], []]
    envhz = []
    envshape = []
    noisehz = []
    for frame in frames:
        st.apply(frame)
        for c in range(3):
            hz[c].append(st.hz(c))
            amp[c].append(15 if st.env_mode(c) else st.level(c))
            tone[c].append(st.tone_on(c))
            noise[c].append(st.noise_on(c))
            env[c].append(st.env_mode(c))
        envhz.append(st.env_hz())
        envshape.append(st.env_shape())
        noisehz.append(st.noise_hz())
    per = [[], [], []]
    st2 = State(clock)
    for frame in frames:
        st2.apply(frame)
        for c in range(3):
            per[c].append(st2.period(c))
    out = [chipdis.Track(c, hz[c], amp[c], tone[c], noise[c], env[c],
                         period=per[c]) for c in range(3)]
    chip = {"chip": "AY-3-8910 at %d Hz" % clock}
    for c in range(3):
        used = sum(1 for i in range(len(frames)) if env[c][i]
                   and (tone[c][i] or noise[c][i]))
        if used:
            chip["ch%d envelope" % c] = "%d frames on the envelope generator" \
                % used
    live = [envhz[i] for i in range(len(frames))
            if any(env[c][i] for c in range(3)) and envhz[i]]
    if live:
        live.sort()
        shapes = sorted(set(envshape[i] for i in range(len(frames))
                            if any(env[c][i] for c in range(3))))
        chip["envelope rate"] = ("%.1f .. %.1f Hz - %s"
                                 % (live[0], live[-1],
                                    "AUDIBLE AS A TONE, this is a buzzer bass"
                                    if live[len(live) // 2] > 30 else
                                    "slow, so it is a real envelope"))
        chip["envelope shape"] = ", ".join(
            "%d (%s)" % (s, SHAPES.get(s, "?")) for s in shapes)
    nz = [noisehz[i] for i in range(len(frames))
          if any(noise[c][i] and amp[c][i] for c in range(3)) and noisehz[i]]
    if nz:
        nz.sort()
        chip["noise"] = "%.0f .. %.0f Hz" % (nz[0], nz[-1])
    return out, chip
