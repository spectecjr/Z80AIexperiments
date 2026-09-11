#!/usr/bin/env python3
"""How close two pieces of audio sound, segment by segment.

    python3 tests/percept.py reference.wav candidate.wav [segment_seconds]

`cover.py` counts spectral peaks matched within 60 cents. That is a fair
measure of whether the right NOTES are present and a poor measure of
whether the result sounds like the original: it cannot tell a part that is
20 dB too quiet from one at the right level, it counts a peak at 8 kHz as
dearly as one at 3 kHz where the ear is most sensitive, and it says nothing
at all about a component that is inaudible because something louder is
sitting on top of it.

This is the perceptual version, and it reports a percentage rather than a
distance, because "57% of peaks covered" and "this sounds 57% of the way
there" are not the same claim and only the second one is worth arguing
about:

    fit = 1 - D(candidate, reference) / D(silence, reference)

So 0% is "no better than silence" and 100% is "indistinguishable under
this model". A segment the arranger got wrong in a way that matters scores
low even if its notes were right, and that is the point.

The model, in order:

  1. 23 ms frames, 10 ms apart - about the ear's temporal resolution.
  2. 34 ERB-spaced bands from 50 Hz to 16 kHz. Detail finer than a critical
     band is not heard separately, so comparing it is comparing noise.
  3. Masking spread across bands, asymmetric: -27 dB per ERB downwards,
     -12 dB per ERB upwards, which is roughly the shape of a masking
     pattern and is why a loud low band hides a quiet higher one.
  4. An equal-loudness weighting, so 3 kHz counts for more than 80 Hz.
  5. Cube-root compression of power, which is how loudness grows.

One global gain is fitted before comparing, because the arrangement's
absolute level is arbitrary, but it is fitted ONCE over the whole signal
and not per segment - otherwise a version that got the dynamics wrong
would score as though it had got them right.

Written by Claude (Opus) for the Z80AIexperiments repo.
"""
import sys

import numpy as np

N_FFT = 1024
HOP = 441                       # 10 ms at 44.1 kHz
N_BANDS = 34
F_LO, F_HI = 50.0, 16000.0
DOWN_DB, UP_DB = 27.0, 12.0     # masking spread, per ERB
FLOOR_DB = -70.0


def erb(f):
    """Frequency in Hz to position on the ERB-rate scale."""
    return 21.4 * np.log10(1.0 + 0.00437 * f)


def erb_inv(e):
    return (10.0 ** (e / 21.4) - 1.0) / 0.00437


def band_matrix(sr, n_fft=N_FFT, n_bands=N_BANDS, lo=F_LO, hi=F_HI):
    """Triangular filters, equally spaced on the ERB-rate scale."""
    fr = np.fft.rfftfreq(n_fft, 1.0 / sr)
    edges = erb_inv(np.linspace(erb(lo), erb(min(hi, sr / 2.0)),
                                n_bands + 2))
    M = np.zeros((n_bands, len(fr)))
    for b in range(n_bands):
        a, c, d = edges[b], edges[b + 1], edges[b + 2]
        up = (fr >= a) & (fr <= c)
        dn = (fr > c) & (fr <= d)
        M[b, up] = (fr[up] - a) / max(1e-9, c - a)
        M[b, dn] = (d - fr[dn]) / max(1e-9, d - c)
        s = M[b].sum()
        if s > 0:
            M[b] /= s
    return M, edges[1:n_bands + 1]


def loudness_weight(centres):
    """An equal-loudness weighting, as dB offsets per band.

    A-weighting's shape: down 20 dB at 100 Hz, flat and slightly up around
    2-4 kHz, down again past 10 kHz. The exact curve depends on level and
    this does not model that - it is here so that a wrong note at 3 kHz
    costs more than a wrong note at 80 Hz, which is true at any level.
    """
    f = np.maximum(1.0, centres)
    f2 = f ** 2
    ra = (12194.0 ** 2 * f2 ** 2) / (
        (f2 + 20.6 ** 2)
        * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2))
        * (f2 + 12194.0 ** 2))
    return 20 * np.log10(np.maximum(1e-12, ra)) + 2.0


def spread(power, down_db=DOWN_DB, up_db=UP_DB):
    """Masking spread across bands: a loud band hides its quiet neighbours.

    Two one-pole passes, one each way, at the slopes a masking pattern
    has. Without this, a component the ear cannot hear at all counts
    against the arrangement as much as one it can.
    """
    n = power.shape[1]
    a_up = 10 ** (-up_db / 20.0)
    a_dn = 10 ** (-down_db / 20.0)
    out = power.copy()
    for b in range(1, n):                       # upwards in frequency
        out[:, b] = np.maximum(out[:, b], out[:, b - 1] * a_up)
    for b in range(n - 2, -1, -1):              # and downwards
        out[:, b] = np.maximum(out[:, b], out[:, b + 1] * a_dn)
    return out


class Ear:
    """The model above, ready to run on signals at one sample rate."""

    def __init__(self, sr, n_fft=N_FFT, hop=HOP, n_bands=N_BANDS):
        self.sr, self.n_fft, self.hop = sr, n_fft, hop
        self.M, self.centres = band_matrix(sr, n_fft, n_bands)
        self.w = loudness_weight(self.centres)
        self.win = np.hanning(n_fft)
        self.gain = 10 ** (self.w / 20.0)

    def excitation(self, x):
        """A signal as band loudnesses over time."""
        x = np.asarray(x, float)
        if x.ndim > 1:
            x = x.mean(axis=1)
        n = max(0, (len(x) - self.n_fft) // self.hop + 1)
        P = np.zeros((n, self.M.shape[0]))
        for i in range(n):
            seg = x[i * self.hop:i * self.hop + self.n_fft] * self.win
            S = np.abs(np.fft.rfft(seg)) ** 2
            P[i] = self.M @ S
        P = spread(P) * self.gain
        # loudness ~ the cube root of intensity, with a floor: below it,
        # differences are differences between two silences
        floor = (10 ** (FLOOR_DB / 10.0)) * max(1e-20, P.max())
        return np.maximum(P, floor) ** 0.3


# ---------------------------------------------------------------
# the pitch domain
# ---------------------------------------------------------------
P_FFT, P_HOP = 4096, 882        # 93 ms, 20 ms apart: pitch needs the window
P_LO, P_HI = 55.0, 3520.0
P_CENTS = 20.0
P_HARM = 8


class Pitch:
    """A harmonic-sum pitchgram: what notes are sounding, not what timbre.

    The band model above is dominated by the one error a chip cannot fix.
    Measured: a square standing in for a sawtooth differs from it by 3.5 in
    the 215 Hz band, while removing the melody entirely changes the 1 kHz
    band by 0.7 - so a distance over bands is mostly a statement about
    timbre, and it scored a correct arrangement 82.6% against 78.2% for one
    with no melody at all. Four points is not enough to steer anything.

    A harmonic sum puts a square and a sawtooth at the same note in nearly
    the same place, so what is left is the notes. Its own blind spot is the
    octave - a note at f/2 supplies energy at f, 2f, 3f and so lights up
    the candidate at f too, and measured on its own this model scored an
    octave-wrong melody ABOVE a correct one. That is why the two are used
    together: they are blind to different things.
    """

    def __init__(self, sr, n_fft=P_FFT, hop=P_HOP):
        self.sr, self.n_fft, self.hop = sr, n_fft, hop
        fr = np.fft.rfftfreq(n_fft, 1.0 / sr)
        self.step = fr[1] - fr[0]
        n = int(round(1200 * np.log2(P_HI / P_LO) / P_CENTS)) + 1
        self.cand = P_LO * 2 ** (np.arange(n) * P_CENTS / 1200.0)
        self.hb = np.array([[int(round(f * k / self.step))
                             for k in range(1, P_HARM + 1)]
                            for f in self.cand])
        self.wt = np.array([1.0 / k for k in range(1, P_HARM + 1)])
        self.elw = 10 ** (loudness_weight(self.cand) / 20.0)
        self.win = np.hanning(n_fft)

    def pitchgram(self, x):
        x = np.asarray(x, float)
        if x.ndim > 1:
            x = x.mean(axis=1)
        n = max(0, (len(x) - self.n_fft) // self.hop + 1)
        out = np.zeros((n, len(self.cand)))
        for i in range(n):
            S = np.abs(np.fft.rfft(x[i * self.hop:i * self.hop + self.n_fft]
                                   * self.win))
            pad = np.concatenate([S, np.zeros(2)])
            acc = np.zeros(len(self.cand))
            for k in range(P_HARM):
                b = np.clip(self.hb[:, k], 0, len(S) - 1)
                acc += self.wt[k] * np.maximum(
                    pad[b], np.maximum(pad[b - 1], pad[b + 1]))
            out[i] = acc * self.elw
        floor = max(1e-20, out.max()) * 10 ** -3.5
        return np.maximum(out, floor) ** 0.5


def fit_gain(a, b):
    """One scalar on b's amplitude that best matches a's loudness."""
    ea, eb = float(np.sqrt((a ** 2).mean())), float(np.sqrt((b ** 2).mean()))
    return (ea / eb) if eb > 1e-12 else 1.0


def _fit(R, C, Z, hop, sr, segment):
    """One representation's fit, overall and per segment."""
    m = min(len(R), len(C), len(Z))
    R, C, Z = R[:m], C[:m], Z[:m]
    per = max(1, int(round(segment * sr / hop)))
    out = []
    for i in range(0, m, per):
        d = float(np.abs(R[i:i + per] - C[i:i + per]).mean())
        d0 = float(np.abs(R[i:i + per] - Z[i:i + per]).mean())
        out.append((i * hop / float(sr),
                    max(0.0, 1.0 - d / d0) if d0 > 1e-12 else 1.0))
    d = float(np.abs(R - C).mean())
    d0 = float(np.abs(R - Z).mean())
    return (max(0.0, 1.0 - d / d0) if d0 > 1e-12 else 1.0), out


class Model:
    """Both representations, built once and reused."""

    def __init__(self, sr):
        self.sr = sr
        self.ear = Ear(sr)
        self.pitch = Pitch(sr)

    def prepare(self, ref):
        """Everything about the reference that does not change."""
        ref = np.asarray(ref, float)
        if ref.ndim > 1:
            ref = ref.mean(axis=1)
        z = np.zeros(len(ref))
        return {"ref": ref,
                "R_band": self.ear.excitation(ref),
                "R_pitch": self.pitch.pitchgram(ref),
                "Z_band": self.ear.excitation(z),
                "Z_pitch": self.pitch.pitchgram(z)}


def compare(ref, cand, sr, segment=2.0, model=None, prepared=None):
    """Per-segment fit, as a fraction, plus the whole-signal figure.

    The two representations are averaged. Returns (overall, [(t, fit)..]).
    """
    model = model or Model(sr)
    prep = prepared or model.prepare(ref)
    cand = np.asarray(cand, float)
    if cand.ndim > 1:
        cand = cand.mean(axis=1)
    r = prep["ref"]
    n = min(len(r), len(cand))
    cand = cand[:n] * fit_gain(r[:n], cand[:n])  # once, not per segment
    b_all, b_seg = _fit(prep["R_band"], model.ear.excitation(cand),
                        prep["Z_band"], model.ear.hop, sr, segment)
    p_all, p_seg = _fit(prep["R_pitch"], model.pitch.pitchgram(cand),
                        prep["Z_pitch"], model.pitch.hop, sr, segment)
    k = min(len(b_seg), len(p_seg))
    per = [(b_seg[i][0], 0.5 * (b_seg[i][1] + p_seg[i][1])) for i in range(k)]
    return 0.5 * (b_all + p_all), per


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip())
        return 2
    import soundfile as sf
    a, sr = sf.read(argv[1], dtype="float32")
    b, sr2 = sf.read(argv[2], dtype="float32")
    if sr2 != sr:
        print("  sample rates differ: %d and %d" % (sr, sr2))
        return 1
    seg = float(argv[3]) if len(argv) > 3 else 2.0
    overall, per = compare(a, b, sr, seg)
    print("  overall fit   %.1f%%" % (100 * overall))
    v = np.array([q for _t, q in per])
    print("  per %.0f s      worst %.1f%%  median %.1f%%  best %.1f%%"
          % (seg, 100 * v.min(), 100 * np.median(v), 100 * v.max()))
    print()
    print("  the ten worst segments")
    for t, q in sorted(per, key=lambda p: p[1])[:10]:
        print("    %6.1f s   %5.1f%%" % (t, 100 * q))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
