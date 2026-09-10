"""Arrange audio onto an SAA1099: six squares and two noise generators.

This is chipdis.py's direction reversed. Instead of reading a register
log and saying what it does, it takes audio and decides what to write to
the chip, frame by frame, so that what comes out is as close to the
input as six oscillators can manage.

HOW IT WORKS. Each frame, the source's spectrum is reduced to band
powers on a log frequency scale. Then a greedy matching pursuit picks
the chip settings that best account for it:

    every (octave, frequency byte) the chip can make is an ATOM, and
    its band vector is not a single peak but the whole odd-harmonic
    ladder of a square wave - f, 3f at a ninth of the power, 5f at a
    twenty-fifth, and so on. Fitting with square atoms rather than
    sinusoids is what makes the arrangement honest: you cannot ask this
    chip for a sine, so the matcher should not pretend you can.

    each noise setting is an atom too, flat up to half its clock rate.

Six atoms are chosen per frame, each with a gain, and the gain is
quantised to the chip's four bits BEFORE the residual is taken - so the
quantisation error is accounted for by the atoms chosen after it rather
than left to spoil the result.

Two things keep it from warbling. A CONTINUITY BONUS makes an atom that
was already sounding on a channel cheaper than a new one, which both
steadies the output and cuts the number of register writes. And a FLOOR
stops it chasing reverb tails and noise: an atom has to reduce the error
by a worthwhile fraction or the channel stays silent.

The output is a register log - the same format chipdis.py reads - so the
whole thing round-trips, and the result can be rendered by saa1099.py
and measured against the source.
"""
import math

import numpy as np

import saa1099 as S

CLOCK = 8000000.0
LEVELS = 15                     # what one amplitude register holds


def band_edges(lo=45.0, hi=9000.0, per_octave=6):
    n = int(round(math.log(hi / lo, 2) * per_octave))
    return lo * 2.0 ** (np.arange(n + 1) / float(per_octave))


def short_energy(x, sr, rate, n_frames, win_ms=10.0, long_win=4096):
    """The loudness of each frame, measured over a short window.

    The band analysis needs a long window to resolve bass pitch, and a
    long window smears an attack over several frames - which is why the
    first version of this tracked only half the onsets. So shape and
    loudness are measured separately: the bands say WHAT to play, this
    says how loud, over ten milliseconds rather than ninety.
    """
    hop = int(round(sr / float(rate)))
    w = int(sr * win_ms / 1000.0)
    out = np.zeros(n_frames)
    for i in range(n_frames):
        c = i * hop + long_win // 2
        lo = max(0, c - w // 2)
        seg = x[lo:lo + w]
        out[i] = float(np.mean(seg * seg)) if len(seg) else 0.0
    return out


def band_power(x, sr, rate, edges, long_win=4096, short_win=1024,
               split=400.0):
    """Band powers a frame, at two resolutions.

    A long window resolves the bass - at 4,096 samples the bins are 10.8
    Hz, which is a semitone at the bottom of this chip's range - and
    smears transients. A short one does the opposite. So the low bands
    come off the long window and the high bands off the short one, which
    is the usual answer and costs one extra transform.
    """
    hop = int(round(sr / float(rate)))
    n = int((len(x) - long_win) / hop) + 1
    out = np.zeros((n, len(edges) - 1))
    for win, want_low in ((long_win, True), (short_win, False)):
        fr = np.fft.rfftfreq(win, 1.0 / sr)
        w = np.hanning(win)
        idx = [np.where((fr >= edges[b]) & (fr < edges[b + 1]))[0]
               for b in range(len(edges) - 1)]
        use = [b for b in range(len(edges) - 1)
               if (edges[b] < split) == want_low and len(idx[b])]
        for i in range(n):
            start = i * hop + (long_win - win) // 2
            seg = x[start:start + win]
            if len(seg) < win:
                break
            sp = np.abs(np.fft.rfft(seg * w)) ** 2
            for b in use:
                out[i, b] = sp[idx[b]].sum()
    return out


def nearest_tone(bank, f):
    """The tone atom closest to a frequency, in cents."""
    i = int(np.searchsorted(bank.tone_hz, f))
    best, bi = None, None
    for j in (i - 1, i, i + 1):
        if 0 <= j < len(bank.tone_hz):
            d = abs(math.log(bank.tone_hz[j] / f, 2))
            if best is None or d < best:
                best, bi = d, j
    return bank.tone_idx[bi]


def refine(bank, atom, fr, sp, span=150.0, prominence=1.3):
    """Snap a tone atom to the actual peak near it.

    The greedy fit works on 1/6 octave bands because that is robust, and
    34 of this chip's frequencies land inside one such band at 440 Hz -
    so to the fit they are identical and the pitch it returns is
    arbitrary to +-100 cents, which is a semitone and a half out of tune.
    This looks at the fine spectrum around the atom it picked, finds the
    peak, and moves to the nearest frequency the chip can actually make.
    Where there is no peak to find - noise, or a band full of nothing -
    it leaves the atom alone.
    """
    f = float(bank.hz[atom])
    k = None
    for widen in (1.0, 2.0):            # an argmax at the edge means the
        lo = f * 2 ** (-span * widen / 1200.0)      # real peak is outside
        hi = f * 2 ** (span * widen / 1200.0)
        k = np.where((fr >= lo) & (fr <= hi))[0]
        if len(k) < 3:
            return atom
        seg = sp[k]
        j = int(np.argmax(seg))
        if 0 < j < len(k) - 1:
            break
    seg = sp[k]
    j = int(np.argmax(seg))
    if seg[j] <= prominence * np.mean(seg):         # nothing peaked here
        return atom
    idx = k[j]
    if 0 < idx < len(sp) - 1:
        a, b, c = sp[idx - 1], sp[idx], sp[idx + 1]
        den = a - 2 * b + c
        off = 0.5 * (a - c) / den if den else 0.0
    else:
        off = 0.0
    peak = fr[idx] + off * (fr[1] - fr[0])
    if peak <= 0:
        return atom
    return nearest_tone(bank, peak)


class Bank:
    """Every setting the chip can be put in, as a band vector."""

    def __init__(self, edges, clock=CLOCK, lo=40.0, hi=6000.0,
                 harmonics=15):
        self.edges = edges
        nb = len(edges) - 1
        rows = []
        self.atoms = []
        seen = set()
        for octave in range(8):
            for n in range(256):
                f = (clock / 512.0) * (1 << octave) / (511 - n)
                if not (lo <= f <= hi):
                    continue
                key = round(math.log(f, 2) * 600)        # 2 cent grid
                if key in seen:
                    continue
                seen.add(key)
                v = np.zeros(nb)
                for h in range(1, harmonics + 1, 2):     # squares: odd only
                    fh = f * h
                    if fh >= edges[-1]:
                        break
                    b = np.searchsorted(edges, fh) - 1
                    if 0 <= b < nb:
                        v[b] += 1.0 / (h * h)
                if v.sum() <= 0:
                    continue
                rows.append(v / v.sum())
                self.atoms.append(("tone", octave, n, f))
        # noise: the three fixed rates, and mode 3 over a grid of clocks
        for mode in (0, 1, 2):
            rate = (clock / 256.0) / (1 << mode)
            rows.append(self._noise_vec(rate, nb))
            self.atoms.append(("noise", mode, 0, rate))
        for octave in range(8):
            for n in range(0, 256, 8):
                f = (clock / 512.0) * (1 << octave) / (511 - n)
                rate = 2.0 * f
                if not (120.0 <= rate <= 16000.0):
                    continue
                rows.append(self._noise_vec(rate, nb))
                self.atoms.append(("noise3", octave, n, rate))
        self.mat = np.array(rows)                 # atoms x bands, unit power
        self.kind = np.array([a[0] for a in self.atoms])
        self.hz = np.array([a[3] for a in self.atoms])
        self.band_of = np.array([int(np.searchsorted(edges, a[3]) - 1)
                                 for a in self.atoms])
        tones = [i for i in range(len(self.atoms))
                 if self.atoms[i][0] == "tone"]
        order = sorted(tones, key=lambda i: self.hz[i])
        self.tone_idx = np.array(order)
        self.tone_hz = np.array([self.hz[i] for i in order])

    def _noise_vec(self, rate, nb):
        """An LFSR's spectrum: flat to half the shift rate, then falling."""
        v = np.zeros(nb)
        for b in range(nb):
            fc = 0.5 * (self.edges[b] + self.edges[b + 1])
            width = self.edges[b + 1] - self.edges[b]
            x = math.pi * fc / rate
            shape = 1.0 if x < 1e-9 else (math.sin(x) / x) ** 2
            v[b] = shape * width
        s = v.sum()
        return v / s if s > 0 else v


def pan_of(bank, atom, bandL, bandR):
    """Where in the stereo field this atom's fundamental sits.

    Returned as the fraction of its power that belongs on the left. The
    chip has a four bit amplitude on each side, so a voice can be placed
    anywhere in sixteen steps without spending a channel on it.
    """
    f = bank.hz[atom]
    b = int(np.searchsorted(bank.edges, f) - 1)
    b = max(0, min(len(bandL) - 1, b))
    l, r = bandL[b], bandR[b]
    if l + r <= 0:
        return 0.5
    return float(l / (l + r))


def fit(target, bank, nch=6, prev=None, floor=0.02, keep=0.25, unit=1.0):
    """Greedy: the chip settings that best account for one frame.

    Returns a list of (atom index, level) - level 1..15, and a gain is
    quantised to a level before its atom is subtracted, so whatever the
    quantisation loses is offered to the atoms chosen after it.
    """
    resid = target.copy()
    total = target.sum()
    out = []
    used = set()
    taken = set()                   # bands that already have a voice
    mat = bank.mat
    norm = (mat * mat).sum(axis=1)
    for _ in range(nch):
        if resid.sum() <= floor * total:
            break
        g = (mat @ resid) / norm                        # best gain an atom
        g = np.maximum(g, 0.0)
        gain = g.copy()
        if prev:                                        # steadiness is cheap
            for a, _lv in prev:
                gain[a] *= 1.0 + keep
        drop = gain * (mat @ resid) - 0.5 * gain * gain * norm
        for a in used:
            drop[a] = -1.0
        if taken:                   # at most one voice to a band: stacking
            drop = drop.copy()      # near-copies of one pitch is a cluster,
            for a in taken:         # not a note, and it wastes five channels
                drop[bank.band_of == a] = -1.0
        a = int(np.argmax(drop))
        if drop[a] <= 0:
            break
        level = int(round(math.sqrt(max(0.0, g[a]) / unit)))
        level = max(0, min(LEVELS, level))
        if level == 0:
            used.add(a)
            continue
        resid = resid - (level * level * unit) * mat[a]
        np.maximum(resid, 0.0, out=resid)
        used.add(a)
        if bank.kind[a] == "tone":
            taken.add(int(bank.band_of[a]))
        out.append((a, level))
    return out


def calibrate(bank, edges, rate=50):
    """What one level of one square is worth, in the same units as the
    source's band powers - measured by rendering it, not assumed."""
    chip = S.SAA1099()
    for r, v in ((0x1C, 0x02), (0x1C, 0x01), (0x14, 0x01), (0x15, 0),
                 (0x16, 0), (0x10, 0x03), (0x08, 85), (0x00, 0x11)):
        chip.write(r, v)
    for _ in range(25):
        chip.run(1.0 / rate)
    x = chip.samples()[:, 0]
    p = band_power(x, S.RATE, rate, edges)
    return p[len(p) // 2].sum()


# ---------------------------------------------------------------
# from chosen atoms to the registers that realise them
# ---------------------------------------------------------------

class Voices:
    """Which channel plays what, and the register writes that say so.

    Two rules come from the chip rather than from the music. Noise
    generator 0 serves channels 0 to 2 and generator 1 serves 3 to 5, and
    in mode 3 each is clocked by the FIRST channel of its group - so a
    noise atom goes on channel 0 or channel 3, with that channel's tone
    disabled and its frequency register holding the clock. Everything
    else is a square, anywhere.
    """

    def __init__(self):
        self.state = [None] * 32
        self.where = {}                 # atom index -> channel, last frame

    def registers(self, bank, chosen):
        ch = [None] * 6                 # (atom, left level, right level)
        noise = [a for a in chosen if bank.kind[a[0]] != "tone"]
        tones = [a for a in chosen if bank.kind[a[0]] == "tone"]
        for slot, a in zip((0, 3), noise[:2]):
            ch[slot] = a
        free = [c for c in (1, 2, 4, 5, 0, 3) if ch[c] is None]
        placed = []
        for a in tones:                 # keep a channel if it had this atom
            want = self.where.get(a[0])
            if want is not None and want in free:
                ch[want] = a
                free.remove(want)
            else:
                placed.append(a)
        for a in placed:
            if not free:
                break
            ch[free.pop(0)] = a

        reg = dict.fromkeys(range(0x00, 0x06), 0)
        fen = nen = 0
        octs = [0] * 6
        freq = [0] * 6
        nmode = [0, 0]
        self.where = {}
        for c in range(6):
            if ch[c] is None:
                continue
            a, lvl_l, lvl_r = ch[c]
            kind, p1, p2, _hz = bank.atoms[a]
            self.where[a] = c
            reg[c] = (lvl_l & 15) | ((lvl_r & 15) << 4)
            if kind == "tone":
                fen |= 1 << c
                octs[c], freq[c] = p1, p2
            else:
                nen |= 1 << c
                gen = c // 3
                if kind == "noise3":
                    nmode[gen] = 3
                    octs[c], freq[c] = p1, p2
                else:
                    nmode[gen] = p1
        want = dict(reg)
        want[0x14] = fen
        want[0x15] = nen
        want[0x16] = nmode[0] | (nmode[1] << 4)
        want[0x10] = octs[0] | (octs[1] << 4)
        want[0x11] = octs[2] | (octs[3] << 4)
        want[0x12] = octs[4] | (octs[5] << 4)
        for c in range(6):
            want[0x08 + c] = freq[c]
        out = []
        for r in (0x14, 0x15, 0x16, 0x10, 0x11, 0x12,
                  0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D,
                  0x00, 0x01, 0x02, 0x03, 0x04, 0x05):
            v = want[r]
            if self.state[r] != v:              # only what changed
                out.append((r, v))
                self.state[r] = v
        return out


INIT = [(0x1C, 0x02), (0x1C, 0x01), (0x18, 0x00), (0x19, 0x00),
        (0x14, 0x00), (0x15, 0x00), (0x16, 0x00),
        (0x00, 0), (0x01, 0), (0x02, 0), (0x03, 0), (0x04, 0), (0x05, 0)]


def arrange(x, sr, rate=50, nch=6, edges=None, bank=None, unit=None,
            floor=0.02, keep=0.25, quiet=1e-4, dynamics=True, norm_pct=84.0,
            pan_depth=0.8, refine_pitch=True):
    """Audio in, register log out."""
    edges = band_edges() if edges is None else edges
    bank = Bank(edges) if bank is None else bank
    unit = calibrate(bank, edges, rate) if unit is None else unit
    stereo_in = x.ndim > 1 and x.shape[1] == 2
    mono = x.mean(axis=1) if stereo_in else x
    power = band_power(mono, sr, rate, edges)
    if stereo_in:
        powL = band_power(x[:, 0], sr, rate, edges)
        powR = band_power(x[:, 1], sr, rate, edges)
    x = mono
    # The chip has no absolute loudness - an amplitude register is just a
    # number - so the source has to be scaled into the chip's units before
    # the four-bit quantisation can mean anything. Aim the loudest frame at
    # most of what six channels can produce, which leaves headroom and puts
    # the quiet frames where the quantisation still has steps to spare.
    if dynamics:
        # Loudness from a ten millisecond window, shape from the bands, so
        # an attack lands on the frame it happened in rather than smeared
        # across the five the long analysis window covers.
        shape = power / np.maximum(1e-30, power.sum(axis=1))[:, None]
        power = shape * short_energy(x, sr, rate, len(power))[:, None]
    # Normalise on a percentile, not the peak: one transient is enough to
    # crush everything else into the bottom two or three levels.
    peak = np.percentile(power.max(axis=1), norm_pct)
    if peak > 0:
        power = power * ((0.8 * LEVELS) ** 2 * unit / peak)
    loud = power.sum(axis=1)
    gate = quiet * loud.max()
    hop = int(round(sr / float(rate)))
    lwin, swin = 4096, 1024
    wl, ws = np.hanning(lwin), np.hanning(swin)
    frl = np.fft.rfftfreq(lwin, 1.0 / sr)
    frs = np.fft.rfftfreq(swin, 1.0 / sr)
    voices = Voices()
    frames = []
    chosen_per_frame = []
    prev = None
    for i in range(len(power)):
        chosen = [] if loud[i] <= gate else \
            fit(power[i], bank, nch, prev, floor, keep, unit)
        if chosen and refine_pitch:
            segl = x[i * hop:i * hop + lwin]
            c0 = i * hop + lwin // 2
            segs = x[max(0, c0 - swin // 2):max(0, c0 - swin // 2) + swin]
            spl = np.abs(np.fft.rfft(segl * wl)) if len(segl) == lwin else None
            sps = np.abs(np.fft.rfft(segs * ws)) if len(segs) == swin else None
            out2 = []
            for a, level in chosen:
                if bank.kind[a] == "tone":
                    # Pitch refinement always wants the LONG window: the
                    # short one's bins are 43 Hz, so a +-100 cent search
                    # around 400 Hz is barely one bin wide and there is
                    # nothing to find. Time smearing matters to the level,
                    # which comes from somewhere else entirely, and not to
                    # the pitch.
                    f = float(bank.hz[a])
                    if f < 5000.0 and spl is not None:
                        a = refine(bank, a, frl, spl)
                    elif sps is not None:
                        a = refine(bank, a, frs, sps)
                out2.append((a, level))
            chosen = out2
        prev = chosen
        chosen_per_frame.append(chosen)
        sided = []
        for a, level in chosen:
            if stereo_in:
                p = pan_of(bank, a, powL[i], powR[i])
                p = 0.5 + (p - 0.5) * pan_depth        # pull it in a little
                lv_l = int(round(level * math.sqrt(2 * p)))
                lv_r = int(round(level * math.sqrt(2 * (1 - p))))
            else:
                lv_l = lv_r = level
            sided.append((a, max(0, min(LEVELS, lv_l)),
                          max(0, min(LEVELS, lv_r))))
        frames.append(voices.registers(bank, sided))
    if frames:
        frames[0] = list(INIT) + frames[0]
    return frames, chosen_per_frame, {"bank": bank, "edges": edges,
                                      "unit": unit, "rate": rate,
                                      "power": power}


def render(frames, rate=50):
    chip = S.SAA1099()
    for frame in frames:
        for r, v in frame:
            chip.write(r, v)
        chip.run(1.0 / rate)
    return chip.samples()


def render_long(frames, rate=50, chunk=1500):
    """Render in chunks, so a four minute arrangement fits in memory.

    The chip's phases carry across chunks because it is the same object;
    only the decimation filter sees an edge, and that is a third of a
    millisecond at each join.
    """
    chip = S.SAA1099()
    pieces = []
    for i in range(0, len(frames), chunk):
        for frame in frames[i:i + chunk]:
            for r, v in frame:
                chip.write(r, v)
            chip.run(1.0 / rate)
        pieces.append(chip.samples())
        chip.out = []
    return np.concatenate(pieces, axis=0)


def compare(src, out, sr, rate, edges):
    """How close it got, in the band domain where it was fitted."""
    a = band_power(src, sr, rate, edges)
    b = band_power(out, sr, rate, edges)
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    ascale = a.sum() / max(1e-30, b.sum())
    b = b * ascale
    la = np.log10(a + 1e-12)
    lb = np.log10(b + 1e-12)
    loud = a.sum(axis=1)
    w = loud > 0.01 * loud.max()
    # Two different failures, worth separating: bands the source has and the
    # arrangement missed, and bands the source does not have at all, which
    # is where a square wave's own harmonics land.
    has = a[w] > 0.005 * a[w].sum(axis=1)[:, None]
    d = 10 * np.abs(la[w] - lb[w])
    missing = d[has]
    added = (b[w] * (~has)).sum() / max(1e-30, b[w].sum())
    return {"frames": n, "dB_mean": missing.mean(),
            "dB_median": np.median(missing),
            "added": 100.0 * added,
            "per_band": (10 * np.abs(la[w] - lb[w])).mean(axis=0),
            "edges": edges}
