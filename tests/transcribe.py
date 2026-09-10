"""Audio to a score: bass, lead, chords and drums, on a beat grid.

arrange.py fits the spectrum frame by frame and knows nothing about
parts, which is why six channels go on whatever is loudest and the
result is a wash. This does the other thing: work out what the piece is
made of, throw most of it away, and keep the four lines a chip can
actually play.

    tempo       from the autocorrelation of the spectral flux, with the
                beat phase from a pulse train
    bass        a harmonic sum in 40..200 Hz, median filtered, quantised
                to semitones and to the grid
    lead        the same in 250..2000 Hz, with the bass's harmonics taken
                out first so it does not follow the bass around
    chords      a twelve bin chroma a beat, matched against major and
                minor triads
    drums       onsets classified by where their energy is: low for a
                kick, mid plus high for a snare, high only for a hat

Everything is quantised and minimum lengths imposed, because the point
is to SIMPLIFY. A chip arrangement that follows every nuance sounds like
mud; one that plays four clean lines sounds like music.
"""
import math

import numpy as np

A4 = 440.0


def stft(x, sr, win=4096, hop=441):
    w = np.hanning(win)
    n = max(0, (len(x) - win) // hop + 1)
    out = np.empty((n, win // 2 + 1))
    for i in range(n):
        out[i] = np.abs(np.fft.rfft(x[i * hop:i * hop + win] * w))
    return out, np.fft.rfftfreq(win, 1.0 / sr)


def hpss(mag, t_ker=17, f_ker=17):
    """Split sustained from percussive, by two median filters.

    A median along TIME keeps what holds still and removes clicks; a
    median along FREQUENCY keeps what is broadband and removes tones.
    That is the whole of harmonic/percussive separation, and without it
    the lead tracker follows the drums - measured on a cue whose metal
    hits ring at 420 and 560 Hz, the lead came back as 415 and 554.
    """
    H = np.empty_like(mag)
    P = np.empty_like(mag)
    h = t_ker // 2
    for i in range(mag.shape[0]):
        lo, hi = max(0, i - h), min(mag.shape[0], i + h + 1)
        H[i] = np.median(mag[lo:hi], axis=0)
    h = f_ker // 2
    for b in range(mag.shape[1]):
        lo, hi = max(0, b - h), min(mag.shape[1], b + h + 1)
        P[:, b] = np.median(mag[:, lo:hi], axis=1)
    tot = H + P + 1e-12
    return mag * (H / tot), mag * (P / tot)


def flux(mag):
    """Spectral flux: how much louder things got, summed."""
    d = np.diff(mag, axis=0)
    d[d < 0] = 0
    f = d.sum(axis=1)
    return np.concatenate([[0.0], f])


def tempo_of(fl, hz, lo=80.0, hi=170.0):
    """Beats a minute, and where the beats fall."""
    f = fl - fl.mean()
    ac = np.correlate(f, f, "full")[len(f) - 1:]
    lags = np.arange(len(ac))
    ok = (lags > hz * 60.0 / hi) & (lags < hz * 60.0 / lo)
    if not ok.any():
        return 120.0, 0
    lag = int(np.argmax(np.where(ok, ac, -1e30)))
    # A tempo estimate is routinely out by a factor of two or of three
    # halves - a dotted pulse looks exactly like a beat to an
    # autocorrelation - so try the relatives and keep whichever pulse
    # train actually lines up best per pulse, inside a sane range.
    cands = set()
    for mult in (0.5, 2.0 / 3, 1.0, 1.5, 2.0):
        L = int(round(lag * mult))
        if L > 3 and lo <= 60.0 * hz / L <= hi:
            cands.add(L)
    best = None
    for L in sorted(cands):
        bpm = 60.0 * hz / L
        prior = math.exp(-0.5 * (math.log(bpm / 110.0) / 0.45) ** 2)
        for p in range(L):
            pulses = fl[p::L]
            if not len(pulses):
                continue
            score = prior * pulses.mean() / max(1e-12, fl.mean())
            if best is None or score > best[0]:
                best = (score, L, p)
    if best is None:
        return 60.0 * hz / lag, 0
    return 60.0 * hz / best[1], best[2]


def salience(mag, fr, lo, hi, partials=5, weight=0.8):
    """Harmonic sum: the pitch most of the energy is a harmonic of."""
    k = np.where((fr >= lo) & (fr <= hi))[0]
    out = np.zeros((len(mag), len(k)))
    for j, f in enumerate(fr[k]):
        acc = np.zeros(len(mag))
        for h in range(1, partials + 1):
            b = int(round(f * h / (fr[1] - fr[0])))
            if b < mag.shape[1]:
                acc += (weight ** (h - 1)) * mag[:, b]
        out[:, j] = acc
    return out, fr[k]


def track_bass(x, sr, rate, lo=45.0, hi=170.0, win=16384, thresh=0.12):
    """Bass pitch from a long window, by harmonic sum.

    Autocorrelation is the obvious tool and it is the wrong one: a periodic
    signal correlates as well at 2T as at T, so the peak picked is an octave
    out as often as not, and no tie-break on lag length fixes both directions
    (preferring the long lag reads D2 as D1, preferring the short one reads
    it as D3 - both were measured here).

    A 16,384-sample window is a 2.7 Hz bin, which is 1.1 semitones at the
    bottom of the bass and half of one at the top, and a sum over five
    harmonics settles the octave from where the energy actually is rather
    than from a tie. Parabolic interpolation on the winning bin takes the
    pitch the rest of the way.
    """
    hop = int(round(sr / float(rate)))
    n = max(0, (len(x) - win) // hop + 1)
    w = np.hanning(win)
    fr = np.fft.rfftfreq(win, 1.0 / sr)
    step = fr[1] - fr[0]
    top = int(hi * 5.2 / step) + 2              # five harmonics, and a little
    cand = np.arange(int(lo / step), int(hi / step) + 1)
    def at(S, k):
        k = int(round(k))
        return float(S[max(0, k - 2):k + 3].max()) if 0 <= k < len(S) else 0.0

    out = np.zeros(n)
    strength = np.zeros(n)
    for i in range(n):
        seg = x[i * hop:i * hop + win]
        if not seg.size or float(seg @ seg) <= 1e-12:
            continue                            # silence has no pitch, and
        S = np.abs(np.fft.rfft(seg * w))[:top]  # argmax of zeros is bin zero
        if not S.size:
            continue
        sal = np.zeros(len(cand))
        for h in range(1, 6):
            k = cand * h
            ok = k < len(S)
            sal[ok] += S[k[ok]] / h             # later harmonics weigh less
        j = int(np.argmax(sal))
        k = cand[j]
        # the octave question. The sum above is pulled to whichever partial
        # is loudest, and in a mix whose bass fundamental is rolled off that
        # is the second harmonic. What settles it is the ODD harmonics of
        # the note an octave down - 3f/2 and 5f/2 are not harmonics of f at
        # all, so energy there can only come from the lower note really
        # being played. (Measured on the same file: at 6 s the ladder runs
        # 65.4 / 130.8 / 196 / 261.6 with nothing at 98, which is C2 with a
        # quiet fundamental, not C3 with a rumble underneath.)
        while k / 2.0 * step >= lo:
            half = k / 2.0
            odd = max(at(S, half * 3), at(S, half * 5))
            if at(S, half) < 0.05 * at(S, k) or odd < 0.05 * at(S, k):
                break
            k = int(round(half))
        if 0 < k < len(S) - 1:
            a0, b0, c0 = S[k - 1], S[k], S[k + 1]
            den = a0 - 2 * b0 + c0
            k = k + (0.5 * (a0 - c0) / den if den else 0.0)
        out[i] = k * step
        strength[i] = sal[j]
    if strength.max() > 0:
        out[strength < thresh * strength.max()] = 0.0
    med = out.copy()                            # median filter over the gaps
    for i in range(n):
        v = [q for q in out[max(0, i - 2):i + 3] if q > 0]
        med[i] = float(np.median(v)) if len(v) >= 2 else 0.0
    return med


def track(mag, fr, lo, hi, thresh=0.08, smooth=5):
    """One pitch a frame, or zero: the strongest harmonic sum, smoothed.

    A harmonic sum will happily pick a SUBHARMONIC - every harmonic of
    f/2 that matters is also a harmonic of f - so each candidate is
    checked against the spectrum at its own fundamental, and an octave up
    wins if that is where the energy actually is.
    """
    sal, fs = salience(mag, fr, lo, hi)
    peak = sal.max(axis=1)
    idx = sal.argmax(axis=1)
    f0 = fs[idx]
    step = fr[1] - fr[0]
    for i in range(len(f0)):
        f = f0[i]
        if f <= 0:
            continue
        best, bf = None, f
        for mult in (1.0, 2.0, 3.0):
            g = f * mult
            b = int(round(g / step))
            if b >= mag.shape[1] or g > hi * 1.5:
                continue
            here = mag[i, max(0, b - 1):b + 2].max()
            j = int(np.argmin(np.abs(fs - g))) if len(fs) else 0
            s_here = sal[i, j] if g <= fs[-1] else 0.0
            score = here * (0.6 + 0.4 * s_here / max(1e-12, peak[i]))
            if best is None or score > best * 1.25:     # only if clearly better
                best, bf = score, g
        f0[i] = bf
    gate = peak < thresh * peak.max()
    f0[gate] = 0.0
    out = f0.copy()                             # median filter, ignoring gaps
    h = smooth // 2
    for i in range(len(f0)):
        w = [v for v in f0[max(0, i - h):i + h + 1] if v > 0]
        out[i] = float(np.median(w)) if len(w) > h else 0.0
    return out


def to_midi(f):
    return 0 if f <= 0 else 69 + 12 * math.log(f / A4, 2)


def from_midi(m):
    return A4 * 2 ** ((m - 69) / 12.0)


def track_viterbi(mag, fr, lo, hi, thresh=0.10, jump=2.0):
    """The most likely pitch PATH, not the loudest bin a frame.

    Without continuity a lead tracker follows whatever rings loudest,
    which on a cue full of struck metal means it plays the metal. A
    transition penalty in semitones fixes it, and it costs one pass
    forward and one back.
    """
    sal, fs = salience(mag, fr, lo, hi)
    sal = sal / np.maximum(1e-12, sal.max())
    semis = np.array([to_midi(f) for f in fs])
    n, m = sal.shape
    score = np.full((n, m + 1), -1e30)       # the last state is "silent"
    back = np.zeros((n, m + 1), dtype=np.int32)
    score[0, :m] = sal[0]
    score[0, m] = thresh
    for i in range(1, n):
        prev = score[i - 1]
        best_silent = prev[m]
        for j in range(m):
            cand = prev[:m] - jump * np.abs(semis - semis[j])
            k = int(np.argmax(cand))
            a, b = cand[k], best_silent - 0.5
            if a >= b:
                score[i, j], back[i, j] = a + sal[i, j], k
            else:
                score[i, j], back[i, j] = b + sal[i, j], m
        k = int(np.argmax(prev[:m]))
        stay = prev[m]
        leave = prev[k] - 0.5
        score[i, m] = max(stay, leave) + thresh
        back[i, m] = m if stay >= leave else k
    path = np.zeros(n, dtype=np.int32)
    path[-1] = int(np.argmax(score[-1]))
    for i in range(n - 1, 0, -1):
        path[i - 1] = back[i, path[i]]
    return np.array([0.0 if p == m else fs[p] for p in path])


def notes_of(f0, hz, grid, min_frames=3, max_jump=14):
    """A pitch track as notes: quantised to semitones and to the grid."""
    mid = np.array([to_midi(v) for v in f0])
    q = np.where(mid > 0, np.round(mid), 0)
    # snap starts to the grid and drop anything too short
    out = []
    i = 0
    while i < len(q):
        if q[i] <= 0:
            i += 1
            continue
        j = i
        while j < len(q) and q[j] > 0 and abs(q[j] - q[i]) <= 1:
            j += 1
        if j - i >= min_frames:
            start = int(round((i - grid[0]) / grid[1])) * grid[1] + grid[0]
            start = max(0, start)
            length = max(min_frames, int(round((j - i) / grid[1])) * grid[1])
            pitch = int(np.median([v for v in q[i:j] if v > 0]))
            if out and start < out[-1][0] + out[-1][1]:
                out[-1] = (out[-1][0], start - out[-1][0], out[-1][2])
            if not out or abs(pitch - out[-1][2]) <= max_jump or True:
                out.append((start, length, pitch))
        i = j
    return [n for n in out if n[1] >= min_frames]


CHROMA_MAJOR = np.array([1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0], float)
CHROMA_MINOR = np.array([1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0], float)


def chords_of(mag, fr, hz, beat_frames, phase, lo=150.0, hi=2000.0,
              per_chord=2, melody=()):
    """One triad every `per_chord` beats, from a chroma profile."""
    k = np.where((fr >= lo) & (fr <= hi))[0]
    pc = np.zeros((len(mag), 12))
    for b in k:
        m = to_midi(fr[b])
        if m <= 0:
            continue
        pc[:, int(round(m)) % 12] += mag[:, b]
    out = []
    step = int(round(beat_frames * per_chord))
    for start in range(phase, len(mag) - step, step):
        v = pc[start:start + step].sum(axis=0)
        if v.sum() <= 0:
            continue
        v = v / v.sum()
        best = None
        for root in range(12):
            t = np.roll(np.array([1, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 0], float),
                        root)                   # root, both thirds, fifth
            score = float((v * t).sum())
            if best is None or score > best[0]:
                best = (score, root)
        root = best[1]
        # The quality is one interval, and the best evidence about it is not
        # the chroma - a sawtooth on D puts a strong fifth harmonic on F# and
        # votes for D major - but the notes actually transcribed in this span,
        # which are clean.
        minor = major = 0.0
        for nstart, nlen, pitch in melody:
            if nstart + nlen <= start or nstart >= start + step:
                continue
            klass = int(pitch) % 12         # not pc: that is the chroma
            if klass == (root + 3) % 12:
                minor += nlen
            elif klass == (root + 4) % 12:
                major += nlen
        if minor == major == 0:                 # nothing played a third
            minor, major = v[(root + 3) % 12], v[(root + 4) % 12]
        out.append((start, step, root, "m" if minor >= major else ""))
    return out


def drums_of(mag, fr, fl, hz, thresh=0.25, grid=None):
    """Onsets, and what kind of hit each one is.

    The kind is decided on how much each band *rises* at the onset, per bin,
    not on how much energy it holds: absolute sums let a sustained hi-hat and
    a band three octaves wide outvote the hit being classified.
    """
    pk = []
    f = fl / max(1e-12, fl.max())
    for i in range(2, len(f) - 2):
        if f[i] == max(f[i - 2:i + 3]) and f[i] > thresh:
            if not pk or i - pk[-1] >= 4:
                pk.append(i)
    bands = {}
    for name, (lo, hi) in (("low", (40, 140)), ("mid", (160, 1200)),
                           ("high", (3000, 12000))):
        k = np.where((fr >= lo) & (fr < hi))[0]
        bands[name] = mag[:, k].mean(axis=1) if len(k) else np.zeros(len(mag))
    out = []
    for i in pk:
        rise = {}
        for name, b in bands.items():
            before = b[max(0, i - 3):max(1, i - 1)].min() if i >= 2 else b[i]
            rise[name] = max(0.0, b[i] - before)
        tot = sum(rise.values()) + 1e-12
        if rise["low"] / tot > 0.35:
            kind = "kick"
        elif rise["high"] / tot > 0.55:
            kind = "hat"
        else:
            kind = "snare"
        out.append((i, kind, float(min(1.0, f[i] / max(1e-9, f.max())))))
    if grid is not None:
        out = snap(out, grid)
    return out


def snap(hits, grid):
    """Onsets onto the sixteenth grid, loudest wins a shared slot.

    A drum machine is on the grid and a chip part has to be: off-grid hits
    read as mistakes rather than as feel, and two hits a frame apart read as
    one flam nobody played.
    """
    off, step = grid
    best = {}
    for i, kind, vel in hits:
        slot = int(round((i - off) / float(step)))
        at = off + slot * step
        if abs(at - i) > step // 2 + 1:
            at = i
        if slot not in best or vel > best[slot][2]:
            best[slot] = (max(0, at), kind, vel)
    return [best[k] for k in sorted(best)]


def key_quality(chords):
    """One quality per root across the whole piece.

    A window decides major or minor on whichever third happens to sound in
    it, so an intro with no third in it comes out major by default and the
    arpeggio plays the wrong mode for two bars. Music does not change mode
    that often: let the weight of the whole piece settle each root.
    """
    vote = {}
    for _start, length, root, kind in chords:
        a, b = vote.get(root, (0, 0))
        vote[root] = (a + (length if kind == "m" else 0),
                      b + (length if kind == "" else 0))
    return [(st, ln, root, "m" if vote[root][0] >= vote[root][1] else "")
            for st, ln, root, _k in chords]


def transcribe(x, sr, rate=50):
    """Everything above, on one piece of audio."""
    hop = int(round(sr / float(rate)))
    mono = x.mean(axis=1) if x.ndim > 1 else x
    mag, fr = stft(mono, sr, 4096, hop)
    mag /= max(1e-12, mag.max())
    harm, perc = hpss(mag)
    fl = flux(perc)                     # onsets from the percussive part
    bpm, phase = tempo_of(fl, rate)
    beat = 60.0 * rate / bpm
    grid = (phase % max(1, int(round(beat / 4))), max(1, int(round(beat / 4))))
    bass = track_bass(mono, sr, rate)
    # take the bass's harmonics off before looking for the lead
    lead_mag = harm.copy()
    for i, f in enumerate(bass):
        if f <= 0:
            continue
        for h in range(1, 7):
            b = int(round(f * h / (fr[1] - fr[0])))
            if b < lead_mag.shape[1]:
                lead_mag[i, max(0, b - 1):b + 2] *= 0.25
    lead = track_viterbi(lead_mag, fr, 250.0, 1600.0)
    bass_notes = notes_of(bass, rate, grid, 3)
    lead_notes = notes_of(lead, rate, grid, 3)
    chords = key_quality(chords_of(lead_mag, fr, rate, beat, phase,
                                   melody=lead_notes + bass_notes))
    return {"bpm": bpm, "beat": beat, "grid": grid, "rate": rate,
            "frames": len(mag), "harm": harm, "perc": perc, "fr": fr,
            "bass": bass_notes,
            "lead": lead_notes,
            "chords": chords,
            "drums": drums_of(perc, fr, fl, rate, grid=grid),
            "flux": fl}
