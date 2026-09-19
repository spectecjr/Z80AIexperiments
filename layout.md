# Where things live

**One directory a project, and its tools inside it.** The root holds the
demos — their `.z80s` sources, their generated tables, and a design note
per demo — because that is what this repository started as and what most
of it still is. Everything that is its own thing gets a directory, and its
toolchain goes *in* that directory rather than in a shared one.

    root                the demos: chequer*, road*, zarch, wolf3d, ...
                        with a .md note each, and costs.md / tricks.md /
                        demo-ideas.md across all of them
    tests/              the demos' toolchain: the Python models that are
                        the specification, the harnesses, the generators
                        that write the .z80s tables, and the tests that
                        check one against the other
    demo/               the GIFs those tests record
    reports/            what the tests printed, checked in
    soundchip/          the SAA1099 work, with soundchip/tests/ beside it
    bubble/             the Bubble Bobble prototype, with bubble/tools/
    codesprite/         the compiled-sprite compiler, an installable
                        package with its own tests and CI
    designs/            plans and feature requests, which are neither
                        notes nor code

There is deliberately **no shared `tools/`**. There was one, and it was a
trap: it held one project's private toolchain under a name that promised a
general one, and two of its modules were called `sam.py` and `z80.py` —
the same names the demos' harness imports. Anything that ran with both on
`sys.path` would have got whichever came first.

## Three Z80 emulators, and that is correct

| | |
|---|---|
| the `z80` pip module | what `tests/bench.py` and `tests/sam.py` drive. Native, fast enough to redraw every frame of a sweep twice, and it is the one that produces the T-state counts in `costs.md` |
| `bubble/tools/z80.py` | pure Python, no dependencies, written to run a whole game prototype rather than to time a routine — and instrumented, which is what `bubble/tools/profile.py` attributes bus traffic by PC with |
| `codesprite/codesprite/z80/` | inside an installable package that must not depend on anything outside itself, used to verify generated code against its own model |

They are three answers to three different questions and merging them would
lose something each time: the pip module cannot be instrumented the way the
prototype needs, the pure-Python one is far too slow for a 156-frame sweep,
and the packaged one would stop being self-contained. **What is not
allowed is for them to disagree about the machine**, and that is what
`tests/test_machine.py` is for: the palette over all 256 CLUT bytes, the
paging ports in all three places they are written down (two Python models
and the assembly), the rule that a block maps a page and the one above it,
and the screen's geometry. It fails the day one of them drifts.

The same goes for the two SAM models — `tests/sam.py` is paging and timing
for calling a routine, `bubble/tools/sam.py` is paging, CLUT, keyboard and
a display decoder for running a program — and for the two GIF writers and
the two budget scripts, which measure different things for different
projects.

## The one inconsistency left

**Two assemblers.** The demos, the sound routines and `codesprite` all use
`sjasmplus`; `bubble/build.sh` uses `pasmo`, which is not installed here. `codesprite` already emits for
both and treats sjasmplus as the shipping target, so the prototype is the
odd one out — and on a machine with only sjasmplus installed, `bubble` is
the one thing here that will not build. Porting its sources is a real piece
of work rather than a rename, so it is written down here rather than done
quietly.

## What is not here

**A loader.** Everything in `tests/` is driven by Python: the bench sets the
paging registers itself, puts a stack at `7FF0` and calls a routine. A real
machine enters a demo at `8000` with ROM 0 in section A, the system page in
B, pages 1 and 2 in C and D, interrupts on and the stack somewhere in
`4000-7FFF` (see the hardware skill's **Demo configuration**), and the demo
has to `DI`, move its stack, set up its own paging and go. Nothing here does
that.

The shapes agree, which is the good news: the bench's stack lives in section
B and its code in the high block, exactly where the machine's entry state
puts them. What is missing is the part no measurement can stand in for - a
`LOAD CODE 32768` fills at most 32K, and `chequer10`'s map is 341K, so a
runnable version needs a bootstrap that loads and pages the rest from disk.
That is also the only thing standing between these routines and being timed
on real hardware rather than modelled.

## If you add something

- A new demo: sources and a `.md` note at the root, its model and
  generators in `tests/`, its GIF in `demo/`.
- A new project: a directory of its own, and its tools inside it.
- A tool two projects need: it does not exist yet. When it does, the
  question to ask first is whether the two projects really need the same
  thing or two things with the same name — the answer so far has always
  been the second.
