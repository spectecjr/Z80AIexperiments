# reports/

**What the machine said**, checked in. Every T-state count and byte count in
`costs.md`, `tricks.md`, `demo-ideas.md` and the design notes came out of one
of these runs; this directory is the runs themselves, so a claim can be
diffed against its source rather than taken on trust.

    python3 tests/mkreports.py --all        # everything in tests/, as here
    python3 tests/mkreports.py              # or just the demos the notes quote
    python3 tests/mkreports.py chequer10    # or one of them

What is checked in is `--all`: every test in `tests/`, all passing. Most
take a second or two; `float16` takes six minutes and `float32` two,
because they are exhaustive over their inputs rather than sampled.

Each file is one test's output with a header saying whether it passed and
how long it took. They are *generated* — edit the test, not the report.
Two of them are studies rather than tests: `snd.txt` is what a 50 Hz music
tick costs inside a frame that cannot be interrupted (`sound.md`), and
`budget.txt` is whether a playable game fits in one (`game.md`). A third,
`machine.txt`, is the cross-check that the repository's two SAM models and
its assembly agree about the hardware - see `layout.md`.

**What is in one.** The demo tests all print the same three things:

- **memory**, chunk by chunk: what the map holds and what it claims. Those
  are not the same number and the difference is the point — a chunk gets a
  *pair* of 16K pages because that is what `LMPR` maps, so a bank of eleven
  chunks claims 352K however much of it is compiled code.
- **the picture**, compared byte for byte against a Python model of the same
  frame, over every camera position and horizon the demo can take. A
  mismatch is printed as the first differing byte with its row and column.
- **the cost**, in T-states: each piece of the frame measured by disabling
  the others, and then the whole frame over the sweep. 120,000 T-states is a
  50 Hz frame on a 6 MHz Z80B and 240,000 a 25 Hz one.

Some of them also print **memory traffic** — every fetch, read and write a
frame takes — because that, not time, is what the ASIC's contention is
charged on. `costs.md` §1b explains what to do with it.

**These are uncontended numbers.** The emulator runs a Z80 at full speed
against flat memory; a real SAM's ASIC steals cycles from the CPU while the
display is being fetched. See `costs.md` §1b and
`.claude/skills/sam-coupe-hardware`.
