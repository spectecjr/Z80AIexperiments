# vox.z80s — design notes

A Comanche-style heightmap flyover: one ray a screen column, stepped
outwards, the column filled from the bottom up. 313,302 T-states a frame,
19.2 Hz.

Verified bit-exact against `tests/vox.py` over 16 camera positions.

## Why this one is different

**There is no overdraw at all.** A column keeps a horizon — the highest row
drawn in it so far — and only draws where a sample rises above it. Every
screen byte is written exactly once. `wolf3d` prefills the viewport and
paints over 78% of what it wrote; this does not, and it is the only renderer
in the repo that can say so.

The price is that a *sample* is dear. Costed before writing any of it:

| | T-states |
|---|---|
| `x += dx`, `y += dy` | 30 (two 16-bit adds, plus the shuffling) |
| the cell's address | ~26 |
| height → screen row | 18 |
| compare with the horizon | 16 |
| the loop | 14 |
| **a hidden sample** | **~155** |

1,024 samples is 159,000 T-states, and the 8,192 bytes drawn are another
119,000 at the wide scaler's 14.5 each. The estimate before building was
17 Hz; it measured 19.2.

## Everything is arranged to make a sample cheap

- **The map is 16×16 and page-aligned**, so a cell's address is one byte —
  `roto.z80s`'s texel trick. The world tiles every 16 cells, and the ray
  steps one cell, so sixteen steps cross the map exactly once and the tiling
  never shows.
- **y is 4.12**, so its row is already in the top nibble of its high byte
  and needs no shifting — also `roto`'s. And for the same reason as `roto`:
  only `A` survives `EXX`, so the address byte has to be finished, both
  nibbles, before coming back.
- **Sixteen height levels and sixteen steps**, so the tables that turn a
  height into a screen row and into a colour are *both* indexed by
  `(h & 0xF0) | z` — no shifting at all. They sit in the two pages above the
  map, so `INC D` walks between them.
- **The step counts down**, so the loop test is `DEC C` / `JP P` and nothing
  else. The tables are generated with the step reversed to suit.
- **Indexing the colour by the step as well as the height** means the
  distance fade costs nothing.

## The fill

`wolf3d`'s wide scaler run, upwards: 64 groups of

    LD (HL),A / INC L / LD (HL),A / ADD HL,DE

with `DE` one row less one, entered as many groups from the end as there are
rows to fill — 14.5 T-states a byte. `HL` is left pointing at the next row
up, which is exactly where the next fill in that column starts, so nothing
is recomputed between them.

The viewport is 64 rows, which is what keeps a single fill under 64 groups
and so the run's entry to a **single patched byte**. A taller viewport needs
a two-page run and a 16-bit entry, which costs about 50 T-states a fill.

    alternate   HL = x, DE = y, BC = dx, SP = dy
    main        HL = the next row up in this column, B = the horizon,
                C = the step, DE = a table pointer, A = whatever

## Invariants

- `D` is the map page for the whole of a sample and is walked up to the row
  and colour pages with `INC D`. The fill uses `D` as scratch for the new
  horizon, so it is reloaded on the way out; the *hidden* path has to
  `DEC D` instead. Forgetting that one was the only bug: the next sample
  then reads the row table as if it were the map.
- The viewport must stay at 64 rows unless the fill run grows with it.
- `EXX` makes the *other* set active — load the ray after it, not before.

## What it costs

| | T-states |
|---|---|
| **`vx_frame`** | **min 305,525, mean 313,302, max 325,412** |
| | **19.2 Hz** — 1,024 samples and 8,192 bytes drawn |

Roughly half of that is sampling and a third is the fill. The optimisation
pass took it from 335,223 with the two trims above.

## If you pick this up

The obvious next thing is more depth: 24 or 32 steps would double the
horizon distance, at about 10,000 T-states a step. A 32×32 map costs six
more instructions a sample; a 64×64 one costs ten. Both are worth it if the
tiling starts to show, which at one cell a step and sixteen steps it does
not.

    python3 tests/mkvoxdata.py      # regenerate the map and tables
    python3 tests/test_vox.py       # verify and time
