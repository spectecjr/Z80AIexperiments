"""A score onto six channels, the way a chip musician would spend them.

transcribe.py reduces audio to a bass line, a lead, two more melodic
voices, a chord and a drum part. This plays them - all of them, every
frame. That is the whole design rule, and it is the second version of it:

    EVERY PART IDENTIFIED GETS A CHANNEL, AND KEEPS IT.

The first version let parts yield to each other - the arpeggio rested
while the lead played, the drums took a channel of their own - and the
result measured 23.7% of the source's strong 200-2500 Hz peaks covered,
which is audibly thin. A part that goes quiet to make room for another
part is a part the arrangement has lost. So now nothing yields: a voice
with nothing to play holds its last note or falls back to a chord tone,
which is the chip version of reducing a line to a single tone rather than
dropping it.

    ch0   bass - and the KICK, which steals this channel for five frames.
          A kick and a bass note land on the same beat in nearly every bar,
          so spending a second channel on the pair buys nothing
    ch1   the lead, held through the gaps in the tracking
    ch2   the second voice. Where the tracker found none, the lead an
          octave up, so this channel is never silent under a lead
    ch3   the chord, ARPEGGIATED, ALWAYS. This is the mid register, and
          it is the part the first version threw away
    ch4   the third voice, falling back to a sustained chord tone
    ch5   percussion, noise only, at a fixed rate - NOT mode 3, which
          clocks from ch3's tone generator, and ch3 is running the
          arpeggio. A snare whose brightness follows the chord is not a
          snare

Four tone voices above the bass, then, against a median of six strong
partials in the source - so the arrangement is a reduction, but it is no
longer a sketch. Levels are set so the four do not sum past the mixer:
the lead leads, the inner voices sit under it, the arpeggio under those.
"""
import math

import numpy as np

import arrange as A

CLOCK = 8000000.0
A4 = 440.0


def pick(f):
    """Nearest (octave, frequency byte) for a frequency."""
    best = None
    for octave in range(8):
        n = 511 - (CLOCK / 512.0) * (1 << octave) / f
        if -1.0 <= n <= 256.0:
            nn = int(round(min(255.0, max(0.0, n))))
            got = (CLOCK / 512.0) * (1 << octave) / (511 - nn)
            err = abs(math.log(got / f))
            if best is None or err < best[0]:
                best = (err, octave, nn)
    return (best[1], best[2]) if best else (0, 0)


def midi_hz(m):
    return A4 * 2 ** ((m - 69) / 12.0)


TRIAD = {"": (0, 4, 7), "m": (0, 3, 7)}


class Out:
    """Per-frame state for six channels, then the register writes."""

    def __init__(self, n):
        self.n = n
        self.oct = np.zeros((6, n), int)
        self.byte = np.zeros((6, n), int)
        self.lvl = np.zeros((6, n), int)
        self.noise = np.zeros((6, n), int)       # 0 off, else mode+1
        self.sounded = np.zeros((6, n), bool)

    def tone(self, c, i, hz, level):
        if i < 0 or i >= self.n or level <= 0 or hz <= 0:
            return
        o, b = pick(hz)
        self.oct[c, i], self.byte[c, i] = o, b
        self.lvl[c, i] = max(self.lvl[c, i], min(15, level))
        self.sounded[c, i] = True

    def force(self, c, i, hz, level):
        """Like tone(), but it takes the channel over rather than sharing."""
        if i < 0 or i >= self.n:
            return
        o, b = pick(hz)
        self.oct[c, i], self.byte[c, i] = o, b
        self.lvl[c, i] = min(15, max(0, level))
        self.noise[c, i] = 0
        self.sounded[c, i] = level > 0

    def hiss(self, c, i, mode, level):
        if i < 0 or i >= self.n or level <= 0:
            return
        self.noise[c, i] = mode + 1
        self.lvl[c, i] = max(self.lvl[c, i], min(15, level))
        self.sounded[c, i] = True

    def registers(self):
        frames = []
        state = [None] * 32
        for i in range(self.n):
            want = {}
            fen = nen = 0
            for c in range(6):
                if self.noise[c, i]:
                    nen |= 1 << c
                elif self.sounded[c, i]:
                    fen |= 1 << c
                want[c] = self.lvl[c, i] * 0x11
                want[0x08 + c] = self.byte[c, i]
            want[0x14] = fen
            want[0x15] = nen
            modes = [0, 0]
            for c in range(6):
                if self.noise[c, i]:
                    modes[c // 3] = self.noise[c, i] - 1
            want[0x16] = modes[0] | (modes[1] << 4)
            want[0x10] = self.oct[0, i] | (self.oct[1, i] << 4)
            want[0x11] = self.oct[2, i] | (self.oct[3, i] << 4)
            want[0x12] = self.oct[4, i] | (self.oct[5, i] << 4)
            out = []
            for r in (0x14, 0x15, 0x16, 0x10, 0x11, 0x12, 0x08, 0x09, 0x0A,
                      0x0B, 0x0C, 0x0D, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05):
                if state[r] != want[r]:
                    out.append((r, want[r]))
                    state[r] = want[r]
            frames.append(out)
        if frames:
            frames[0] = list(A.INIT) + frames[0]
        return frames


def decay(level, k, fall, floor=0.55):
    """A level k frames into a note, never falling past a sustain.

    Without the floor a long note fades to nothing and the part disappears
    under itself: the bass sounded in 63% of frames where the score had it
    in 89%, because a 105-frame note at 0.12 a frame runs out of level
    before it runs out of note. An instrument decays to a sustain, not to
    silence.
    """
    return int(round(max(level * floor, level - fall * k)))


def fold_lead(notes, window=7, span=4, fixed=None):
    """The melody into one register, keeping every pitch class.

    A pitch tracker picks whichever partial is loudest, so the line it
    returns jumps octaves: measured on a real recording, 11 of 85 notes
    leapt more than seven semitones, and the result does not read as one
    instrument playing a tune - it reads as part of the texture, which is
    what "the lead vanishes" sounds like from the outside.

    Each note is moved by whole octaves until it sits within `window`
    semitones of the melody's local centre. The tune keeps its shape and
    loses the leaps an octave-confused tracker invented.

    The centre is a CENTRED median over the four notes either side, not a
    running average of the notes before. A lagging reference drags behind a
    melody that is genuinely climbing and then folds a later note back
    down, which invents a leap rather than removing one: measured on the
    test cue, the lagging version turned 2 leaps into 3.
    """
    raw = [float(p) for _s, _l, p in notes]
    out = []
    for i, (start, length, pitch) in enumerate(notes):
        if fixed is not None and i < len(fixed) and fixed[i]:
            out.append((start, length, pitch))    # the spectrum vouches for
            continue                              # this octave: leave it
        lo = max(0, i - span)
        ref = float(np.median(raw[lo:i + span + 1]))
        p = float(pitch)
        while p - ref > window:
            p -= 12
        while ref - p > window:
            p += 12
        out.append((start, length, int(round(p))))
    return out


def build(sc, bass_lvl=12, lead_lvl=15, v2_lvl=7, v3_lvl=5, arp_lvl=5,
          arp_step=4, drum_lvl=12, bass_min=60.0, kick_len=5, hold=10,
          top=2700.0, fold=7, vib_cents=14.0, vib_frames=10,
          vib_after=8):
    """A transcription to six channels of chip, with nothing left out."""
    n = sc["frames"]
    o = Out(n)
    voices = sc.get("voices") or [[], []]

    def lay(ch, notes, level, fall, cap=top, vib=None):
        """A part onto a channel, note by note."""
        on = np.zeros(n, bool)
        for start, length, pitch in notes:
            hz = midi_hz(pitch)
            while hz > cap:                     # a square at 3 kHz whistles
                hz /= 2.0                       # over the arrangement
            for k in range(length):
                i = start + k
                if not (0 <= i < n):
                    continue
                f = hz
                if vib and length >= vib[2] and k >= vib[2]:
                    # a lead reads as a lead because it is doing something
                    # the texture is not. This is the cheapest such thing:
                    # the frequency byte moves by one, which near the top of
                    # the divider range is about 7 cents
                    depth = vib[0] * min(1.0, (k - vib[2]) / float(vib[2]))
                    f = hz * 2 ** (depth * math.sin(
                        2 * math.pi * (k - vib[2]) / vib[1]) / 1200.0)
                o.tone(ch, i, f, decay(level, k, fall))
                on[i] = True
        return on

    # the bass gets the same octave treatment as the lead: on one recording
    # its line leapt more than a seventh on 189 of 841 steps, with a median
    # note of eight frames, which is not a bass line but a tracker changing
    # its mind. The fold only moves notes the spectrum does not vouch for
    bass_on = np.zeros(n, bool)
    for start, length, pitch in fold_lead(sc["bass"], fold,
                                          fixed=sc.get("bass_fixed")):
        hz = midi_hz(pitch)
        while hz < bass_min:                 # nothing reproduces 37 Hz, and
            hz *= 2                          # the chip's bottom octave is mud
        for k in range(length):
            o.tone(0, start + k, hz, decay(bass_lvl, k, 0.12))
            if 0 <= start + k < n:
                bass_on[start + k] = True

    lead = fold_lead(sc["lead"], fold, fixed=sc.get("lead_fixed"))
    lead_on = lay(1, lead, lead_lvl, 0.06, vib=(vib_cents, vib_frames,
                                                vib_after))
    v2_on = lay(2, voices[0] if len(voices) > 0 else [], v2_lvl, 0.05)
    v3_on = lay(4, voices[1] if len(voices) > 1 else [], v3_lvl, 0.05)

    # Where the second voice found nothing, ch2 covers the lead - at the
    # octave the TRACKER said, not the one the fold chose. Folding the lead
    # into one register is what makes it read as a line, and it costs 3.5
    # points of peak coverage because the notes leave their real octave;
    # putting that octave back on the channel that would otherwise be idle
    # buys it straight back, and the unison never happens because the two
    # only differ where the fold moved something.
    for (start, length, pitch), (_s, _l, raw) in zip(lead, sc["lead"]):
        hz = midi_hz(raw if raw != pitch else pitch + 12)
        while hz > top:
            hz /= 2.0
        for k in range(length):
            i = start + k
            if 0 <= i < n and not v2_on[i]:
                o.tone(2, i, hz, decay(v2_lvl, k, 0.05))

    # the chord, arpeggiated, every frame of every chord - and the third
    # voice holds a chord tone wherever the tracker gave it nothing, so
    # neither channel ever falls silent mid-phrase
    for start, length, root, kind in sc["chords"]:
        # each chord tone at two octaves, alternating: six steps instead of
        # three, and it reaches into 260-520 Hz where otherwise only the
        # lead goes. Measured better in all three bands than a flat triad
        notes = [48 + root + s + o for s in TRIAD[kind] for o in (0, 12)]
        for k in range(0, length, arp_step):
            hz = midi_hz(notes[(k // arp_step) % len(notes)])
            for j in range(arp_step):
                i = start + k + j
                if 0 <= i < n:
                    o.tone(3, i, hz, decay(arp_lvl, j, 1.2))
        fill = midi_hz(notes[2])                # the fifth, up where it
        for k in range(length):                 # will not mud the root
            i = start + k
            if 0 <= i < n and not v3_on[i]:
                o.tone(4, i, fill * 2, max(0, v3_lvl - 3))

    # a part whose tracking drops out for a moment holds instead of
    # flickering: a note that stops for four frames and starts again is
    # heard as a fault, not as phrasing
    for ch, on in ((1, lead_on), (2, v2_on), (4, v3_on)):
        gap = 0
        for i in range(1, n):
            if o.sounded[ch, i]:
                gap = 0
                continue
            if o.sounded[ch, i - 1] or gap:
                gap += 1
                if gap <= hold:
                    o.oct[ch, i] = o.oct[ch, i - 1]
                    o.byte[ch, i] = o.byte[ch, i - 1]
                    lv = int(o.lvl[ch, i - 1]) - 1
                    if lv > 0:
                        o.lvl[ch, i] = lv
                        o.sounded[ch, i] = True
                    else:
                        gap = hold + 1
                else:
                    gap = hold + 1

    kicks = [q[0] for q in sc["drums"] if q[1] == "kick"]
    for j, (i, kind, vel) in enumerate(sc["drums"]):
        lv = int(round(drum_lvl * (0.55 + 0.45 * vel)))
        if kind == "kick":
            # how long the steal lasts depends on how soon the next kick is.
            # A track with eighth-note kicks would otherwise spend 30% of its
            # frames with no bass at all; an accent is enough
            nxt = next((q for q in kicks if q > i), i + 99)
            span = max(2, min(kick_len, nxt - i - 2))
            for k in range(span):            # a tone swept down, which is
                f = 150.0 * (0.55 ** (k / float(max(1, span - 1))))  # a kick,
                o.force(0, i + k, f, decay(lv, k, 2.2))      # on the bass
        elif kind == "snare":
            for k in range(5):
                o.hiss(5, i + k, 1, decay(lv, k, 2.2))
        else:
            for k in range(3):
                o.hiss(5, i + k, 0, decay(lv - 4, k, 3.0))
    return o


def arrange_score(sc, **kw):
    return build(sc, **kw).registers()
