# Compiled Sprites for SAM Coupé Mode 4 — v1 Plan (+ v2/v3 sketches)

> Decisions already taken: output targets **sjasmplus**; generator in **Python 3**; optimiser objective = **nominal Z80 T-states**; v1 clipping = **vertical only, and switchable off entirely**. Every (routine × form × alignment × parity) variant is a **separate output file**; alignment switches (`--x-align`, `--y-align`) control how many variants exist; **singleton and list ("looped") forms** are both generated; a **size/T-state table** is printed at the end of every run. Plan document to be checked in at `designs/compiled-sprites/PLAN.md` (milestone M0).

## Context

The repo is a scratch space for Z80 experiments (`8x8multiply_r16.z80s`, `main.z80s`). The next experiment is a *compiled sprite* toolchain: import a 16-colour sprite (with mask or transparent index), and generate — offline, with a generous CPU budget (minutes) — the fastest Z80 routine that draws it into a SAM Coupé mode-4 screen, plus companion routines to erase it (solid colour) or restore what was under it (from a saved copy or a clean back buffer). The renderer need not walk the screen in raster order; anything that is correct and faster is allowed. Command line only.

### Target facts the design leans on

- Mode 4: 256×192, 4 bpp, **2 pixels/byte, left pixel in the high nibble**, 128 bytes/line, linear: `addr = base + y*128 + x/2`; 24 576 bytes. `base` must be 256-aligned (any page boundary is). Default `base = 0x8000` → screen `0x8000..0xDFFF`, 8 K free at `0xE000..0xFFFF` in the same page pair = scratch for saved backgrounds, and `0x6000..0x7FFF` (section B) can serve as a top "spill" zone if the user lays memory out that way.
- Because rows are 128 bytes, **one 256-byte page holds exactly two rows** and **bit 7 of L is the row parity**. Consequences used everywhere: stepping down a row is `SET 7,L` (8T) or `INC H : RES 7,L` (12T) — *no address immediates* — and every `LD L,n` immediate is patchable by adding `x/2` without carry.
- Only **2 sub-byte X phases** (even/odd pixel), so 2 pre-shifted variants, not 4/8.
- Partially transparent bytes (one nibble opaque) need read-modify-write; masks per byte are one of `FF / F0 / 0F / 00`.

### Instruction menu and nominal costs (what the optimiser chooses between)

| Purpose | Instruction | T | bytes | notes |
|---|---|---|---|---|
| write 1 byte | `LD (HL),n` | 10 | 2 | HL = pointer |
| write 1 byte | `LD (HL),r` | 7 | 1 | r ∈ A,B,C,D,E holding a cached constant (`LD r,n` 7T/2B) |
| write 1 byte, no pointer moves | `LD (IX+d),n` / `LD (IX+d),r` | 19 | 4/3 | d covers 2 rows; `LD IX,nn` 14T; `INC IXH` 8T |
| write 2 bytes | `PUSH rr` | 11 | 1 | rr ∈ HL,DE,BC (+ HL',DE',BC' via `EXX` 4T); `PUSH IX/IY` 15T/2B; needs SP at run end, DI |
| load pair | `LD rr,nn` / `LD r,n` (half) | 10 / 7 | 3 / 2 | half-loads when one byte already matches |
| set SP | `LD SP,nn` / `LD SP,HL` / `LD SP,IX` | 10 / 6 / 10 | 3 / 1 / 2 | `DEC SP` 6T skips one byte |
| pointer move | `INC L`/`DEC L`/`INC H` | 4 | 1 | within page / +2 rows |
| pointer move | `SET 7,L` / `RES 7,L` | 8 | 2 | +128 / −128, patch-free |
| pointer re-seat | `LD L,n` / `LD HL,nn` | 7 / 10 | 2 / 3 | 1 / 2 patch points |
| RMW half byte | `LD A,(HL) : AND m : OR d : LD (HL),A` | 28 (22 with m,d in regs) | 6 | `RLD/RRD` investigated — cannot express "keep one nibble", rejected |
| copy | `LDI` | 16 | 2 | HL→DE both auto-increment |
| copy | `LD HL,(nn)` + `LD (nn),HL` | 32 / 2 bytes | 6 | pointer-free |
| copy (bounce) | `LD SP,src : POP×n : LD SP,dst : PUSH×n` | ≈10.5–12/byte | | up to 6 pairs (+IX/IY), DI |

A hand-written generic masked blitter costs ~50–60T/byte; the targets are ~14T/byte (HL immediate), ~7–8T/byte (HL + register cache) and **~5.5–7T/byte (stack)** for opaque runs. For a 16×16 opaque sprite that is ~1 000T vs ~7 500T.

## v1 Scope (deliverable)

`codesprite compile ship.png --transparent-index 0 --name spr_ship --budget 300 --out-dir out/spr_ship/` produces **one sjasmplus file per variant** (so users mix and match by `INCLUDE`), plus a manifest. The variant matrix is:

| axis | switch | values | effect |
|---|---|---|---|
| routine | `--routines` | `draw, erase, save, restore, restore_bb` | which routines to emit |
| form | `--form` | `single, list, both` (default both) | singleton call vs. loop over a list of screen addresses (tiles, repeated sprites) |
| X alignment | `--x-align` | `1` (any pixel → phases `xe`,`xo`), `2` (byte aligned → `xe` only) | number of pre-shifted variants |
| Y alignment | `--y-align` | `1` (parities `ye`,`yo` or a parity-patch slot), `2` (even rows only → one) | number of row-parity variants |
| relocation | `--reloc` | `patch` (SMC setpos; default for `single`), `register` (position-independent; default and required for `list`), `none` (fixed address) | how the position gets in |
| clipping | `--clip` | `none` (default; tiles), `y-spill`, `y-entry` | vertical clipping strategy; `none` frees the optimiser from any ordering constraint |

File naming: `<name>_<routine>_<form>_<xe|xo>[_<ye|yo>][_clipY].z80s`, e.g. `spr_ship_draw_list_xe_ye.z80s`; each file is self-contained (its own `setpos`/patch table when `--reloc patch`, its own metadata EQUs). `<name>_manifest.z80s` lists every variant as commented `INCLUDE` lines; `<name>_stats.json` and `<name>_SIZES.md` hold the table below.

Per routine, in every variant:

- `draw` — compiled renderer (opaque + half-transparent bytes; transparent bytes never touched).
- `setpos` (only with `--reloc patch`) — compiled self-modifying position patcher (see *Relocation*).
- `erase` — fills every touched byte with a solid colour `cc` (`--erase-color`), shape `cells|rows|bbox`.
- `save` / `restore` — copy the row spans under the sprite to/from a scratch area (`--scratch-base`, default `0xE000`, densely packed), and `restore_bb` — the same restore from a clean back buffer at a constant delta (`--backbuffer-base`).
- metadata EQUs: `_w/_h/_bytes`, `_tstates` (single: per call; list: prologue + per item + epilogue), `_size`, `_patches`, the palette (if the PNG had one) as SAM CLUT bytes.

**Size / cost table** — printed to stdout at the end of every compile and written to `<name>_SIZES.md` (+ JSON):

```
variant                         form    bytes  T(call)  T(item)  patches  lower-bound  gap
spr_ship_draw_single_xe_ye      single   1043     4712        -       19         3980   18%
spr_ship_draw_list_xe_ye        list     1011       88     4590        0         3980   15%
spr_ship_erase_single_xe        single    412     1988        -       17         1880    6%
...                                                                             total: 9 files, 7810 bytes
```

Plus `runtime/sprite_rt.z80s`: caller-side macros (`SPR_AT name,x,y` → computes the four patch registers and dispatches on x/y parity; `SPR_DRAW`, `SPR_ERASE`, `SPR_SAVE`, `SPR_RESTORE`; `SPR_LIST_BEGIN/ADD/END name` to build an address list on the stack and call the list form) and the documented register/interrupt contract.

Everything is verified by an in-repo Z80 subset emulator before it is written out (`--verify` on by default), and — when a `sjasmplus` binary is available — round-tripped through the real assembler and byte-compared against our own encoder.

### Out of scope for v1 (kept open by the IR; see v2)

Horizontal clipping (crop-and-compile via `--rect` is available), SAM contention-aware objective (the cost tables are pluggable and *reported*, nominal is the objective), sprite sheets/animation, SimCoupe-in-the-loop tests.

## Architecture

```
tools/codesprite/
  pyproject.toml                 deps: pillow; dev: pytest, hypothesis
  codesprite/
    cli.py                       compile | inspect | bench
    sprite.py                    Sprite (w, h, px[y][x] ∈ 0..15|None); PNG/txt/bin import; crop; shift(phase) -> ByteCells
    screen.py                    Mode-4 address model: base, stride, parity, addr(y,x), spill maths
    ir.py                        Cell(row,col,value,mask) · Piece(row, cols, mode, dir) · Plan · Program (Op list, every Op tagged (row,col), patch kinds)
    z80/isa.py                   Op dataclasses, encoder -> bytes, sjasmplus text, nominal T table
    z80/timing.py                cost tables: nominal (objective); sam_border/sam_display/sam_blend (report only, v1 stubs with TODO refs)
    z80/emu.py                   emulator for the emitted subset (64K RAM, cycle counter, SP/EXX/IX/IY, flags for AND/OR)
    codegen/navigate.py          pointer moves + patch bookkeeping (INC/DEC L, SET/RES 7,L, INC H, LD L,n, LD HL,nn, IX re-seat)
    codegen/regalloc.py          Belady (farthest-next-use) caches: 8-bit regs, 16-bit pairs with half-loads, EXX banks, IX/IY
    codegen/draw.py              Plan -> Program for draw (HL / STACK / IX modes, RMW)
    codegen/erase.py             same generator, all cells := cc, mask FF
    codegen/copy.py              save/restore/restore_bb (LDI chains, LD HL,(nn) pairs, POP/PUSH bounce)
    codegen/setpos.py            patch table -> unrolled setpos; clip entry preambles / exit boundaries
    codegen/forms.py             single vs list wrappers: prologue (shared register setup), per-item fetch, loop, epilogue
    codegen/variants.py          expands the (routine × form × x/y alignment × parity × clip) matrix into jobs
    codegen/peephole.py          final local cleanups
    optimize/baseline.py         greedy row-major plan (instant, always correct)
    optimize/evaluate.py         Plan -> (T, size, patches) via the real codegen (exactness by construction)
    optimize/anneal.py           simulated annealing over plans; budget, restarts, --jobs, --seed, checkpoints
    emit/sjasm.py                one file per variant: labels, EQUs, header (cmdline, sprite hash, stats)
    emit/report.py               size/T-state table (stdout + SIZES.md + JSON), manifest, lower bounds
    verify.py                    emulator-based equivalence for every routine, many positions/parities/backgrounds
  runtime/sprite_rt.z80s
  examples/  (txt sprites, a SAM demo .z80s that includes a generated module)
  tests/
designs/compiled-sprites/PLAN.md (+ later: MEMORY-LAYOUT.md, RUNTIME-PROTOCOL.md)
```

### 1. Sprite import (`sprite.py`)

- **PNG** (Pillow): indexed PNG → indices used as-is (must be < 16, else error); RGB/RGBA → `--palette pal.txt` (16 RGB triples, optional SAM colour codes) with exact match, `--nearest` to snap. Transparency: alpha < 128, **or** `--transparent-index N`, **or** `--mask mask.png` (non-zero = opaque). `--rect x,y,w,h` crops from a sheet.
- **txt**: one hex digit per pixel, `.` = transparent — used by tests and for hand authoring.
- **bin**: packed nibbles (`w/2` bytes per row, `w` even) + optional mask bin.
- `shift(phase)`: phase 1 (odd x) prepends a transparent pixel → byte width `ceil((w+1)/2)`; then pack into `ByteCells` with masks `FF/F0/0F` and drop `00`. This is the only place nibble maths lives.

### 2. Screen model (`screen.py`)

`addr(y,x) = base + y*128 + x//2` (16-bit wrap allowed for spill), `parity(y) = y & 1`, `pageH(y) = (base>>8) + (y>>1)`, `lowL(y,x) = (y&1)*128 + x//2`. Validates base alignment and that scratch/backbuffer regions don't overlap the screen.

### 3. IR (`ir.py`)

- `Cell(row, col, value, mask)` for the shifted sprite; cols are bytes.
- `Piece`: a contiguous span of cells in one row with `mode ∈ {HL, STACK, IX}` and `dir ∈ {L2R, R2L}` (STACK is always R2L physically, but the leftover-odd-byte end is a choice). Pieces may include interior transparent gaps if the plan says so (gap crossing = `INC L`s / `DEC SP`s, never a write).
- `Plan` = ordered list of pieces + global choices (`ptr_reg_for_sp ∈ {none, HL}`, pinned constants per bank — v1 keeps pins empty).
- `Program` = list of `Op`; each Op carries `(row, col)` provenance, `patch ∈ {None, L8, H8}` per immediate byte, and cost/size from `isa.py`. Provenance is what keeps v2 clipping schemes possible without redesign.

### 4. Code generation (`codegen/`)

**Machine state** tracked by the generator: contents of A, B, C, D, E (and primes), HL/DE/BC (+primes), IX, IY as known constants or "pointer"/"unknown"; active EXX bank; whether HL currently holds a valid screen pointer; SP validity.

**Draw, HL mode**: navigate to cell (`INC L`×k if k ≤ threshold, `SET/RES 7,L` + `INC H` for row moves, else `LD L,n` (1 patch) / `LD HL,nn` (2 patches)); write via `LD (HL),r` if cached else `LD (HL),n`; half-byte cells → RMW (mask/data from regs when cached). Serpentine row order falls out naturally because a reversed piece makes the row step patch-free.

**Draw, STACK mode**: `LD SP,nn` (2 patches) or `SET 7,L : LD SP,HL` when HL is the row pointer; pairs pushed R2L; odd leftover byte → HL/IX write; half-transparent bytes end a stack piece. `DI` at entry / `EI` at exit and `LD (.sp+1),SP … LD SP,nn` restore are emitted only if any stack op exists (`--stack di|raw|none`), and their fixed cost is part of the objective so tiny sprites don't pay for it.

**Draw, IX mode**: for isolated cells — `LD (IX+d),n` with IX re-seated every 2 rows; no interaction with HL/SP/data pairs.

**Register allocation**: given a fixed piece order the future is known, so 8-bit and 16-bit caches use Belady's farthest-next-use eviction with cost-aware admission (cache a byte only if ≥3 uses precede its eviction; prefer half-loads for pairs; EXX bank switch costed at 4T; IX/IY as slow overflow slots for pushes).

**Erase**: same generator over cells with `value = cc, mask = FF`, shape `cells|rows|bbox`. Will land on stack mode with all pairs = `cccc`.

**Save/Restore/Restore_bb**: shape = per-row span from first to last touched byte (full bytes, so half-byte cells are covered). Menu per span: LDI chain (dst pointer never re-seated because the scratch layout is dense), `LD HL,(nn)`/`LD (nn),HL` pairs, POP/PUSH register bounce. Restore is the mirror; restore_bb is the same with `src = dst + delta`. Ordering/mode chosen by the same annealer.

**Relocation (`--reloc patch`, default; `none` = fixed position, fastest)**: every address immediate byte gets a patch kind. Caller sets, from `(x,y)` with `q = y>>1`, `p = y&1`: `C = x/2 + p*128`, `B = x/2 + (1-p)*128`, `D = baseH + q`, `E = baseH + q + p`. L-immediates of even sprite rows are patched from C, odd rows from B; H-immediates from D/E likewise. `setpos` is emitted unrolled and sorted by `(reg, k)` so most patches are a bare `LD (nn),A` (13T) and only a change of `k` costs `LD A,r : ADD A,k` (11T). Half-transparent RMW and all `SET/RES/INC` navigation are patch-free. The optimiser counts patch cost with weight `--moves-per-draw` (default 1.0), so it will trade `LD L,n` against runs of `INC L` correctly. `setpos` also exists for erase/save/restore (they share the B/C/D/E contract).

**Relocation (`--reloc register`)** — required by the list form, optional for single: no self-modification. The caller (or the list loop) supplies HL = address of the sprite's top-left byte. Navigation is purely relative (`INC/DEC L`, `SET/RES 7,L`, `INC H`), stack rows use `LD SP,HL` from the pointer, and `LD L,n` re-seats are replaced by `LD A,L : ADD A,k : LD L,A` (15T) so the optimiser strongly prefers serpentine order and short `INC L` hops. `IX` mode re-seats with `PUSH HL : POP IX` (11+14T) instead of `LD IX,nn`. Row parity still selects `SET 7,L` vs `INC H : RES 7,L`, hence the `ye`/`yo` variants (or `--y-align 2`).

**Forms (`--form single|list|both`)**:

- *single*: `CALL name` after `setpos` (patch) or with HL set (register).
- *list*: for tiles and repeated sprites — register setup is done **once**, then the body runs for every address in a list. The list lives on the stack, as suggested: the caller pushes the return address, then the N screen addresses (last item first), sets `B = N`, and `JP`s to the routine; the routine `POP HL`s each item (10T), runs the body, `DJNZ` (13T), and finally `RET` lands on the return address. Bodies that use stack writes swap SP: `LD (.lst+1),SP` (20T) before the body and `.lst: LD SP,0` (10T) after — ~53T/item overhead; HL-only bodies pay 23T/item. The runtime macros `SPR_LIST_BEGIN/ADD/END` build the list. The register allocator treats the body as a loop: constants still live at the body's end are hoisted into the prologue, so identical tiles get their pairs loaded exactly once (`T(item)` in the table shows the marginal cost). Lists must contain one x/y phase only; the caller sorts items into up to four lists (one per variant file) — `SPR_LIST_ADD` does that bucketing.

**Y parity (`--y-parity variants|patch`, only when `--y-align 1`)**: `SET 7,L` vs `INC H : RES 7,L` alternate with y parity, so either emit two y-parity variants (4 routines total, fastest: 8/12T alternating) or emit a uniform 3-byte transition slot (`NOP : SET 7,L` ⇄ `INC H : RES 7,L`, 12T, patched by setpos only when parity changes). Default `variants`; `patch` halves code size.

**Vertical clipping (`--clip none|y-spill|y-entry`)**: `none` (default; the tile case) = caller keeps the sprite on screen and the optimiser has no ordering constraint. `spill` = no code change; setpos accepts signed y and the documented memory layout provides junk zones above/below the screen. `entry` = constrains piece order to be row-monotone, emits per-row entry stubs that reload the live register set at that boundary (top clip), and a boundary table of 3-byte slots where the runtime plants `JP exit` (bottom clip; slot bytes saved/restored by the runtime, ~160T only when clipping).

### 5. Optimiser (`optimize/`)

1. **Baseline** (ms): row-major, one piece per run, mode by simple rule (stack if run ≥ 4 opaque bytes), Belady caches. Always emitted if the budget is 0. Gives the upper bound and a correctness reference.
2. **Simulated annealing** over plans, evaluated by *running the real codegen* (so the cost is exact, not modelled). Moves: swap/relocate pieces, reverse a subsequence (2-opt), flip piece direction, split/merge pieces, merge across a small gap, toggle mode, toggle `ptr_reg_for_sp`. Objective: single form `T_draw + moves_per_draw·T_setpos`; list form `T_prologue/expected_list_len + T_item` (`--list-len`, default 16); `+ α·bytes` with `--objective weighted:α`. Each variant file is optimised independently (its own budget slice; `--jobs` parallelises across variants and restarts). Budget-driven schedule (`--budget`, default 60s), `--jobs N` independent restarts in processes, `--seed`, periodic checkpoint of the best plan, progress line on stderr, memoised plan-hash → cost.
3. **Polish**: peephole (e.g. `LD L,n` immediately after `LD HL,nn`, redundant `EXX` pairs, `INC L : DEC L`), then final verify.
4. **Reporting**: lower bound = Σ cells·(cheapest conceivable write) + minimal row overheads, so the JSON says how far from "provably optimal" the result is.

Python speed: a 32×32 sprite evaluates in a few ms → ~10⁵ evaluations per 5-minute budget per process; adequate for v1, and `--jobs` scales restarts. Hot-loop acceleration is a v2 item.

### 6. Emission (`emit/`)

sjasmplus syntax: `MODULE spr_ship … ENDMODULE`, `DEFB/DEFW`, local labels for patch points (`.p12: LD L,0` → address `.p12+1`), `EQU`s for metadata, a header comment with the command line, sprite hash, and per-routine cost/size for every timing table. Optional `--bin` via sjasmplus if present. Note: the existing `8x8multiply_r16.z80s` uses `\` for modulo, which sjasmplus does not accept; the generated module is self-contained and does not include it.

### 7. Verification (`verify.py`, `z80/emu.py`, tests)

- Emulator executes the generated `Program` (and, when sjasmplus is available, the *assembled bytes*, which also validates our encoder) on a 64 K image whose screen is random noise; result must equal the reference composite for: both x phases, both y parities, dozens of positions incl. spill positions, after `setpos` runs. Cycle counts from the emulator must equal the optimiser's claim.
- `save → draw → restore` returns the original screen; `erase` yields solid colour on exactly the shape; `restore_bb` equals the back buffer on the shape; `entry` clipping matches a clipped reference; SP is restored and nothing outside the screen/scratch is written (guard pages of canaries).
- Property tests (hypothesis): random sprites 1..48 px, random density incl. empty rows/cols and all-half-transparent bytes; random plans (any plan must be correct — correctness is independent of the optimiser).
- Golden test: a hand-made 16×16 opaque sprite must come out ≤ 1 100T, proving stack mode is being found.

### 8. CLI

```
codesprite compile SRC [--mask M] [--transparent-index N] [--palette P] [--rect x,y,w,h] [--nearest]
    --name NAME --out-dir DIR [--bin] [--sjasmplus PATH]
    [--routines draw,erase,save,restore,restore_bb] [--form single|list|both]
    [--x-align 1|2] [--y-align 1|2] [--y-parity variants|patch] [--reloc patch|register|none] [--clip none|y-spill|y-entry]
    [--screen-base 0x8000] [--scratch-base 0xE000] [--backbuffer-base 0x0000]
    [--erase-color N] [--erase-shape cells|rows|bbox] [--stack di|raw|none]
    [--budget SEC] [--jobs N] [--seed S] [--objective time|size|weighted:A] [--moves-per-draw F] [--list-len N]
    [--no-verify] [--progress]
codesprite inspect SRC …          cells, half-bytes, bbox, baseline cost, lower bound, variant count and estimated sizes
codesprite bench SRC …            cost vs budget curve (for tuning the annealer)
codesprite sizes DIR              re-print the size table from the manifest/JSON of a previous run
```

### 9. Test sprites

- **Synthetic**: txt sprites in `examples/` (solid 16×16, ring, diagonal line, checkerboard of half-bytes, 1-px dots, 48×48 blob) — these are the property/golden fixtures and are what CI runs.
- **Bubble Bobble (arcade / Atari ST)**: used as the realistic 16×16 4-bpp test set. The rips are Taito's copyright, so they are **not committed**; `tests/fixtures/fetch_external.py` downloads a sheet from a URL given in `tests/fixtures/external.toml` (Spriters Resource arcade and Atari ST Bubble Bobble sheets pre-filled), slices frames with `--rect`/grid metadata, caches under `tests/fixtures/external/` (git-ignored), and the tests that use them `skip` when the cache is empty. Note: this sandbox cannot reach spriters-resource.com (connection refused by network policy), so I will wire the fetcher and metadata but the first real download happens on the user's machine; a hand-drawn *original* Bub-style 16×16 dragon in txt format stands in for it in CI.
- The Bubble Bobble set doubles as the `bench` corpus: the SIZES table for the whole set (per frame, per variant) is checked in under `designs/compiled-sprites/bench/` after each optimiser change so regressions are visible in diffs.

## Milestones (in order; each ends green)

- **M0** — check this plan in at `designs/compiled-sprites/PLAN.md`; package skeleton, pyproject, pytest, CI workflow (python 3.11; sjasmplus step optional and cached).
- **M1** — `sprite.py`, `screen.py`, txt/PNG/bin import, shift/pack, unit tests.
- **M2** — `z80/isa.py` (ops, encoder, text, nominal T), `z80/emu.py`, tests that encode+emulate every op in the menu against known results.
- **M3** — `ir.py`, `codegen/draw.py` HL-immediate only, `navigate.py`, `emit/sjasm.py`, `verify.py` → **first end-to-end correct compiled sprite** (`--reloc none`).
- **M4** — register caches, STACK and IX modes, DI/SP save, `--reloc patch` (patch kinds + `setpos`) and `--reloc register`, x/y alignment switches and parity variants, **one file per variant + manifest + size table**; verification across positions/parities.
- **M5** — list form (stack-list protocol, loop-carried register hoisting, `T(item)` accounting), runtime macros incl. list builders; erase, save, restore, restore_bb; the SAM demo (moving sprite + a tile row drawn via the list form) assembles with sjasmplus.
- **M6** — annealer with budget/jobs/seed/checkpoints, lower bounds, JSON stats, `bench`, Bubble Bobble fetcher + bench corpus table.
- **M7** — `--clip y-spill|y-entry`, peephole, docs (`RUNTIME-PROTOCOL.md`, `MEMORY-LAYOUT.md`), examples.

## v2 sketch

- **Horizontal clipping**: auto-generated pre-clipped specialty routines per 8-px band (left/right), and a **column-patch** form for HL/IX-only programs (write ops of a column are NOP-able while navigation stays valid; the (row,col) provenance already gives the patch lists).
- List form v2: mixed-sprite lists (address + routine pointer per item), and *tile-map* compilation (a whole map row/screen of tiles as one routine with shared registers).
- **SAM contention models** as objective (`--timing sam_blend`), with sources (SAM technical manual / SimCoupe's timing) — every memory access rounded to 4T, 8T during active display in modes 3/4; re-rank PUSH vs LD (HL),n under that model.
- **Better search**: pinned-constant sets as plan variables, exact DP for within-row mode choice and for pair allocation of a single stack run, incremental re-evaluation, and a C/Rust evaluator (cffi) for 10–50× more iterations.
- **Animation sets**: sprite sheets, shared setpos, *delta frames* (compile only the cells that differ between consecutive frames, fused with the erase of vanished cells) and fused "restore old + draw new" for small movements.
- Known-background mode (half bytes become opaque), `PUSH AF` exploitation when F is known, POP-modify-PUSH hybrid for half bytes inside stack runs.
- SimCoupe-in-the-loop test: assemble the demo, run headless, dump the screen and compare; measure real frame cost with line interrupts.

## v3 sketch

- Whole-scene compilation: batches of sprites sharing register state and SP setup; a scene-level scheduler that interleaves erase/draw across sprites for minimal register churn.
- Runtime compiler on the SAM itself (compact tokenised sprite form → generated code in RAM) so large animation sets don't need all frames precompiled; the offline tool emits the token stream and the Z80 codegen.
- Additional targets with the same IR: SAM modes 1–3, ZX Spectrum (interleaved layout — the place where `INC H` tricks originated), MSX/CPC; full-screen delta "video" playback.
- Optimality tooling: ILP/CP-SAT formulation for small sprites to certify the annealer's results and calibrate its lower bounds.

## Verification of the plan itself (end-to-end acceptance for v1)

1. `pip install -e tools/codesprite[dev] && pytest` green (emulator, codegen, property tests).
2. `codesprite compile examples/ship16.txt --name spr_ship --budget 60 --out-dir out/spr_ship` finishes within budget, verify passes for every variant file, the size table prints, and draw ≤ ~1 100T for the opaque 16×16 example with a reported lower-bound gap; `--x-align 2 --y-align 2 --form list --clip none` yields exactly one draw file per routine.
3. With sjasmplus installed: `sjasmplus examples/demo_sam.z80s` assembles the demo that includes selected variant files and `runtime/sprite_rt.z80s`; bytes match our encoder (`--bin` diff).
4. Load the demo in SimCoupe (manual, v1) and see the sprite drawn, erased, and restored at moving positions including odd x and odd y.


---

## Changes since approval

Recorded as they were made, so this document stays a usable design record.

* **setpos needs three entry registers, not four.** The high byte of a row
  address is `D + (r + parity)/2`, a per-row offset from one register, not
  a choice between two parity registers.  `B`, `C` and `D` carry the whole
  contract; `E` is unused.
* **Register relocation cannot use the alternate bank.** `EXX` swaps `HL`,
  which is the anchor a relocatable routine navigates from.  Bodies built
  with `--reloc register` (including every list-form body) cache push
  values in the main bank only.
* **The list form reserves `B`.** It is the `DJNZ` counter, so `BC` cannot
  double as a data pair inside a list body.
* **Interrupt guarding moved to the caller.**  `--stack di|raw|none` became
  two orthogonal switches: `--stack allow|none` says whether the generator
  may write through SP at all, and `--interrupts caller|di` says who
  guards it.  The default is `caller`: one `DI`/`EI` around a batch of
  sprites is cheaper than guarding each routine.  SP is still saved and
  restored by the routine itself in every case.
* **Stack use is documented everywhere**, since it decides whether a caller
  needs interrupts off: a header line in each generated file, a
  `<label>_uses_stack` EQU, a `stack` column in the size table, a field in
  the JSON, and a note in the manifest.
* **Register contract simplified.** All registers are trashed - `AF`, `BC`,
  `DE`, `HL`, `IX`, `IY` and the alternate bank - and only SP is preserved.
* **An external assembler cross-check was added** (`emit/external.py`).
  sjasmplus is unavailable in the development sandbox, so `pasmo` is used
  to confirm every encoding byte for byte; sjasmplus-specific *syntax*
  remains unverified until it runs on a machine that has it.
* **`emit/parse.py` was added**: emitted text is parsed back and re-encoded,
  so a mistake in how an instruction prints is caught, not only how it
  encodes.
* **Scratchpads are passed in, not baked in.**  ``save`` and ``restore``
  take the scratch address in DE (``--scratch register``, the default), so
  each sprite instance owns its own area and one compiled routine serves
  them all.  It costs nothing - the pointer had to be loaded either way -
  and saves two bytes per routine.  ``<label>_scratch_bytes`` says how much
  an instance needs.  ``--scratch fixed`` restores the old behaviour.
* **The target memory map is confirmed**: code, data and stack in
  ``$0000-$7FFF`` so interrupts stay serviceable; the display file paged in
  whole at ``$8000-$DFFF``; ``$E000-$FFFF`` free in the same page.  Sprite
  code may be duplicated across paged banks with trampolines - generated
  routines do not care where they sit, beyond needing to be in RAM.  Mode 4
  putting the left pixel in the high nibble is confirmed too.
* **Optimisation is not yet a search.**  M6 is outstanding; today
  `optimize/evaluate.py` generates eight candidate plans and keeps the
  cheapest, which is honest but is not the annealer the plan describes.
