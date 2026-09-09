# codesprite

Compiles a sprite into Z80 code that draws itself, for the SAM Coupé in
mode 4 (256×192, 16 colours, 4bpp, 128 bytes/line, linear).

Instead of a general blitter looping over pixel data and masks, each
sprite becomes straight-line code with the pixel values baked in as
immediate operands, transparent bytes simply absent, and the fastest
write path the Z80 offers used wherever it fits. The design document is
`designs/compiled-sprites/PLAN.md` at the repository root.

## Setup

```sh
pip install -e "tools/codesprite[dev]"      # pillow; pytest + hypothesis for dev
pytest tools/codesprite -q
```

Optional but recommended — an external assembler to cross-check the
generated encodings (any one of these; the tests skip if none is found):

```sh
apt-get install pasmo z80asm                # both fine for encoding checks
# sjasmplus is the shipping syntax target: build from
# https://github.com/z00m128/sjasmplus if you want the full check
```

## Use

```sh
# fixed position, both x phases
codesprite compile ship.png --transparent-index 0 --name spr_ship --out-dir out

# relocatable by self-modification: setpos then draw
codesprite compile ship.png --name spr_ship --out-dir out --reloc patch \
    --routines draw,erase,save,restore

# byte-aligned, even rows only, drawn from a list of addresses (tiles)
codesprite compile tile.txt --name tile --out-dir out \
    --reloc register --form list --x-align 2 --y-align 2

codesprite inspect ship.png      # cells, half-bytes, lower bound
codesprite sizes out             # re-print a previous run's table
```

Every run prints a size/T-state table and writes `<name>_SIZES.md`,
`<name>_stats.json` and an `INCLUDE` manifest. One file per variant, so a
project includes only what it uses.

### Options that shape the variant matrix

| switch | meaning |
|---|---|
| `--routines` | `draw`, `erase`, `save`, `restore`, `restore_bb` |
| `--form` | `single` (call it once) or `list` (loop over stacked addresses) |
| `--x-align` | `1` = any pixel (two pre-shifts) · `2` = byte aligned (one) |
| `--y-align` | `1` = any row (two row-step encodings) · `2` = even rows only |
| `--reloc` | `none` (fixed) · `patch` (self-modifying setpos) · `register` (HL) |
| `--clip` | `none` today; `y-spill`/`y-entry` are M7 |
| `--mode` | `best` (cost every candidate plan) · `hl` · `stack` · `ix` · `auto` |
| `--stack` | `di` (guard stack writes with DI/EI) · `raw` |

## Sprite input

`.txt` (one hex digit per pixel, `.` = transparent), indexed `.png`
(alpha, `--transparent-index` or `--mask`), or raw `.bin` with packed
nibbles. `--rect x,y,w,h` crops a frame out of a sheet.

## How it is checked

Nothing is written out that has not been run:

1. the generated program is **assembled to bytes and executed** in an
   emulator over a randomised screen, and compared with a reference
   composite drawn in Python — for both x phases, both y parities, many
   positions, and (for patched builds) after `setpos` has moved it;
2. it must touch nothing outside the display file, restore SP, and match
   the cost model's T-state count exactly;
3. the emitted **text** is parsed back and re-encoded, so a mistake in how
   an instruction prints is caught as well as how it encodes;
4. when an assembler is installed, the whole module is assembled
   externally and compared byte for byte.

`save → draw → restore` round-trips are checked to return the screen
unchanged, and the list form is checked to consume exactly its items.

## State

Working: sprite import, the IR, HL/stack/IX write modes, register caching
across both banks, all three relocation modes, the variant matrix, single
and list forms, draw/erase/save/restore/restore_bb, the size table, and
the verification stack above. 328 tests.

Not done yet: the annealer (M6 — today it costs eight candidate plans and
keeps the best, which is not a search), vertical clipping (M7), and a
realistic sprite corpus.

Measured, nominal T-states, verified in the emulator:

| sprite | cells | naive HL writes | best | T/byte |
|---|---|---|---|---|
| solid 16×16 | 128 | 1858 | 912 | 7.1 |
| ring 16×16 | 96 | 1570 | 1480 | 15.4 |
| ship 14×12 | 55 | 1012 | 1012 | 18.4 |

## Open questions for the target machine

These are assumptions the generator makes; correcting any of them is
cheap, and each is isolated to one place:

* **Screen at `$8000`, contiguous** (`HMPR = VMPR`), leaving `$E000-$FFFF`
  for save/restore scratch. Everything about row stepping depends on the
  24K display file being contiguous in the CPU's address space
  (`codesprite/screen.py`).
* **Where the generated code lives**, and that it is paged in throughout —
  patched routines rewrite their own immediates, so they cannot be in ROM.
* **Interrupt policy.** Stack writes point SP into the display file, so
  those sections currently `DI`/`EI`. If you keep interrupts off for the
  whole frame anyway, `--stack raw` saves 8T per routine.
* **IY and the alternate bank** are used freely (IY is not, actually —
  only `AF`, `BC`, `DE`, `HL`, `IX` and `BC'/DE'/HL'`). Say so if an
  interrupt handler needs any of them preserved.
* **CLUT byte encoding**, if you want palettes emitted as SAM colour
  bytes rather than RGB comments.

## Layout

```
codesprite/
  sprite.py      import and pack into mode 4 byte cells
  screen.py      the address model (stride, parity, paging assumptions)
  ir.py          Piece / Plan / Program, with (row,col) on every op
  z80/isa.py     the emitted instruction subset: encoding, text, timing
  z80/emu.py     emulator used as the correctness oracle
  codegen/       navigate, draw, erase, copy, setpos, forms, regalloc
  optimize/      baseline plans and candidate evaluation
  emit/          sjasmplus output, size report, parser, external check
  verify.py      run-and-compare for every routine shape
runtime/sprite_rt.z80s   caller-side macros and the register contract
examples/                sprites, committed generated output, a demo
```
