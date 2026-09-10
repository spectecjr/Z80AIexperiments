"""A disassembler for chip music: what a register log is actually doing.

The synthesis routines in this repo all work the same way - a score
decides what to write to a sound chip every frame - and this reads that
backwards. Given one (frequency, amplitude, flags) per channel per
frame, off a register log and nothing else, it recovers:

    notes       where each one starts, how long it lasts, which note it
                is and how far off equal temperament, and the shape of
                its amplitude
    glides      runs where the pitch moves rather than steps, with the
                rate in cents a second and whether the PERIOD or the
                frequency was what got stepped - which says how the
                player's code was written, not just what it sounded like
    vibrato     rate and depth, per note, by looking at what is left of
                the pitch once the trend is taken out
    pairs       two channels holding the same note a few cents apart,
                and how many times a second they therefore beat
    stacks      one channel running at 2f, 3f or 4f of another
    ganging     several channels carrying one noise generator, which is
                how you get more amplitude steps than a register has
    grid        the frame grid the note starts fall on, and so the tempo

None of that needs the source. It is all in the log, which is the point:
point it at somebody else's player and it tells you how their
instruments are built.

Everything here is chip-agnostic - it takes Tracks, and saareg.py and
ayreg.py make Tracks out of an SAA1099 log and a VGM respectively.
"""
import math

CENT = 1200.0


def cents(a, b):
    """How far b is above a, in cents."""
    if a <= 0 or b <= 0:
        return 0.0
    return CENT * math.log(b / a, 2)


class Track:
    """One channel, frame by frame."""

    def __init__(self, ch, hz, amp, tone, noise, env=None, name=None,
                 period=None):
        self.ch = ch
        self.period = period            # the raw divider, when the chip has one
        self.hz = hz                    # Hz a frame, 0 when it has none
        self.amp = amp                  # 0..15 a frame
        self.tone = tone                # booleans a frame
        self.noise = noise
        self.env = env or [False] * len(hz)
        self.name = name or "ch%d" % ch

    def __len__(self):
        return len(self.hz)

    def on(self, i):
        return self.amp[i] > 0 and (self.tone[i] or self.noise[i])

    def kind(self):
        """What this channel is for, over the whole log."""
        t = any(self.tone[i] and self.on(i) for i in range(len(self)))
        n = any(self.noise[i] and self.on(i) for i in range(len(self)))
        if t and n:
            return "tone+noise"
        if n:
            return "noise"
        if t:
            return "tone"
        return "silent"


class Glide:
    def __init__(self, ch, start, steps, f0, f1, bytewise):
        self.ch, self.start, self.steps = ch, start, steps
        self.f0, self.f1 = f0, f1
        self.cents = cents(f0, f1)
        self.bytewise = bytewise

    def rate(self, hz):
        return self.cents / (self.steps / float(hz))


class Note:
    def __init__(self, ch, start, frames, hz, amps):
        self.ch, self.start, self.frames = ch, start, frames
        self.hz = hz                    # the Hz of each frame of it
        self.amps = amps
        self.glide_in = None
        self.vib = None

    def median_hz(self):
        s = sorted(self.hz)
        return s[len(s) // 2]

    def shape(self):
        """attack frames, peak level, and whether it decays or holds."""
        peak = max(self.amps)
        att = self.amps.index(peak)
        end = self.amps[-1]
        return att, peak, ("decays" if end <= peak * 0.4 else
                           "holds" if end >= peak * 0.8 else "falls")


def find_glides(track, min_step=12.0, min_total=55.0, min_frames=3):
    """Runs where the pitch moves steadily instead of stepping.

    A glide is what a player does by writing a new period every frame,
    so it shows up as several frames of same-signed change. Whether the
    PERIOD moved by a constant amount or the frequency did is worth
    knowing: the first is what a few lines of Z80 naturally produce.
    """
    out = []
    n = len(track)
    i = 1
    while i < n:
        if not (track.on(i) and track.on(i - 1)):
            i += 1
            continue
        d = cents(track.hz[i - 1], track.hz[i])
        if abs(d) < min_step:
            i += 1
            continue
        j = i
        while j < n and track.on(j) and track.on(j - 1):
            dj = cents(track.hz[j - 1], track.hz[j])
            if abs(dj) < min_step or (dj > 0) != (d > 0):
                break
            j += 1
        span = cents(track.hz[i - 1], track.hz[j - 1])
        if (j - i) >= min_frames - 1 and abs(span) >= min_total:
            # was the period stepped evenly, or the frequency?
            per = [1.0 / track.hz[k] for k in range(i - 1, j)]
            dper = [per[k + 1] - per[k] for k in range(len(per) - 1)]
            dhz = [track.hz[k + 1] - track.hz[k] for k in range(i - 1, j - 1)]
            bytewise = spread(dper) < spread(dhz)
            out.append(Glide(track.ch, i - 1, j - i, track.hz[i - 1],
                             track.hz[j - 1], bytewise))
            i = j
        else:
            i = j + 1
    return out


def spread(xs):
    """Relative scatter, for telling two candidate straight lines apart."""
    xs = [x for x in xs if x == x]
    if not xs:
        return 1e9
    m = sum(xs) / len(xs)
    if m == 0:
        return 1e9
    var = sum((x - m) ** 2 for x in xs) / len(xs)
    return math.sqrt(var) / abs(m)


def find_notes(track, glides, tol=70.0, jump=55.0):
    """Segment what is left into notes once the glides are out of it."""
    gl = {}
    for g in glides:
        for k in range(g.start, g.start + g.steps + 1):
            gl[k] = g
    notes = []
    n = len(track)
    i = 0
    while i < n:
        if not track.on(i) or i in gl:
            i += 1
            continue
        j = i + 1
        while j < n and track.on(j) and j not in gl:
            if abs(cents(track.hz[j - 1], track.hz[j])) > jump:
                break
            if abs(cents(track.hz[i], track.hz[j])) > tol:
                break
            if track.amp[j] > track.amp[j - 1] and track.amp[j - 1] == 0:
                break
            j += 1
        note = Note(track.ch, i, j - i, track.hz[i:j], track.amp[i:j])
        g = gl.get(i - 1)
        if g and g.start + g.steps == i - 1:
            note.glide_in = g
        notes.append(note)
        i = j
    return notes


def find_vibrato(note, hz=50, min_depth=4.0, window=9):
    """What is left of the pitch once the shape of the note is out of it.

    A note is not a straight line - it can be bent into at the start and
    sagged at the end, which is what shaku.z80s does deliberately - and
    taking only a straight line out of it leaves enough of that bend to
    drag the fitted period several per cent short. A centred moving
    average removes any slow shape without shifting the period, because
    it has no phase; what it does do is flatten the depth, and the
    flattening is exactly computable, so it is divided back out.
    """
    k = note.frames
    if k < 8:
        return None
    c = [cents(note.hz[0], f) for f in note.hz]
    half = window // 2
    r = []
    for i in range(k):                  # high pass: subtract a local mean
        lo = max(0, i - half)
        hi = min(k, i + half + 1)
        r.append(c[i] - sum(c[lo:hi]) / float(hi - lo))

    def fit(pp):
        s2 = sum(r[i] * math.sin(2 * math.pi * i / pp) for i in range(k))
        c2 = sum(r[i] * math.cos(2 * math.pi * i / pp) for i in range(k))
        return 2 * math.hypot(s2, c2) / k

    # The period comes from the spacing of the peaks, not from a fit over
    # the whole note: a vibrato that arrives over a few cycles has ragged
    # early ones, and a fit averages those in and comes out several per
    # cent short. The median spacing ignores them, which is the point of
    # a median. The fit is still what measures the depth.
    peaks = [i for i in range(1, k - 1)
             if r[i] >= r[i - 1] and r[i] > r[i + 1] and r[i] > 0]
    troughs = [i for i in range(1, k - 1)
               if r[i] <= r[i - 1] and r[i] < r[i + 1] and r[i] < 0]
    gaps = sorted([peaks[i + 1] - peaks[i] for i in range(len(peaks) - 1)]
                  + [troughs[i + 1] - troughs[i] for i in range(len(troughs) - 1)])
    gaps = [g for g in gaps if 2 <= g <= 40]
    if len(gaps) >= 3:                  # two cycles is not a measurement
        period = float(gaps[len(gaps) // 2])
    else:
        best = None
        for pp in range(3, min(k // 2, 40) + 1):
            mag = fit(pp)
            if best is None or mag > best[1]:
                best = (pp, mag)
        period = float(best[0])
    # what the moving average did to a modulation of this period, undone
    resp = math.sin(math.pi * window / period) / \
        (window * math.sin(math.pi / period))
    gain = abs(1.0 - resp) or 1.0
    depth = fit(period) / gain
    if depth < min_depth:
        return None
    return {"hz": float(hz) / period, "cents": depth, "frames": period}


def runs_on(track, min_len=16):
    """The stretches where a channel is sounding without a break."""
    out = []
    i = 0
    n = len(track)
    while i < n:
        if not track.on(i):
            i += 1
            continue
        j = i
        while j < n and track.on(j):
            j += 1
        if j - i >= min_len:
            out.append((i, j))
        i = j


    return out


def find_tremolo(track, hz=50, min_depth=1.2):
    """A periodic amplitude pattern - a volume ramp written per frame.

    This is what a tracker instrument's volume column does, and it is
    audible as tremolo rather than as an envelope when it repeats.
    """
    best = None
    for i, j in runs_on(track):
        a = [float(x) for x in track.amp[i:j]]
        k = len(a)
        mean = sum(a) / k
        r = [x - mean for x in a]
        den = sum(x * x for x in r)
        if den <= 0:
            continue
        for period in range(2, min(k // 3, 50) + 1):
            c = sum(r[t] * r[t + period] for t in range(k - period))
            c /= den
            if c < 0.45:
                continue
            # a ramp that restarts with each note drifts in phase, so
            # averaging the cycles flattens it - take the depth window by
            # window instead, and show the window that is most typical
            wins = [a[t:t + period] for t in range(0, k - period, period)]
            depths = sorted(max(w) - min(w) for w in wins)
            if not depths:
                continue
            depth = depths[len(depths) // 2]
            shape = min(wins, key=lambda w: abs((max(w) - min(w)) - depth))
            if depth >= min_depth and (best is None or depth > best["depth"]):
                best = {"frames": period, "hz": float(hz) / period,
                        "depth": depth, "shape": shape, "corr": c,
                        "at": i, "over": k}
    return best


def tremolo_lag(ta, tb, period):
    """How far apart two channels run the same amplitude pattern."""
    n = min(len(ta), len(tb))
    best = None
    for lag in range(period):
        num = 0.0
        k = 0
        for i in range(n - period):
            if ta.on(i) and tb.on(i + lag):
                num += (ta.amp[i] - 7.5) * (tb.amp[i + lag] - 7.5)
                k += 1
        if k > 20 and (best is None or num / k > best[1]):
            best = (lag, num / k)
    return best[0] if best else None


def find_pairs(tracks, max_cents=260.0, min_frames=10):
    """Two channels on the same note, a little apart: the beat is the point.

    Where the chip divides a clock, the interesting thing is not the
    detune in cents but the DIVIDER difference: a player that writes the
    same period to two channels and adds one to the second has detuned
    by a different number of cents at every pitch, and that is a
    fingerprint of how the code was written.
    """
    out = []
    for a in range(len(tracks)):
        for b in range(a + 1, len(tracks)):
            ta, tb = tracks[a], tracks[b]
            beats = []
            diffs = []
            both = 0
            for i in range(min(len(ta), len(tb))):
                if ta.on(i) and tb.on(i) and ta.tone[i] and tb.tone[i] \
                        and ta.hz[i] > 0 and tb.hz[i] > 0:
                    both += 1
                    if abs(cents(ta.hz[i], tb.hz[i])) < max_cents:
                        beats.append(abs(ta.hz[i] - tb.hz[i]))
                        if ta.period and tb.period:
                            diffs.append(tb.period[i] - ta.period[i])
            if len(beats) >= min_frames:
                beats.sort()
                how = None
                if diffs:
                    common = max(set(diffs), key=diffs.count)
                    if diffs.count(common) > 0.6 * len(diffs):
                        how = common
                mid = beats[len(beats) // 2]
                out.append({"a": ta.ch, "b": tb.ch, "frames": len(beats),
                            "of": both, "beat": mid,
                            "lo": beats[0], "hi": beats[-1], "divider": how,
                            "kind": ("chorus" if mid < 12 else
                                     "roughness" if mid < 90 else "a chord")})
    return out


def find_stacks(tracks, tol=0.02, min_frames=10):
    """One channel running at a whole multiple of another."""
    names = {2.0: "2f", 3.0: "3f", 4.0: "4f", 1.5: "3f/2", 6.0: "6f",
             8.0: "8f"}
    out = []
    for a in range(len(tracks)):
        for b in range(len(tracks)):
            if a == b:
                continue
            ta, tb = tracks[a], tracks[b]
            for ratio, label in names.items():
                k = 0
                for i in range(min(len(ta), len(tb))):
                    if ta.on(i) and tb.on(i) and ta.tone[i] and tb.tone[i] \
                            and ta.hz[i] > 0:
                        if abs(tb.hz[i] / ta.hz[i] - ratio) < tol * ratio:
                            k += 1
                both = sum(1 for i in range(min(len(ta), len(tb)))
                           if ta.on(i) and tb.on(i) and ta.tone[i]
                           and tb.tone[i])
                if k >= min_frames and both and k >= 0.4 * both:
                    out.append({"a": ta.ch, "b": tb.ch, "ratio": label,
                                "frames": k, "of": both})
    return out


def find_grid(starts, n_frames, hz=50, cover=0.85):
    """The frame grid note starts land on, and so the tempo."""
    if len(starts) < 4:
        return None
    best = None
    for g in range(2, min(60, n_frames // 2)):
        for phase in range(g):
            k = sum(1 for s in starts if (s - phase) % g == 0)
            if k >= cover * len(starts) and (best is None or g > best[0]):
                best = (g, phase, k)
    if not best:
        return None
    g, phase, k = best
    return {"frames": g, "hz": float(hz) / g, "bpm": 60.0 * hz / g,
            "hit": k, "of": len(starts)}


def analyse(tracks, hz=50, chip=None):
    """Everything above, over a whole log."""
    out = {"hz": hz, "frames": len(tracks[0]) if tracks else 0,
           "chip": chip or {}, "channels": []}
    starts = []
    for t in tracks:
        glides = find_glides(t)
        notes = find_notes(t, glides)
        for nt in notes:
            nt.vib = find_vibrato(nt, hz)
        starts += [nt.start for nt in notes]
        out["channels"].append({"track": t, "kind": t.kind(),
                                "glides": glides, "notes": notes,
                                "tremolo": find_tremolo(t, hz)})
    out["pairs"] = find_pairs(tracks)
    out["stacks"] = find_stacks(tracks)
    out["grid"] = find_grid(sorted(starts), out["frames"], hz)
    for i, c in enumerate(out["channels"]):          # who shares a tremolo
        tr = c["tremolo"]
        if not tr:
            continue
        c["lags"] = []
        for j, d in enumerate(out["channels"]):
            if j != i and d["tremolo"] and \
                    d["tremolo"]["frames"] == tr["frames"]:
                lag = tremolo_lag(c["track"], d["track"], tr["frames"])
                if lag:
                    c["lags"].append((d["track"].ch, lag))
    return out


# ---------------------------------------------------------------
# the report: the same analysis, for a person to read
# ---------------------------------------------------------------

def note_name(f):
    import saareg
    return saareg.note_name(f)


def report(a, title="", notes_per_channel=14):
    hz = a["hz"]
    L = []
    w = L.append
    w("  %s%s%d frames, %.2f s at %d Hz"
      % (title, "   " if title else "", a["frames"],
         a["frames"] / float(hz), hz))
    chip = a.get("chip") or {}
    if chip:
        w("")
        w("  THE CHIP")
        for k, v in chip.items():
            w("    %-16s %s" % (k, v))
    if a.get("grid"):
        g = a["grid"]
        w("    %-16s every %d frames - %.1f a second, %.0f bpm in quarters"
          % ("note starts", g["frames"], g["hz"], g["bpm"] / 4.0))
    if a["pairs"]:
        w("    %-16s %s" % ("detuned pairs",
                            "; ".join(
                                ("ch%d+ch%d beat %.1f..%.1f Hz over %d of %d "
                                 "frames - %s" %
                                 (p["a"], p["b"], p["lo"], p["hi"],
                                  p["frames"], p["of"], p["kind"]))
                                + ("" if p["divider"] is None else
                                   " - the dividers differ by %+d, so it was "
                                   "written as one period plus %d"
                                   % (p["divider"], p["divider"]))
                                for p in a["pairs"])))
    if a["stacks"]:
        w("    %-16s %s" % ("harmonic stacks",
                            ", ".join("ch%d is %s of ch%d (%d frames)"
                                      % (s["b"], s["ratio"], s["a"],
                                         s["frames"]) for s in a["stacks"])))
    for c in a["channels"]:
        t = c["track"]
        if c["kind"] == "silent":
            continue
        w("")
        w("  CHANNEL %d   %s, %d notes, %d glides"
          % (t.ch, c["kind"], len(c["notes"]), len(c["glides"])))
        playing = [t.hz[i] for i in range(len(t)) if t.on(i) and t.tone[i]]
        if playing:
            w("    %-16s %.1f .. %.1f Hz" % ("pitch", min(playing),
                                             max(playing)))
        amps = [x for x in t.amp if x]
        if amps:
            w("    %-16s %d .. %d" % ("level", min(amps), max(amps)))
        tr = c.get("tremolo")
        if tr:
            w("    %-16s repeats every %d frames (%.1f Hz), %.0f levels deep,"
              " like %s"
              % ("volume pattern", tr["frames"], tr["hz"], tr["depth"],
                 " ".join("%.0f" % v for v in tr["shape"])))
            for ch, lag in c.get("lags", []):
                w("    %-16s ch%d runs the same pattern %d frames later"
                  % ("", ch, lag))
        vibbed = [n for n in c["notes"] if n.vib]
        if vibbed:
            # read it off the longest note: the more cycles there are, the
            # less a ragged first one matters
            best = max(vibbed, key=lambda n: n.frames)
            w("    %-16s %.2f Hz, +-%.0f cents, off the longest note (%d "
              "frames); on %d of %d notes"
              % ("vibrato", best.vib["hz"], best.vib["cents"], best.frames,
                 len(vibbed), len(c["notes"])))
        long_notes = [n for n in c["notes"] if n.frames > 2]
        if long_notes:
            att = sum(n.shape()[0] for n in long_notes) / float(len(long_notes))
            drop = sum(max(n.amps) - n.amps[-1] for n in long_notes) \
                / float(len(long_notes))
            ramped = sum(1 for n in long_notes if max(n.amps) - n.amps[-1] >= 2)
            w("    %-16s peak after %.1f frames, then down %.1f levels by the "
              "end; %d of %d notes ramp"
              % ("amplitude", att, drop, ramped, len(long_notes)))
        for g in c["glides"][:6]:
            w("    glide at %5.2f s  %6.1f -> %6.1f Hz  %+5.0f cents in %d "
              "frames (%.0f cents/s), %s stepped evenly"
              % (g.start / float(hz), g.f0, g.f1, g.cents, g.steps,
                 g.rate(hz), "period" if g.bytewise else "frequency"))
        if len(c["glides"]) > 6:
            w("    ... and %d more glides" % (len(c["glides"]) - 6))
        if c["kind"] != "noise" and c["notes"]:
            line = []
            for n in c["notes"][:notes_per_channel]:
                nm, ct = note_name(n.median_hz())
                line.append("%s%+.0f/%df" % (nm, ct, n.frames))
            w("    notes            " + "  ".join(line)
              + ("  ..." if len(c["notes"]) > notes_per_channel else ""))
    return "\n".join(L)
