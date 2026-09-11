"""SAA1099 register logs: the format, and what a frame of them means.

A register log is what a debugger or an emulator hook can hand you: the
writes a player makes to the chip, frame by frame. Nothing else about
the program is needed - no source, no symbols - because the chip only
ever learns what is in these thirty-two registers.

    ; saareg 1 50
    0 1C=02 1C=01 14=07 15=08 16=30
    1 10=43 11=65 08=55 09=55 0A=55 00=55 01=33 02=11 03=99
    2 08=56 ...

One line a frame: the frame number, then `register=value` in hex, in
the order they were written. Frames with no writes may be left out.
This is the whole format, and `capture()` writes it straight off an
emulator's OUT hook.

State() then turns a frame of that into what the chip is actually
doing - frequencies in Hz, notes, amplitudes, noise rates - which is
where reading a log stops being a hex dump and starts being music.
"""
import re

CLOCK = 8000000.0               # the SAM's crystal for the SAA
HZ = 50                         # frames a second
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def tone_hz(n, octave, clock=CLOCK):
    """f = 15625 * 2^octave / (511 - n), the chip's own arithmetic."""
    return (clock / 512.0) * (1 << octave) / (511 - n)


def note_name(f):
    """The nearest equal-tempered note, and how far off it is in cents."""
    if f <= 0:
        return "-", 0.0
    import math
    m = 69 + 12 * math.log(f / 440.0, 2)
    k = int(round(m))
    cents = (m - k) * 100
    return "%s%d" % (NOTES[k % 12], k // 12 - 1), cents


def write_log(path, frames, hz=HZ):
    """frames is a list of lists of (register, value)."""
    with open(path, "w") as f:
        f.write("; saareg 1 %d\n" % hz)
        for i, frame in enumerate(frames):
            if frame:
                f.write("%d %s\n" % (i, " ".join("%02X=%02X" % (r, v)
                                                 for r, v in frame)))


def read_log(path):
    """Returns (frames, hz). Frames left out of the log come back empty."""
    hz = HZ
    rows = {}
    last = -1
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        if line.startswith(";"):
            m = re.match(r";\s*saareg\s+(\d+)\s+(\d+)", line)
            if m:
                hz = int(m.group(2))
            continue
        parts = line.split()
        i = int(parts[0])
        rows[i] = [(int(p[:2], 16), int(p[3:], 16)) for p in parts[1:]]
        last = max(last, i)
    return [rows.get(i, []) for i in range(last + 1)], hz


def capture(bench, addr_port=511, data_port=255):
    """Hook an emulator's OUT and collect (register, value) pairs.

    The same nine lines work on a real debugger's watchpoint: the chip
    has two ports, one to select a register and one to write it.
    """
    out = {"sel": 0, "pairs": []}

    def hook(port, value):
        if port == addr_port:
            out["sel"] = value
        elif port == data_port:
            out["pairs"].append((out["sel"], value))

    bench.m.set_output_callback(hook)
    return out


class State:
    """The chip, as a log leaves it after each frame."""

    def __init__(self, clock=CLOCK):
        self.clock = clock
        self.reg = [0] * 32

    def apply(self, frame):
        for r, v in frame:
            self.reg[r & 0x1F] = v & 0xFF

    # --- what the registers mean ---------------------------------

    def amp(self, ch):
        v = self.reg[ch]
        return v & 15, v >> 4                   # left, right

    def octave(self, ch):
        v = self.reg[0x10 + ch // 2]
        return (v & 7) if (ch & 1) == 0 else ((v >> 4) & 7)

    def freq(self, ch):
        return self.reg[0x08 + ch]

    def hz(self, ch):
        return tone_hz(self.freq(ch), self.octave(ch), self.clock)

    def tone_on(self, ch):
        return bool(self.reg[0x14] & (1 << ch))

    def noise_on(self, ch):
        return bool(self.reg[0x15] & (1 << ch))

    def noise_mode(self, gen):
        return (self.reg[0x16] >> (4 * gen)) & 3

    def noise_hz(self, gen):
        """How often that generator's LFSR shifts."""
        mode = self.noise_mode(gen)
        if mode == 3:                           # clocked by ch0 or ch3
            return 2.0 * self.hz(gen * 3)
        return (self.clock / 256.0) / (1 << mode)

    def env(self, gen):
        """The envelope generator: None when it is switched off."""
        v = self.reg[0x18 + gen]
        if not (v & 0x80):
            return None
        return {"shape": (v >> 1) & 7, "bits": 3 if (v & 1) else 4,
                "external": bool(v & 0x20), "mirror": bool(v & 0x10),
                "raw": v}

    def enabled(self):
        return bool(self.reg[0x1C] & 1)

    def sounding(self, ch):
        """Is anything actually coming out of this channel?"""
        l, r = self.amp(ch)
        return (l or r) and (self.tone_on(ch) or self.noise_on(ch)) \
            and self.enabled()

    def snapshot(self):
        """Everything interesting about this frame, as plain numbers."""
        ch = []
        for c in range(6):
            ch.append({
                "n": self.freq(c), "oct": self.octave(c), "hz": self.hz(c),
                "amp": self.amp(c), "tone": self.tone_on(c),
                "noise": self.noise_on(c), "on": self.sounding(c),
            })
        return {"ch": ch, "enabled": self.enabled(),
                "noise": [{"mode": self.noise_mode(g), "hz": self.noise_hz(g)}
                          for g in (0, 1)],
                "env": [self.env(0), self.env(1)],
                "reg": list(self.reg)}


def decode(frames, clock=CLOCK):
    """A log to one snapshot a frame."""
    st = State(clock)
    out = []
    for frame in frames:
        st.apply(frame)
        out.append(st.snapshot())
    return out


def tracks(frames, clock=CLOCK):
    """A log as six chipdis Tracks, plus what the chip was set to."""
    import chipdis
    snaps = decode(frames, clock)
    out = []
    for c in range(6):
        hz = [s["ch"][c]["hz"] for s in snaps]
        amp = [max(s["ch"][c]["amp"]) for s in snaps]
        tone = [s["ch"][c]["tone"] and s["enabled"] for s in snaps]
        noise = [s["ch"][c]["noise"] and s["enabled"] for s in snaps]
        # the SAA divides by (511 - n), so THAT is the divider a detune is
        # written in, not the frequency byte
        per = [511 - s["ch"][c]["n"] for s in snaps]
        out.append(chipdis.Track(c, hz, amp, tone, noise, period=per))
    last = snaps[-1] if snaps else None
    chip = {}
    if last:
        # over the whole log, not in the last frame: a piece that ends in
        # silence has every mixer bit clear there, which says nothing at all
        def ever(key):
            got = []
            for c in range(6):
                k = sum(1 for s in snaps if s["ch"][c][key]
                        and s["enabled"] and max(s["ch"][c]["amp"]))
                if k:
                    got.append("ch%d (%d frames)" % (c, k))
            return " ".join(got) or "nothing"

        chip["tone on"] = ever("tone")
        chip["noise on"] = ever("noise")
        for g in (0, 1):
            used = any(s["ch"][c]["noise"] for s in snaps
                       for c in range(g * 3, g * 3 + 3))
            if used:
                mode = last["noise"][g]["mode"]
                rates = sorted(set(                     # while it is audible
                    round(s["noise"][g]["hz"]) for s in snaps
                    if any(s["ch"][c]["noise"] and max(s["ch"][c]["amp"])
                           for c in range(g * 3, g * 3 + 3))))
                how = ("clocked by ch%d's tone generator" % (g * 3)
                       if mode == 3 else "fixed rate, mode %d" % mode)
                chip["noise gen %d" % g] = (
                    "%s: %d .. %d shifts a second, so noise up to %d Hz"
                    % (how, rates[0], rates[-1], rates[-1] / 2))
        for g in (0, 1):
            e = last["env"][g]
            if e or any(decode(frames, clock)[i]["env"][g] for i in
                        range(0, len(snaps), max(1, len(snaps) // 20))):
                chip["envelope %d" % g] = "IN USE: %s" % (e or "was, earlier")
        if not any("envelope" in k for k in chip):
            chip["envelopes"] = "never switched on"
        # channels ganged on one generator: the amplitude-resolution trick
        for g in (0, 1):
            gang = [c for c in range(g * 3, g * 3 + 3)
                    if any(s["ch"][c]["noise"] and max(s["ch"][c]["amp"])
                           for s in snaps)]
            if len(gang) > 1:
                peak = max(sum(max(s["ch"][c]["amp"]) for c in gang)
                           for s in snaps)
                chip["ganging %d" % g] = (
                    "%s all carry generator %d - %d levels, not 16 (peak %d)"
                    % (" ".join("ch%d" % c for c in gang), g, 15 * len(gang) + 1,
                       peak))
    return out, chip
