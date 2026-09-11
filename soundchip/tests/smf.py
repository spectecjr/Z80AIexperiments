#!/usr/bin/env python3
"""A standard MIDI file, as tracks of notes in seconds.

    python3 tests/smf.py score.mid

There is no MIDI library here and this needs no more than a reader, in the
same spirit as `ayreg.py` for VGM: parse the chunks, walk the delta times,
keep the note-ons and note-offs, and convert ticks to seconds through
whatever tempo map the file carries.

The awkward parts of the format, all of which turned up in real exports:

  - running status. A stream of note events omits the status byte when it
    repeats, so the parser has to remember the last one - and meta and
    sysex events must NOT overwrite it.
  - a note-on with velocity 0 is a note-off. Most sequencers write them.
  - several note-ons on one pitch before any note-off. They nest, so the
    ons are queued and each off closes the oldest.
  - tempo changes anywhere in any track, in a format-1 file where the map
    usually lives in track 1 but is not required to.
  - SMPTE division, where the tick rate is absolute rather than a
    subdivision of the beat.

Written by Claude (Opus) for the Z80AIexperiments repo.
"""
import struct
import sys


class Note(object):
    __slots__ = ("start", "end", "pitch", "velocity", "channel")

    def __init__(self, start, end, pitch, velocity, channel):
        self.start, self.end = start, end
        self.pitch, self.velocity, self.channel = pitch, velocity, channel

    @property
    def length(self):
        return self.end - self.start

    def __repr__(self):
        return "Note(%.3f..%.3f, %d, v%d, ch%d)" % (
            self.start, self.end, self.pitch, self.velocity, self.channel)


class Track(object):
    def __init__(self, index, name, notes, channels, programs):
        self.index, self.name = index, name
        self.notes = notes
        self.channels, self.programs = channels, programs

    def __repr__(self):
        return "Track(%d, %r, %d notes)" % (self.index, self.name,
                                            len(self.notes))


def _vlq(b, i):
    """A variable-length quantity, and where it ended."""
    v = 0
    while i < len(b):
        v = (v << 7) | (b[i] & 0x7F)
        more = b[i] & 0x80
        i += 1
        if not more:
            break
    return v, i


def _chunks(data):
    i = 0
    while i + 8 <= len(data):
        tag = data[i:i + 4]
        length = struct.unpack(">I", data[i + 4:i + 8])[0]
        yield tag, data[i + 8:i + 8 + length]
        i += 8 + length


def read(path):
    """A file as (tracks, ticks_per_beat, tempo_map, time_signatures).

    The tempo map is [(tick, microseconds_per_beat), ...] and is what makes
    ticks into seconds. Times on the notes are already in seconds.
    """
    data = open(path, "rb").read()
    fmt = ntrk = div = None
    raw = []
    for tag, body in _chunks(data):
        if tag == b"MThd" and len(body) >= 6:
            fmt, ntrk, div = struct.unpack(">HHH", body[:6])
        elif tag == b"MTrk":
            raw.append(body)
    if div is None:
        raise ValueError("no MThd chunk: not a MIDI file")

    smpte = bool(div & 0x8000)
    if smpte:                                   # absolute ticks a second
        frames = 256 - (div >> 8)
        ticks_per_second = frames * (div & 0xFF)
        ticks_per_beat = None
    else:
        ticks_per_beat = div
        ticks_per_second = None

    # pass one: every tempo and time signature, in ticks
    tempos, sigs = [], []
    for body in raw:
        t = i = 0
        while i < len(body):
            dt, i = _vlq(body, i)
            t += dt
            if i >= len(body):
                break
            st = body[i]
            if st == 0xFF:
                mt = body[i + 1]
                n, j = _vlq(body, i + 2)
                val = body[j:j + n]
                if mt == 0x51 and n == 3:
                    tempos.append((t, (val[0] << 16) | (val[1] << 8) | val[2]))
                elif mt == 0x58 and n >= 2:
                    sigs.append((t, val[0], 1 << val[1]))
                i = j + n
            elif st in (0xF0, 0xF7):
                n, j = _vlq(body, i + 1)
                i = j + n
            elif st & 0x80:
                i += 1 + (1 if (st & 0xF0) in (0xC0, 0xD0) else 2)
            else:                               # running status
                i += 1
    tempos.sort()
    if not tempos:
        tempos = [(0, 500000)]                  # the format's own default
    elif tempos[0][0] > 0:
        tempos.insert(0, (0, 500000))

    def seconds(tick):
        if ticks_per_second:
            return tick / float(ticks_per_second)
        out = 0.0
        prev_tick, prev_us = tempos[0]
        for tk, us in tempos[1:]:
            if tk >= tick:
                break
            out += (tk - prev_tick) * prev_us / 1e6 / ticks_per_beat
            prev_tick, prev_us = tk, us
        return out + (tick - prev_tick) * prev_us / 1e6 / ticks_per_beat

    # pass two: the notes
    tracks = []
    for index, body in enumerate(raw):
        t = i = 0
        status = None
        name = None
        pending = {}
        notes = []
        channels, programs = set(), set()
        while i < len(body):
            dt, i = _vlq(body, i)
            t += dt
            if i >= len(body):
                break
            st = body[i]
            if st == 0xFF:                      # meta: never sets running
                mt = body[i + 1]
                n, j = _vlq(body, i + 2)
                if mt == 0x03 and name is None:
                    name = body[j:j + n].decode("latin-1", "replace").strip()
                i = j + n
                continue
            if st in (0xF0, 0xF7):              # sysex: nor does this
                n, j = _vlq(body, i + 1)
                i = j + n
                continue
            if st & 0x80:
                status = st
                i += 1
            if status is None:
                i += 1
                continue
            kind, ch = status & 0xF0, status & 0x0F
            channels.add(ch)
            if kind in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                a, b = body[i], body[i + 1]
                i += 2
                if kind == 0x90 and b > 0:
                    pending.setdefault(a, []).append((t, b))
                elif kind == 0x80 or (kind == 0x90 and b == 0):
                    q = pending.get(a)
                    if q:
                        start, vel = q.pop(0)
                        notes.append(Note(seconds(start), seconds(t),
                                          a, vel, ch))
            elif kind in (0xC0, 0xD0):
                if kind == 0xC0:
                    programs.add(body[i])
                i += 1
            else:
                i += 1
        for pitch, q in pending.items():        # unclosed notes, held to here
            for start, vel in q:
                notes.append(Note(seconds(start), seconds(t), pitch, vel, ch
                                  if channels else 0))
        notes.sort(key=lambda q: (q.start, q.pitch))
        tracks.append(Track(index, name, notes, sorted(channels),
                            sorted(programs)))
    return tracks, ticks_per_beat, tempos, sigs


NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(p):
    return "%s%d" % (NAMES[int(p) % 12], int(p) // 12 - 1)


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip())
        return 2
    tracks, tpb, tempos, sigs = read(argv[1])
    print("  %d ticks a beat, %d tempo events, %d time signatures"
          % (tpb or 0, len(tempos), len(sigs)))
    for tick, us in tempos[:6]:
        print("    tick %-8d %.2f bpm" % (tick, 60e6 / us))
    for tick, n, d in sigs[:4]:
        print("    tick %-8d %d/%d" % (tick, n, d))
    total = sum(len(t.notes) for t in tracks)
    print("  %d tracks, %d notes" % (len(tracks), total))
    for t in tracks:
        if not t.notes:
            print("    %2d  %-22s  empty" % (t.index, (t.name or "-")[:22]))
            continue
        ps = [q.pitch for q in t.notes]
        ln = [q.length for q in t.notes]
        print("    %2d  %-22s %5d notes  %-4s..%-4s  %5.1f..%.1f s  "
              "median %.2f s  ch %s"
              % (t.index, (t.name or "-")[:22], len(t.notes),
                 note_name(min(ps)), note_name(max(ps)),
                 min(q.start for q in t.notes), max(q.end for q in t.notes),
                 sorted(ln)[len(ln) // 2], ",".join(map(str, t.channels))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
