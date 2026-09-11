#!/usr/bin/env python3
"""An original cue, synthesised at full fidelity, for the arranger to eat.

    python3 tests/mkdemosource.py

Nothing chip-like about it: saw waves through a filter, a sine sub, band
passed noise for the metal hits, a pad, a lead with vibrato. The point
is to give arrange.py something that is NOT six squares, so that what
comes out the other side shows what the reduction really costs.

Written by Claude (Opus) for the Z80AIexperiments repo.
"""
import numpy as np

SR = 44100
BPM = 96.0
BEAT = 60.0 / BPM
BARS = 8
DUR = BARS * 4 * BEAT

D2, D3, F3, A3, D4, F4, G4, A4, C5 = (73.42, 146.83, 174.61, 220.0,
                                      293.66, 349.23, 392.0, 440.0, 523.25)


def t_of(n):
    return int(round(n * SR))


def saw(f, n, phase=0.0, harmonics=24):
    t = np.arange(n) / float(SR)
    out = np.zeros(n)
    for h in range(1, harmonics + 1):
        if f * h > SR / 2.2:
            break
        out += np.sin(2 * np.pi * f * h * t + phase) / h
    return out * (2.0 / np.pi)


def sine(f, n, fm=None, depth=0.0):
    t = np.arange(n) / float(SR)
    p = 2 * np.pi * f * t
    if fm:
        p += depth * np.sin(2 * np.pi * fm * t)
    return np.sin(p)


def lp(x, cut):
    """One pole, per sample - cheap and it sounds like a filter."""
    a = np.exp(-2 * np.pi * cut / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = acc * a + x[i] * (1 - a)
        y[i] = acc
    return y


def bp(x, f, q=12.0):
    """A resonant band pass, two poles, for the metal."""
    w = 2 * np.pi * f / SR
    r = 1 - w / (2 * q)
    a1 = 2 * r * np.cos(w)
    a2 = -r * r
    y = np.zeros(len(x))
    for i in range(2, len(x)):
        y[i] = x[i] - x[i - 2] + a1 * y[i - 1] + a2 * y[i - 2]
    return y


def env(n, a, d, s=1.0, r=0.0):
    e = np.ones(n)
    na, nd, nr = t_of(a), t_of(d), t_of(r)
    if na:
        e[:na] = np.linspace(0, 1, na)
    if nd:
        e[na:na + nd] = np.linspace(1, s, min(nd, n - na))
    e[na + nd:] = s
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def clang(n, root=420.0):
    """Struck metal: inharmonic partials and a noise crack over the top."""
    rng = np.random.RandomState(7)
    t = np.arange(n) / float(SR)
    out = np.zeros(n)
    for k, (mult, lvl, dec) in enumerate([(1.0, 1.0, 7.0), (2.76, 0.7, 9.0),
                                          (5.40, 0.45, 12.0),
                                          (8.93, 0.3, 16.0),
                                          (13.3, 0.2, 20.0)]):
        out += lvl * np.sin(2 * np.pi * root * mult * t) * np.exp(-dec * t)
    crack = bp(rng.randn(n), root * 3.2, 6.0) * np.exp(-35 * t)
    return 0.55 * out + 0.5 * crack


def hat(n):
    rng = np.random.RandomState(11)
    t = np.arange(n) / float(SR)
    return bp(rng.randn(n), 7200.0, 3.0) * np.exp(-90 * t)


def mix_into(buf, x, at, gain=1.0):
    i = t_of(at)
    j = min(len(buf), i + len(x))
    if i < len(buf):
        buf[i:j] += gain * x[:j - i]


def build():
    n = t_of(DUR) + SR
    L = np.zeros(n)
    R = np.zeros(n)

    # the ostinato: eighths, a sub sine under a filtered saw
    for b in range(BARS * 8):
        at = b * BEAT / 2.0
        if b % 8 in (3, 7):                     # two gaps a bar, for the lilt
            continue
        ln = t_of(BEAT * 0.42)
        acc = 1.0 if b % 8 in (0, 4) else 0.62
        f = D2 if b % 16 not in (10, 11, 14) else D2 * 1.1892    # up a tone
        v = (0.55 * lp(saw(f, ln), 520) + 0.8 * sine(f / 2, ln)) \
            * env(ln, 0.004, 0.08, 0.45, 0.10) * acc
        mix_into(L, v, at, 0.9)
        mix_into(R, v, at, 0.9)

    # the metal, on one and on the back of three
    for bar in range(BARS):
        for beat, g, rt in ((0.0, 1.0, 420.0), (2.5, 0.7, 560.0)):
            ln = t_of(1.1)
            c = clang(ln, rt)
            at = bar * 4 * BEAT + beat * BEAT
            mix_into(L, c, at, 0.5 * g * (1.15 if beat else 1.0))
            mix_into(R, c, at, 0.5 * g * (0.85 if beat else 1.0))

    # hats on the sixteenths, quiet and panned
    for s in range(BARS * 16):
        at = s * BEAT / 4.0
        ln = t_of(0.07)
        g = 0.22 if s % 4 == 2 else 0.12
        h = hat(ln) * g
        mix_into(L, h, at, 1.0 if s % 2 else 0.6)
        mix_into(R, h, at, 0.6 if s % 2 else 1.0)

    # the lead, from bar three: four notes, with vibrato, filtered
    tune = [(D4, 1.5), (F4, 0.5), (A4, 1.0), (G4, 1.0),
            (F4, 1.5), (D4, 0.5), (C5, 1.0), (A4, 1.0)]
    at = 2 * 4 * BEAT
    for rep in range(2):
        for f, beats in tune:
            ln = t_of(BEAT * beats * 0.92)
            tt = np.arange(ln) / float(SR)
            vib = 1.0 + 0.006 * np.sin(2 * np.pi * 5.2 * tt) * \
                np.minimum(1.0, tt / 0.35)
            v = lp(saw(f, ln) * vib, 2400) * env(ln, 0.03, 0.25, 0.7, 0.12)
            mix_into(L, v, at, 0.42 if rep else 0.36)
            mix_into(R, v, at, 0.36 if rep else 0.42)
            at += BEAT * beats
        at += 0

    # a pad under the second half
    for bar in range(4, BARS):
        ln = t_of(4 * BEAT)
        chord = (D3, F3, A3) if bar < 6 else (D3, F3, G4 / 2)
        p = np.zeros(ln)
        for f in chord:
            p += lp(saw(f * 0.999, ln), 900) + lp(saw(f * 1.001, ln), 900)
        p *= env(ln, 0.6, 0.2, 0.9, 0.5) * 0.085
        mix_into(L, p, bar * 4 * BEAT, 1.0)
        mix_into(R, p, bar * 4 * BEAT, 1.0)

    out = np.stack([L, R], axis=1)
    out = out[:t_of(DUR + 0.8)]
    out /= np.abs(out).max() / 0.92
    return out


if __name__ == "__main__":
    import soundfile as sf
    y = build()
    sf.write("/tmp/cue.wav", y, SR)
    print("/tmp/cue.wav  %.2f s" % (len(y) / float(SR)))
