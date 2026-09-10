# chequer4.z80s — design notes

**chequer3's board with the depth stripes drawn in the pixels instead of
flipped in the palette.** Same picture — `demo/chequer4.gif` comes out
byte for byte `demo/chequer3.gif`, which is why only one of them is in the
repository — at **114,419 T-states, 95% of a 50 Hz frame**, against
chequer3's 110,556. Eighty T-states a scanline buys a palette that no
longer moves.

| | T-states | |
|---|---|---|
| `chequer3` (stripes in the palette) | 110,556 | 92% of a frame |
| **`chequer4`** (stripes in the pixels) | **114,419** | **95% of a frame** |
| measured spread | min 110,889, max 118,396 | over 273 camera positions |

## Why the palette was the wrong place for them

harrier and chequer3 draw the whole floor in two colour indices and let a
copper swap what those two indices *mean* on every scanline where the depth
crosses a square. It costs nothing in pixels, and on a SAM it costs three
things that do not show up in a T-state count:

- **It moves.** The swap rows come from `ztab[y] + camz`, so they change
  every frame: the CPU rebuilds the table (`chq3_par8`, 7,019 T-states) and
  the copper reads it.
- **It belongs to the other buffer.** The copper paints the frame being
  *displayed*, which is the one drawn last frame, so the parity table has to
  be double-buffered along with the screen or the stripes tear on the flip.
- **The fill cannot be interrupted.** `chq3_floor` runs with `DI` and the
  stack pointer walking the screen. A line interrupt taken during it would
  push a return address into the picture. So for most of the frame the
  copper cannot run at all — which is the part no amount of care fixes.

## The identity that moves them

The colour of a pixel is `1 + (((x - 128 + phi) / p) & 1)`, and the depth
parity adds one to that. Adding **one whole square to the phase** does the
same thing:

    1 + (((x - 128 + phi + p) / p) & 1)  ==  swap(1 + (((x - 128 + phi) / p) & 1))

`tests/chequer4.py` checks it over every width and every phase — 57 widths,
2,052 phases — because everything here rests on it.

So the stripes are a phase, and a phase of exactly one square is an
exchange of the two colours. That is worth stating the other way round:
**a run does not have to change to draw the other stripe.** A run is a
string of `PUSH`es, and what a `PUSH` pushes is a register.

## What it costs

`chequer4.z80s` **shares chequer3's run bank byte for byte** —
`chequer3run.z80s`, `chequer3runlo.z80s` and the entry tables inside them,
8,722 bytes of run and 3,204 of entry, unchanged and unregenerated. It
even keeps the label the runs return to. What changes is the six values a
scanline `POP`s into `BC`, `DE`, `HL`, `IX`, `IY` and `AF`: every value set
gains a complement — every byte `XOR 0x33` — sixteen bytes above it, which
is 416 bytes of table where chequer3 had 104.

Picking between them is a byte a scanline, `0x00` or `0x33`, built by
`chq4_msk8` (6,888 T-states, in place of `chq3_par8`'s 7,019):

| | |
|---|---|
| bit 4 of it | the offset from a value set to its complement |
| all of it | turns the row's last byte round |

so the row loop pays one `AND` and one `ADD` for the first job and one
`XOR` for the second.

    chq4_row:
            LD   A,(DE)             ; this row's mask
            XOR  0                  ; patched: the row's last byte
            LD   (HL),A
            LD   A,(DE)
            DEC  DE
            AND  0x10               ; the mask again, as the offset to
            ADD  A,0                ; the complement of this run's values
            EXX
            LD   L,A
            LD   H,0                ; patched: which values, and which way round
            LD   SP,HL
            POP  BC
            ...

## Where the eighty T-states went

| | T-states a scanline |
|---|---|
| the mask, twice, and what it patches — the last-byte store included, which is now `LD (HL),A` where it was `LD (HL),n` | +38 |
| `POP BC` and `POP DE`: the two colours come from the value set now | +20 |
| the row pointer walks by hand, because `DE` is the mask pointer | +15 |
| the value pointer through `HL` instead of a patched `LD SP,nn` | +7 |
| **the row loop** | **210 against chequer3's 130** |

The band loop gives about 50 of them back a band — it no longer patches the
last-byte store between `LD (HL),n` and `LD A,n`, and it no longer loads
`BC` and `DE` with the two colours — which over 57 bands is around 2,800
T-states, and the measured whole-frame difference is +3,863.

## What it does not fix

**The distance fog is still the palette.** The board is drawn in two
indices and graded with distance by a per-scanline palette, and that half
has not moved. What has changed is that the palette is now **the same on
every frame of the demo** — a fixed gradient, no per-frame table, nothing
to double-buffer, nothing that has to line up with a fill that cannot be
interrupted.

Moving that half into the pixels as well looks affordable, and the numbers
say why:

- the fog is 6 distinct colour pairs over the 84 board rows, not 84,
  because the SAM's palette quantises the gradient
- the whole picture — sky, haze and board — uses **14 distinct colours**,
  and MODE 4 has 16 entries, so it fits with two to spare
- the value sets are chosen per band already, so a band drawing its own
  two colours costs **nothing** at run time
- it would take 40 (value set, colour pair) combinations, 1,280 bytes
  against the 416 here, and the low block has 756 spare
- and 2 of the 57 width bands straddle a fog change, which the generator
  would fix by snapping that change to the band boundary — a row either way
  in a static gradient

That is a separate routine and a memory problem, not an edit to this one.

## Invariants

- Nothing between `POP AF` and the run may touch the flags, which is why
  the row's last byte is stored *before* the pops rather than after the
  run. Where the run reaches that byte it writes over it again.
- A value set and its complement must not straddle a 256-byte boundary:
  the row loop adds 16 to the low byte only. `ALIGN 32` a set-pair.
- `DE` in the alternate set is the mask pointer, so the row pointer steps
  by hand. Do not put −128 back in it.
- The board is drawn bottom upwards, or the overrun eats the row below.
- The geometry and the runs are chequer3's, and chequer3's are harrier's:
  regenerate `tests/mkchq3data.py` first if any of them change.

    python3 tests/mkchq4data.py     # regenerate the value sets and tables
    python3 tests/chequer4.py       # a square of phase is a colour swap
    python3 tests/test_chequer4.py  # verify against the model and time
