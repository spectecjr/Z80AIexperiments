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


def onset_peaks(fl, thresh=0.12, rel=0.22, half=50, min_gap=4):
    """Where the onsets are: local maxima of the flux, over a local floor."""
    f = fl / max(1e-12, fl.max())
    local = np.array([np.median(f[max(0, i - half):i + half + 1])
                      for i in range(len(f))])
    out = []
    for i in range(2, len(f) - 2):
        if f[i] != max(f[i - 2:i + 3]):
            continue
        if f[i] < thresh or f[i] < local[i] + rel * (1.0 - local[i]):
            continue
        if not out or i - out[-1] >= min_gap:
            out.append(i)
    return out


def tempo_of(fl, hz, lo=70.0, hi=240.0, tol=1.0, fine=0.25):
    """The grid the onsets actually land on, and its phase.

    Scored by what the grid EXPLAINS: the fraction of detected onsets within
    `tol` frames of it, less the fraction a grid that fine would catch by
    luck. A finer grid always catches more for nothing - at a sixteenth of
    7.03 frames, three positions in every seven qualify by chance, 42.7% -
    so the excess over chance is the only honest score, and without it the
    search runs away to the fastest tempo in the range.

    The whole range is scanned rather than the relatives of an
    autocorrelation peak. Both of the previous versions got a recording
    wrong whose own MIDI says 160 bpm: the first returned 106.7, out by
    exactly three halves because a dotted pulse looks like a beat to an
    autocorrelation and a log-normal prior at 110 bpm then preferred the
    slower reading - 31% of that recording's onsets landed on the grid it
    chose. The second refined the autocorrelation's own peak and reached
    157.9 bpm, which sounds close and is not: over 198 seconds a 1.3%
    period error drifts 127 frames, so the grid is in antiphase long before
    the end, and it scored 49%. A third recording needed 130 bpm, which is
    not a simple multiple of any autocorrelation peak at all, so no
    candidate set built from one could reach it.

    The tempo's OCTAVE is not decidable from onsets and does not need to be.
    This returns the tightest grid that explains them: on that recording,
    onsets land on multiples of 9.375 frames, which is 80 bpm counted in
    sixteenths and the 160 bpm of the MIDI counted in eighths. Both are true;
    the grid is the same either way, and the grid is what gets used.
    """
    onsets = onset_peaks(fl)
    if len(onsets) < 8:
        f = fl - fl.mean()
        ac = np.correlate(f, f, "full")[len(f) - 1:]
        lags = np.arange(len(ac))
        ok = (lags > hz * 60.0 / hi) & (lags < hz * 60.0 / lo)
        if not ok.any():
            return 120.0, 0
        return 60.0 * hz / int(np.argmax(np.where(ok, ac, -1e30))), 0
    ons = np.asarray(onsets, float)
    best = None
    for bpm in np.arange(lo, hi + fine, fine):
        step = 60.0 * hz / bpm / 4.0            # onsets land on sixteenths
        if step <= 2 * tol:
            continue
        phases = np.arange(0.0, step, 0.25)
        d = np.mod(ons[None, :] - phases[:, None], step)
        d = np.minimum(d, step - d)
        hits = (d <= tol).mean(axis=1)
        k = int(np.argmax(hits))
        score = hits[k] - min(1.0, (2 * tol + 1.0) / step)
        if best is None or score > best[0]:
            best = (score, bpm, phases[k], hits[k])
    if best is None:
        return 120.0, 0
    return float(best[1]), int(round(best[2]))


def refine_peak(S, k):
    """Sub-bin position of the peak at bin k, by parabola.

    The correction is clamped to half a bin: if k is not actually a local
    maximum the parabola can point anywhere at all, including at negative
    frequencies, and a frequency of -3 Hz is a crash two functions later.
    """
    if not (0 < k < len(S) - 1):
        return float(k)
    a, b, c = float(S[k - 1]), float(S[k]), float(S[k + 1])
    den = a - 2 * b + c
    if den == 0.0:
        return float(k)
    return k + max(-0.5, min(0.5, 0.5 * (a - c) / den))


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


def track_bass(x, sr, rate, lo=36.0, hi=170.0, win=16384, thresh=0.12,
               cents_per_step=15.0, oct_ratio=0.05, min_fund=0.0,
               mode_frames=41):
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
    # A LOGARITHMIC candidate grid, not the FFT's own bins. At 16,384 samples
    # a bin is 2.7 Hz, which up at 300 Hz is a sixth of a semitone but down at
    # 58 Hz is four fifths of one - so a candidate set of integer bins cannot
    # even name the note, and a measured B1 came back as A#1, a semitone
    # flat, on every frame it sounded.
    n_cand = int(round(1200 * math.log(hi / lo, 2) / cents_per_step)) + 1
    cand_hz = lo * 2 ** (np.arange(n_cand) * cents_per_step / 1200.0)
    # each harmonic of each candidate, as a bin, with its neighbours: a
    # candidate a few cents off still has to collect its own energy
    hbins = np.array([[int(round(f * h / step)) for h in range(1, 6)]
                      for f in cand_hz])

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
        pad = np.concatenate([S, np.zeros(3)])
        sal = np.zeros(n_cand)
        for h in range(5):
            b = np.clip(hbins[:, h], 0, len(S) - 1)
            near = np.maximum(np.maximum(pad[b - 1], pad[b]), pad[b + 1])
            sal += near / (h + 1.0)             # later harmonics weigh less
        # A candidate an octave below a real note scores well on any
        # harmonic sum, because every harmonic of the note is also a
        # harmonic of the half - and the odd-harmonic test cannot save it in
        # a full mix, where other instruments supply energy at 3f/2 and 5f/2.
        # Measured against a score: the bass came back one or two octaves
        # low with the right pitch class, and disabling the octave descent
        # entirely changed nothing, because the sum was picking the
        # subharmonic outright. So a candidate must HAVE a fundamental: its
        # own first partial, against the loudest partial it claims.
        if min_fund > 0:
            first = np.maximum(pad[np.clip(hbins[:, 0], 0, len(S) - 1)],
                               0.0)
            loudest = np.zeros(n_cand)
            for h in range(5):
                b = np.clip(hbins[:, h], 0, len(S) - 1)
                loudest = np.maximum(loudest, pad[b])
            sal = np.where(first >= min_fund * loudest, sal, 0.0)
            if sal.max() <= 0:
                continue
        j = int(np.argmax(sal))
        f = cand_hz[j]
        # the octave question. The sum above is pulled to whichever partial
        # is loudest, and in a mix whose bass fundamental is rolled off that
        # is the second harmonic. What settles it is the ODD harmonics of
        # the note an octave down - 3f/2 and 5f/2 are not harmonics of f at
        # all, so energy there can only come from the lower note really
        # being played. (Measured on a real recording: at 6 s the ladder ran
        # 65.4 / 130.8 / 196 / 261.6 with nothing at 98, which is C2 with a
        # quiet fundamental, not C3 with a rumble underneath.)
        while f / 2.0 >= lo:
            half = f / 2.0
            odd = max(at(S, half * 3 / step), at(S, half * 5 / step))
            if at(S, half / step) < oct_ratio * at(S, f / step) \
                    or odd < oct_ratio * at(S, f / step):
                break
            f = half
        got = refine_peak(S, int(round(f / step))) * step
        out[i] = got if got > 0 else f
        strength[i] = sal[j]
    if strength.max() > 0:
        out[strength < thresh * strength.max()] = 0.0
    # A MODE filter, on semitones, not a median on frequencies. A held bass
    # note makes the tracker alternate between two adjacent semitones frame
    # by frame - measured, F#1 G1 F#1 G1 across four seconds of one note -
    # and a median of a 50/50 alternation is whichever side it fell on, so
    # the note comes apart into dozens of fragments. The commonest semitone
    # over a window cannot alternate. A score of the same performance says
    # the notes there are 4.50 s long and the tracker was calling them 0.62.
    if mode_frames > 1:
        h = mode_frames // 2
        mid = np.array([to_midi(v) if v > 0 else 0.0 for v in out])
        sm = np.zeros(n)
        for i in range(n):
            w = [int(round(q)) for q in mid[max(0, i - h):i + h + 1] if q > 0]
            if len(w) > h // 2:
                vals, counts = np.unique(w, return_counts=True)
                sm[i] = from_midi(float(vals[int(np.argmax(counts))]))
        return sm
    med = out.copy()
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


def track_viterbi(mag, fr, lo, hi, thresh=0.10, jump=0.30, max_step=7):
    """The most likely pitch PATH, not the loudest bin a frame.

    Without continuity a lead tracker follows whatever rings loudest, which
    on a cue full of struck metal means it plays the metal. A transition
    penalty in semitones fixes that, and it costs one pass forward and one
    back.

    There is no silent state, and that is deliberate. With one, the path
    can go quiet for a frame and come back anywhere it likes, because
    re-entry from silence carries no pitch penalty - silence is a free
    teleport between registers. Measured on a real recording, the lead it
    produced ran A4 C5 E5 A4 C5 C6 F5 A4 ... D6 B4 D5: a line leaping an
    octave and a half every bar, which does not read as a lead at all. It
    reads as sparkle, and what a listener reports is that the lead has
    vanished.

    So the path is continuous by construction, single frame steps are
    capped at `max_step` semitones, and voicing is decided afterwards from
    the salience along the path that was chosen. The penalty is then free
    to be gentle enough for a melody to actually move: at 2.0 a semitone,
    which is what it was, a two semitone step costs twice the most any
    frame can pay, so the tracker could only move by teleporting.
    """
    sal, fs = salience(mag, fr, lo, hi)
    sal = sal / np.maximum(1e-12, sal.max())
    semis = np.array([to_midi(f) for f in fs])
    n, m = sal.shape
    if n == 0 or m == 0:
        return np.zeros(n)
    # the transition cost, once: -inf past max_step so no frame can leap
    d = np.abs(semis[:, None] - semis[None, :])
    cost = np.where(d <= max_step, -jump * d, -np.inf)

    score = np.empty((n, m))
    back = np.zeros((n, m), dtype=np.int32)
    score[0] = sal[0]
    for i in range(1, n):
        cand = score[i - 1][:, None] + cost      # from j to k
        back[i] = np.argmax(cand, axis=0)
        score[i] = cand[back[i], np.arange(m)] + sal[i]
    path = np.zeros(n, dtype=np.int32)
    path[-1] = int(np.argmax(score[-1]))
    for i in range(n - 1, 0, -1):
        path[i - 1] = back[i, path[i]]
    # voiced where the path's own salience earns it
    out = np.array([fs[p] for p in path])
    along = np.array([sal[i, path[i]] for i in range(n)])
    out[along < thresh] = 0.0
    return out


# One voice a register, and the TOP one reaches to 2.6 kHz. It used to stop
# at 1.6, which is where the lead tracker stops too, so a line above that
# was carried by nothing at all - and a listener hears that as the high
# melody going missing.
# Chosen by sweeping both against the source's peaks in three bands at once
# (200-700, 700-1400, 1400-2500 Hz) and taking the split whose WORST band is
# best, not the one whose mean is best: a configuration that covers 70% of
# the top band while leaving 49% of the middle has lost a part, and losing a
# part is the whole failure mode. This one measured 60.1 / 58.4 / 58.7.
HIGH = (1200.0, 2600.0)
LOW = (200.0, 700.0)


def track_voices(mag, fr, bands=(HIGH, LOW), thresh=0.09,
                 cents_per_step=50.0):
    """One melodic line per register, all of them at once.

    One tracker finds one line, and a mix has more: measured on a real
    recording, 200-2500 Hz holds a median of six strong partials a frame,
    while an arrangement of a lead, its octave and an arpeggio puts two or
    three voices there - one of them a duplicate of another. That gap is
    what "thin" is, and it measured 23.7% of the source's strong peaks
    covered within 60 cents.

    Each frame, each band in turn: take the harmonic sum over that band,
    claim its peak, then subtract that pitch's harmonic comb from the
    spectrum so a lower band cannot claim the same note again.

    Banding is what keeps a voice singing one line. Assigning the strongest
    three peaks to three voices by continuity was tried first and it let
    voice 0 run E4 - E5 - C5 - C4 - A3 in ten seconds, which is not a part,
    and it let two voices land on A3 together. A register each cannot cross
    and cannot duplicate.
    """
    step = fr[1] - fr[0]
    plan = []
    for lo, hi in bands:
        n = int(round(1200 * math.log(hi / lo, 2) / cents_per_step)) + 1
        cand = lo * 2 ** (np.arange(n) * cents_per_step / 1200.0)
        bins = np.array([[int(round(f * h / step)) for h in range(1, 7)]
                         for f in cand])
        plan.append((cand, bins, bins < mag.shape[1]))
    w = np.array([0.8 ** h for h in range(6)])

    out = np.zeros((len(mag), len(bands)))
    for i in range(len(mag)):
        S = mag[i].copy()
        ref = float(S.max())
        if ref <= 0:
            continue
        for v, (cand, bins, ok) in enumerate(plan):
            sal = np.zeros(len(cand))
            for h in range(6):
                m = ok[:, h]
                sal[m] += w[h] * S[bins[m, h]]
            j = int(np.argmax(sal))
            if sal[j] <= thresh * ref * w.sum():
                continue
            f = cand[j]
            got = refine_peak(S, int(round(f / step))) * step
            if got > 0:
                f = got
            out[i, v] = f
            for h in range(1, 9):               # take the note out of the
                b = int(round(f * h / step))    # spectrum before the next
                if b < len(S):                  # band looks at it
                    S[max(0, b - 2):b + 3] = 0.0
    for v in range(len(bands)):                 # median filter the gaps
        col = out[:, v].copy()
        for i in range(len(col)):
            q = [x for x in out[max(0, i - 2):i + 3, v] if x > 0]
            col[i] = float(np.median(q)) if len(q) >= 2 else 0.0
        out[:, v] = col
    return out


def notes_of(f0, hz, grid, min_frames=3, max_jump=14):
    """A pitch track as notes: quantised to semitones, and to the grid
    only if one is given.

    Pass grid=None for material that was played by hand. Snapping a note
    start to a 9.375-frame grid moves it by up to 94 ms, which is audible,
    and on an unquantised performance there is nothing there to snap TO -
    the grid is a description of the average, not of any actual note.
    """
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
            if grid is None:
                start, length = i, j - i
            else:
                start = int(round((i - grid[0]) / grid[1])) * grid[1] + grid[0]
                start = max(0, start)
                length = max(min_frames,
                             int(round((j - i) / grid[1])) * grid[1])
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
    # float positions, rounded only at use. Rounding the window to whole
    # frames first is the same drift that put the tempo three halves out:
    # at 103.4 bpm a two-beat window is 58.03 frames, and 58 loses a frame
    # every twenty bars.
    out = []
    span = beat_frames * per_chord
    step = max(1, int(round(span)))
    k = 0
    while True:
        start = int(round(phase + k * span))
        k += 1
        if start + step >= len(mag):
            break
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


def drum_sections(perc, fr, rate=50, win=8.0, thresh=0.15, min_run=4.0,
                  bridge=2.0, lo=(45.0, 95.0), hi=(6000.0, 13000.0)):
    """When the piece has a drum part, as a mask over frames.

    Onset detection cannot tell a drum from the attack of anything else, and
    that is not a small error on real music: measured against a score, this
    file's drums fired from 12 s to 189 s of a piece whose drum track runs
    54 s to 108 s, placing 26 snares at 38 s where the score is silent. On a
    second piece, whose score has NO DRUM TRACK AT ALL, it played 566.

    Per-onset classification does not fix it. Spectral flatness of the rise,
    bands rising together, energy above 8 kHz, the percussive share of the
    rise, the share sitting on harmonics: every one landed between 65% and
    76% against a base rate of 67% for guessing "not a drum" every time.

    Nor does the amount of high-band percussive energy, however it is
    thresholded. The second piece has NINETEEN TIMES the first one's, from
    bright synth transients - a "Knife" and a "Noise Generator", by their
    track names - and it is peakier too: a 90th-to-20th-percentile contrast
    of 24.8 against 18.4. Any measure of how much or how spiky the high band
    is calls that piece drums.

    What separates them is that a kit hits LOW AND HIGH AT THE SAME TIME. A
    kick lands with a hat; a snare has a body and a crack. A bright synth
    attack has no reason to coincide with the bass. The correlation between
    low-band and high-band percussive flux, measured over a window:

        a section with drums                +0.405, +0.605
        the same piece where there are none -0.038
        a piece whose score has no drums    -0.015, -0.011

    Errors are frame-to-frame noise while the truth is a contiguous block,
    so runs shorter than `min_run` seconds go and gaps under `bridge` close.
    """
    kl = np.where((fr >= lo[0]) & (fr <= lo[1]))[0]
    kh = np.where((fr >= hi[0]) & (fr <= hi[1]))[0]
    n = len(perc)
    if not len(kl) or not len(kh) or n < 4:
        return np.zeros(n, bool)

    def flux_of(k):
        e = perc[:, k].sum(axis=1)
        return np.concatenate([[0.0], np.maximum(0.0, np.diff(e))])

    a, b = flux_of(kl), flux_of(kh)
    w = max(4, int(round(win * rate)))
    ker = np.ones(w) / w
    ma = np.convolve(a, ker, "same")
    mb = np.convolve(b, ker, "same")
    va = np.convolve(a * a, ker, "same") - ma * ma
    vb = np.convolve(b * b, ker, "same") - mb * mb
    cov = np.convolve(a * b, ker, "same") - ma * mb
    r = cov / np.sqrt(np.maximum(1e-20, va * vb))

    on = r > thresh
    idx = np.where(on)[0]
    out = np.zeros(n, bool)
    if not len(idx):
        return out
    runs = []
    start = prev = idx[0]
    for i in idx[1:]:
        if i - prev > bridge * rate:
            runs.append((start, prev))
            start = i
        prev = i
    runs.append((start, prev))
    for p, q in runs:
        if q - p >= min_run * rate:
            out[p:q + 1] = True
    return out


def drums_of(mag, fr, fl, hz, thresh=0.12, rel=0.22, grid=None,
             gate=None):
    """Onsets, and what kind of hit each one is.

    The kind is decided on how much each band *rises* at the onset, per bin,
    not on how much energy it holds: absolute sums let a sustained hi-hat and
    a band three octaves wide outvote the hit being classified.
    """
    pk = []
    f = fl / max(1e-12, fl.max())
    # the threshold has to be LOCAL. Against the global maximum, a track
    # whose loudest moment is much louder than its average passes almost
    # every ripple: measured, one recording produced 2.81 hits a beat, which
    # is a hit on nearly every sixteenth of every bar of four minutes.
    half = 50
    local = np.array([np.median(f[max(0, i - half):i + half + 1])
                      for i in range(len(f))])
    for i in range(2, len(f) - 2):
        if f[i] != max(f[i - 2:i + 3]):
            continue
        if f[i] < thresh or f[i] < local[i] + rel * (1.0 - local[i]):
            continue
        if gate is not None and i < len(gate) and not gate[i]:
            continue                            # the piece has no drums here
        if not pk or i - pk[-1] >= 4:
            pk.append(i)
    bands = {}
    # 40-90, not 40-140: a bass note's fundamental sits in 60-140 and its
    # attack then reads as a kick. One recording came back as 862 kicks
    # against 86 snares and 7 hats, which is not a drum kit
    for name, (lo, hi) in (("low", (40, 90)), ("mid", (160, 1200)),
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
        # and a kick's rise is concentrated low, where a bass note's attack
        # lifts its harmonics with it
        if rise["low"] / tot > 0.35 and rise["low"] > 1.5 * rise["mid"]:
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


def octave_fixed(mag, fr, notes, ratio=0.30):
    """Which notes are certainly in the octave the tracker put them in.

    A pitch tracker's octave is a guess, and an arranger that folds a
    melody into one register has to know which guesses to respect: fold a
    note that really was up there and the high line disappears, which is
    what a listener reports as losing the melody.

    The test is the one that settled the bass. A note at f could be the
    second harmonic of f/2, and what distinguishes the two is the ODD
    harmonics of f/2: 3f/2 and 5f/2 are not harmonics of f at all, so
    energy there can only come from f/2 really being played. No energy
    there means f is a fundamental in its own right, and folding it down
    would move a note the composer wrote.
    """
    step = fr[1] - fr[0]

    def at(row, f):
        b = int(round(f / step))
        return float(row[max(0, b - 2):b + 3].max()) if b < len(row) else 0.0

    out = []
    for start, length, pitch in notes:
        f = from_midi(pitch)
        lo = max(0, min(start, len(mag) - 1))
        hi = max(lo + 1, min(start + length, len(mag)))
        row = mag[lo:hi].mean(axis=0)
        here = at(row, f)
        odd = max(at(row, f / 2 * 3), at(row, f / 2 * 5))
        out.append(here > 0 and odd < ratio * here)
    return out


def track_struck(mag, fr, lo=450.0, hi=1700.0, rate=50, back=4,
                 thresh=0.12, min_gap=6, cents_per_step=25.0, partials=5):
    """The line that is STRUCK, which is what a listener calls the melody.

    Neither "loudest" nor "highest" finds a melody. On one recording at 45 s
    the three layers are a drone bass at C2/E2, an organ holding a C-E-G-B
    stack whose C3 and E3 are the loudest things in the whole mix at -1 and
    -2 dB, and a bell. The bell is the tune, and a tracker following the
    strongest salience follows the organ every time.

    What separates them is not where they are but what they do: a bell is
    struck and then decays, and an organ just sits. So the pitch is decided
    only at onsets, and from the RISE in the spectrum at that onset - the
    part of it that is new - rather than from the spectrum itself, which is
    mostly whatever was already sounding. The note then holds until the next
    strike, which is the shape a struck note has anyway.

    Measured on that recording: it returns C6 where the bell is C6 and D5
    where the bell is D5, in both cases against an organ 20 dB louder in
    the bands the old tracker preferred.
    """
    step = fr[1] - fr[0]
    k = np.where((fr >= lo * 0.9) & (fr <= hi * partials * 1.1))[0]
    band = np.where((fr >= lo) & (fr <= hi))[0]
    if not len(band) or len(mag) < back + 2:
        return np.zeros(len(mag))
    # onsets, from the rise in this band alone - not the whole spectrum's
    flux = np.zeros(len(mag))
    for i in range(back, len(mag)):
        flux[i] = np.maximum(0.0, mag[i, band] - mag[i - back, band]).sum()
    if flux.max() <= 0:
        return np.zeros(len(mag))
    f = flux / flux.max()
    onsets = []
    for i in range(2, len(f) - 2):
        if f[i] == max(f[i - 2:i + 3]) and f[i] > thresh:
            if not onsets or i - onsets[-1] >= min_gap:
                onsets.append(i)

    n = int(round(1200 * math.log(hi / lo, 2) / cents_per_step)) + 1
    cand = lo * 2 ** (np.arange(n) * cents_per_step / 1200.0)
    hb = np.array([[int(round(c * h / step)) for h in range(1, partials + 1)]
                   for c in cand])
    w = np.array([0.8 ** h for h in range(partials)])

    out = np.zeros(len(mag))
    for j, i in enumerate(onsets):
        rise = np.maximum(0.0, mag[i] - mag[max(0, i - back)])
        pad = np.concatenate([rise, np.zeros(2)])
        sal = np.zeros(n)
        for h in range(partials):
            b = np.clip(hb[:, h], 0, len(rise) - 1)
            sal += w[h] * np.maximum(pad[b], np.maximum(pad[b - 1],
                                                       pad[b + 1]))
        if sal.max() <= 0:
            continue
        c = int(np.argmax(sal))
        got = refine_peak(rise, int(round(cand[c] / step))) * step
        hz = got if got > 0 else cand[c]
        end = onsets[j + 1] if j + 1 < len(onsets) else len(mag)
        out[i:end] = hz
    return out


def legato(notes, min_frames=8, join=3, max_hold=28, tol=0):
    """A note list as a melody: no slivers, no restarts on the same note.

    What notes_of produces is a frame-by-frame pitch decision quantised to
    the grid, and a line that holds one note for three seconds comes out of
    it as a long note with three-frame fragments punched through it.
    Measured on one recording, the median melodic event was 0.14 s inside a
    part whose real notes last seconds - so the melody restarted five times
    a second, and a restarted note is heard as a stutter, not as phrasing.

    Two passes. Adjacent notes of the same pitch are joined into one,
    across gaps of up to `join` frames. Then anything still shorter than
    `min_frames` is dropped and its time given to the note before it, which
    is what a player's own legato does.
    """
    if not notes:
        return []
    # `tol` lets neighbours within a semitone or two merge, keeping the
    # pitch of whichever was longer. A tracker on a held bass note wobbles
    # between adjacent semitones, and requiring equality then cuts one note
    # into dozens: measured against a score, a 4.50 s bass note came back as
    # a median of 0.62 s, a seventeenth of its length. Smoothing the pitch
    # track instead got the lengths right and cost 15 points of pitch-class
    # accuracy, because it smears through the note changes that are real.
    out = []
    for start, length, pitch in sorted(notes):
        if out and abs(out[-1][2] - pitch) <= tol \
                and start <= out[-1][0] + out[-1][1] + join:
            a, l, p = out[-1]
            out[-1] = (a, max(l, start + length - a),
                       p if l >= length else pitch)
        else:
            out.append((start, length, pitch))
    kept = []
    for start, length, pitch in out:
        if length < min_frames and kept:
            a, l, p = kept[-1]
            kept[-1] = (a, max(l, start + length - a), p)   # absorbed
        elif length >= min_frames:
            kept.append((start, length, pitch))
    # Hold each note towards the next so the line is unbroken - but only
    # across a gap of up to `max_hold` frames, about a beat. Past that the
    # melody is RESTING, and a rest is part of the structure: holding
    # through one turns a phrase into a drone, and measured on one recording
    # it produced melody notes of 16.2 and 16.5 seconds.
    for i in range(len(kept) - 1):
        a, l, p = kept[i]
        gap = kept[i + 1][0] - (a + l)
        if 0 < gap <= max_hold:
            kept[i] = (a, kept[i + 1][0] - a, p)
    # and merge again: holding can leave two notes of the same pitch touching,
    # and a note that stops and restarts where nothing happened is a stutter
    out = []
    for start, length, pitch in kept:
        if out and out[-1][2] == pitch and start <= out[-1][0] + out[-1][1]:
            a, l, p = out[-1]
            out[-1] = (a, max(l, start + length - a), p)
        else:
            out.append((start, length, pitch))
    return out


def trim_tails(notes, mag, fr, rate=50, drop=0.45, keep=3, floor=0.6,
               hold=3):
    """Shorten each note to where its own partial stops being loud.

    A pitch tracker ends a note when the pitch stops being detectable, and
    reverb keeps it detectable long after the player let go. Measured
    against a score of the same performance: detected melody notes ran
    1.22x the written length, and a bell's strike partial stays within 12 dB
    of its own peak for a further 0.15 s after the written note-off.

    So the end of a note is where its energy has fallen to `drop` of the
    peak it reached inside the note - which is a decay, and is what a player
    hears as the note ending - rather than where the pitch disappears into
    the room.
    """
    step = fr[1] - fr[0]
    out = []
    for start, length, pitch in notes:
        f = from_midi(pitch)
        b = int(round(f / step))
        if not (0 < b < mag.shape[1] - 2) or length <= keep:
            out.append((start, length, pitch))
            continue
        a = max(0, min(start, len(mag) - 1))
        e = mag[a:a + length, max(0, b - 2):b + 3].max(axis=1)
        if not len(e) or e.max() <= 0:
            out.append((start, length, pitch))
            continue
        peak = float(e.max())
        end = len(e)
        # the drop has to be SUSTAINED, and the note may not lose more than
        # (1 - floor) of itself. Without either guard this trims almost
        # everything to the minimum on material whose notes do not decay:
        # measured, two recordings' melodies went to a median of 0.08 s,
        # the floor, and their peak coverage fell by 9 points.
        for i in range(max(keep, int(floor * len(e))), len(e) - hold):
            if (e[i:i + hold] < drop * peak).all():
                end = i
                break
        out.append((start, max(keep, end), pitch))
    return out


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


def transcribe(x, sr, rate=50, melody="loudest", stems=None):
    """Everything above, on one piece of audio.

    `melody` picks which line becomes the lead: "loudest" (the default, and
    the one the tests cover) or "struck". See the note beside the two
    trackers - nothing here can choose between them reliably, and getting it
    wrong means arranging around the wrong part.

    `stems` is an optional dict of separated sources - {"drums": array,
    "bass": array, "other": array, "vocals": array}, any subset - as a
    separator like Demucs produces. Each one that is present replaces a
    piece of guesswork with a fact:

      drums   the stem IS the drum part, so onsets in it are drum hits and
              the whole drum_sections apparatus is unnecessary. Four
              attempts at deciding that from a mix are documented in this
              file and in midiarr.md, the best of them a correlation
              heuristic.
      bass    the bass line without an organ's low notes or a kick's thump
              in the way. Measured against a score, the tracker on a full
              mix gets the pitch class right 85% of the time and the octave
              3%, and most of that is other instruments in the same band.
      other   what is left after bass, drums and voice, which is where a
              melody usually is.

    What separation does NOT fix is which part is the tune: a bell and an
    organ both land in "other", and that is the error worth the most here -
    57% against a score's 100%. See midiarr.md §4b.
    """
    stems = stems or {}
    hop = int(round(sr / float(rate)))
    mono = x.mean(axis=1) if x.ndim > 1 else x
    mag, fr = stft(mono, sr, 4096, hop)
    mag /= max(1e-12, mag.max())
    harm, perc = hpss(mag)
    fl = flux(perc)                     # onsets from the percussive part
    bpm, phase = tempo_of(fl, rate)
    beat = 60.0 * rate / bpm
    # the grid as a FLOAT. Rounding the step to whole frames is the same
    # mistake as rounding the period: the test cue's sixteenth is 7.8125
    # frames and int(round()) makes it 8, which is 2.4% out and drifts a
    # quarter of a beat across the cue - only 16 of its 43 hits then land
    # within 1.5 frames of a grid they were all played exactly on.
    step16 = max(1.0, beat / 4.0)
    grid = (float(phase) % step16, step16)
    if stems.get("drums") is not None:
        # the stem is the drum part: no gate, and the onsets are its own
        d_mag, d_fr = stft(stems["drums"], sr, 4096, hop)
        d_mag /= max(1e-12, d_mag.max())
        _dh, d_perc = hpss(d_mag)
        gate = np.ones(len(d_mag), bool)
        drums = drums_of(d_perc, d_fr, flux(d_perc), rate, grid=None)
    else:
        gate = drum_sections(perc, fr, rate)
        drums = drums_of(perc, fr, fl, rate, grid=None, gate=gate)
    # the mode window at about half a beat: long enough to outvote a
    # semitone alternation, short enough not to smear a moving bass line.
    # Fixed at 41 frames it was right for one recording at 80 bpm and took
    # 9 points of peak coverage off another.
    bass = track_bass(mono, sr, rate,
                      mode_frames=max(5, int(round(beat / 2)) | 1))
    # A kick is a pitch too - 40 to 60 Hz of it - and the bass tracker will
    # happily report it. Measured on a recording with eighth-note kicks, the
    # bass line came back alternating E1 with a different note every time,
    # which is the real bass and the kick taking turns. Blank those frames
    # and let the note segmenter's median bridge them.
    for i, kind, _v in drums:
        if kind == "kick":
            bass[max(0, i - 1):i + 4] = 0.0
    # take the bass's harmonics off before looking for the lead
    lead_mag = harm.copy()
    for i, f in enumerate(bass):
        if f <= 0:
            continue
        for h in range(1, 7):
            b = int(round(f * h / (fr[1] - fr[0])))
            if b < lead_mag.shape[1]:
                lead_mag[i, max(0, b - 1):b + 2] *= 0.25
    # Two candidates for the melody, and which is right is not something
    # this file can decide. The struck line is the tune when a struck
    # instrument carries it - a bell over an organ, where the organ is
    # louder in every band. The loudest line is right when nothing is being
    # struck.
    #
    # Choosing automatically was tried and is wrong: gated on having enough
    # strikes to be a part, it took the test cue's METAL PERCUSSION as the
    # melody, which is struck and is not a tune. Pitch variety does not
    # separate them either - the clangs' partials give as many distinct
    # pitches as a melody does. So the caller says, and the default is the
    # one with a test behind it: the cue's eight-note motif comes back in
    # order from the loudest line and does not from the struck one.
    if stems.get("other") is not None:
        o_mag, _ofr = stft(stems["other"], sr, 4096, hop)
        o_mag /= max(1e-12, o_mag.max())
        lead_mag, _op = hpss(o_mag)
        lead_mag = lead_mag[:len(mag)]
    loudest = track_viterbi(lead_mag, fr, 250.0, 1600.0)
    struck = track_struck(lead_mag, fr, rate=rate)
    lead = struck if melody == "struck" else loudest
    # the lead out of the way too, and whatever is left is the other parts:
    # the inner lines a single tracker never sees, which are most of what a
    # two-or-three-voice arrangement is missing
    rest = lead_mag.copy()
    for i, f in enumerate(lead):
        if f <= 0:
            continue
        for h in range(1, 7):
            b = int(round(f * h / (fr[1] - fr[0])))
            if b < rest.shape[1]:
                rest[i, max(0, b - 2):b + 3] *= 0.15
    # The high voice is tracked with the lead still IN the spectrum, on
    # purpose. Above the lead, "a separate part" and "the lead's own octave"
    # are the same frequencies, and taking the lead's harmonics out to tell
    # them apart removes the high line either way - which is how it went
    # missing. Whichever it is, it belongs on a channel.
    hi = track_voices(lead_mag, fr, bands=(HIGH,))
    lo = track_voices(rest, fr, bands=(LOW,))
    V = np.concatenate([hi, lo], axis=1)
    # No grid snapping on the notes. The grid is still worth having - the
    # chord windows and the arpeggio's rate are built on it - but a note
    # start belongs where it was played. Measured, on two hand-played
    # recordings, snapping cost both measures: peak coverage 58.7% -> 56.5%
    # and 59.6% -> 59.1%. A 9.375-frame grid moves a note by up to 94 ms,
    # and on an unquantised performance there is nothing there to snap to.
    bass_notes = legato(notes_of(bass, rate, None, 3), min_frames=6,
                        max_hold=int(round(beat)), tol=1)
    lead_notes = trim_tails(notes_of(lead, rate, None, 3), harm, fr, rate)
    lead_fixed = octave_fixed(harm, fr, lead_notes)
    bass_fixed = octave_fixed(harm, fr, bass_notes)
    chords = key_quality(chords_of(lead_mag, fr, rate, beat, phase,
                                   melody=lead_notes + bass_notes))
    return {"bpm": bpm, "beat": beat, "grid": grid, "rate": rate,
            "frames": len(mag), "harm": harm, "perc": perc, "fr": fr,
            "bass": bass_notes,
            "lead": lead_notes,
            # which octaves the spectrum vouches for, so the arranger knows
            # which ones it must not fold away
            "lead_fixed": lead_fixed,
            "bass_fixed": bass_fixed,
            "voices": [notes_of(V[:, v], rate, None, 3)
                       for v in range(V.shape[1])],
            # whichever line did not become the melody, for the arranger to
            # put somewhere: usually the sustained one, which is a pad
            # the line that did not become the melody, for the arranger to
            # place: usually the sustained one, which is a pad
            "other": notes_of(loudest if melody == "struck" else struck,
                              rate, None, 3),
            "melody_is_struck": melody == "struck",
            "chords": chords,
            "drums": drums,
            "drum_sections": gate,
            # a loudness envelope, one value a frame: the arranger uses it
            # for dynamics the way a score would use velocities
            "env": np.sqrt((mag ** 2).sum(axis=1)),
            "flux": fl}
