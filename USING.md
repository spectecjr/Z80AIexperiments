# USING.md — running the converter yourself

Nothing here needs me, a network, or an account. It is Python and two
libraries.

## What you need

| | |
|---|---|
| Python | 3.8 or later (developed on 3.11) |
| numpy | any recent version (developed on 2.4) |
| soundfile | 0.12+, and **libsndfile 1.1 or later** for MP3 |

    pip install numpy soundfile

If `soundfile` reports a libsndfile older than 1.1 it cannot read or write
MP3. Convert to WAV first with anything (`ffmpeg -i song.mp3 song.wav`) and
point the tool at that; everything else works unchanged.

Then clone the repository and work from its root. No build step.

## One command

    python3 tests/chipify.py song.mp3

writes four files beside the input:

| | |
|---|---|
| `song-chip.wav` | the chip, rendered by the emulator in `saa1099.py` |
| `song-chip.mp3` | the same, if libsndfile can write one |
| **`song-chip.log`** | **the register log** — the actual deliverable |
| `song-chip.txt` | what `chipdis.py` makes of that log, read back |

The `.log` is the point of all this. It is a text file of `(register,
value)` pairs a frame at 50 Hz — SAA1099 registers, which is what a SAM
Coupé would need to be fed to play the thing. The wav is only how you
listen to it here.

A three-minute recording takes about a minute.

## The options that matter

    --refit          search each two-second segment's octaves and levels
                     against the recording, keeping only changes that
                     improve BOTH measures. Twelve to twenty minutes on a
                     three-minute track, and worth it - about three points
                     of perceptual fit and two of note coverage.

    --melody struck  when the tune is played on something struck - a bell,
                     a mallet, a plucked string - underneath a louder
                     sustained part. The default follows whichever line
                     carries the most energy, which on that material is
                     the pad. There is no way to detect this automatically;
                     see chiparr.md.

    --detune N       chorus depth in divider units (default 2, 0 for none).
                     Two channels on one note N dividers apart beat at
                     0.4 to 2.2 Hz, which is the only timbre control the
                     chip has.

    --chorus-steals  give up a voice to get that chorus in the audio path.
                     Fuller, and it measured 12 points of note coverage
                     worse. Try it and decide by ear.

    --start S --length L    work on an excerpt, for trying settings out
                            quickly.

## From a MIDI score instead

    python3 tests/chipify.py song.mid --audio song.mp3

The `--audio` is optional and only used to measure the result. A score
gives exact notes and exact timing, and it lets the part names decide which
channel gets what — a track called "Bell" or "Lead" becomes the melody, one
called "Contrabass" or "Sub" the bass, one called "drawbars", "Organ",
"Choir", "Pad" or "String" the harmony, and channel 10 the drums. Anything
unnamed is sorted by register.

Export with the note data in it: two exports arrived here containing only
track names and a tempo, and the tool will tell you if that happens rather
than producing silence.

## Reading the result

    python3 tests/chipdis.py song-chip.log

`chipdis.py` reads a register log back and describes it in musical terms -
notes, glides, vibrato, detuned pairs and their beat rates, which channels
are ganged. It is how most of the bugs in this repo were found, including
an arpeggio that turned out to be running at 12.5 Hz against the music.

## Measuring it

    python3 tests/percept.py song.wav song-chip.wav     # how close it sounds
    python3 tests/cover.py  song.wav song-chip.log      # how many notes are there
    python3 tests/probe.py  song.wav 20 75              # which line is the tune
    python3 tests/ground.py song.wav song.mid           # trackers against a score

`percept.md` explains what those percentages do and do not mean. The short
version: they are good at catching an octave error or a part that has
fallen silent, and they cannot tell you which part is the melody - asked
that, they give the wrong answer by about a point and a half.

## When it sounds wrong

| what you hear | what to try |
|---|---|
| the melody is the pad, not the tune | `--melody struck` |
| thin | `--detune 0` and `--chorus-steals` are opposites; try both |
| out of time | check the bpm the tool prints against what you played |
| notes too long or short | that is `trim_tails` and the bass mode filter; both are calibrated against one score and may not suit yours |

The bpm line is worth reading every time. It prints the grid it found, and
the tempo's octave is not decidable from audio: a printed 80 bpm on music
written at 160 means it found the eighth-note grid, which is the same grid.
If it prints something unrelated to what you played, everything downstream
is wrong and that is the first thing to fix.
