# Picking this up on another machine

Everything here is in git and nothing is generated at clone time that is
not also checked in, so moving machines is a clone plus a handful of
tools. This is the list, taken from what the code actually invokes rather
than from memory.

    git clone <this repo>
    cd Z80AIexperiments
    python3 tests/mkreports.py --all      # the whole suite, ~9 minutes

If that ends in `ALL REPORTS WRITTEN` with no `FAILED`, the machine is
set up. Everything else below is about what it needs to get there.

## What has to be installed

| | for | check it |
|---|---|---|
| **Python 3.11+** | all of it | `python3 -V` |
| **`z80`** (pip) | the emulator every test drives - Kosarev's core, the same one SimCoupe uses | `python3 -c "import z80"` |
| **`sjasmplus`** | assembling everything except the Bubble Bobble prototype. v1.24 here; on `PATH`, or set `SJASMPLUS` | `sjasmplus --version` |
| **`numpy`**, **`pillow`** (pip) | the GIF recorder and the picture generators | `python3 -c "import numpy, PIL"` |

That is enough for the demos, the reports, the budget studies and the
contention test. The rest is per project:

| | for | |
|---|---|---|
| **`pasmo`** | `bubble/build.sh` only | the prototype is the one thing here not on sjasmplus; `layout.md` says so |
| **`pytest`** | `codesprite`'s 344 tests | `pytest codesprite -q` |
| **`hypothesis`** | codesprite's property tests | `pip install -e "codesprite[dev]"` gets both |
| **`soundfile`** | `soundchip`'s transcription tools, which read real recordings | the routines and their tests do not need it |
| **`mmh3`** | one cross-check in `test_murmur3.py`, which skips it when absent | |
| **SimCoupe** | running any of this as a program rather than a measurement | see below |

## What a desktop gets you that a container does not

**SimCoupe.** It needs SDL2, which is why this could not be built in the
container it was developed in. With it:

    python3 tests/mkcontend.py            # builds build/contend.sbt
    simcoupe build/contend.sbt            # boots and runs itself

and the contention test that `costs.md` §1b rests on can be re-run in
thirty seconds - press keypad `/` to break in, read `B`, `C` and `D`. They
should be **132, 26 and 90**. `tests/mkcontend.py` holds those as the
oracle, so if a change to the timing model moves them, it says so.

**And a machine to load a demo on.**

    python3 tests/mksbt10.py              # builds build/chequer10.sbt
    simcoupe build/chequer10.sbt          # boots it: chequer10, flying

is the demo itself, loader and all - see `loader.md`. With SimCoupe also
installed, `SIMCOUPE=... python3 tests/simshot10.py` boots it, grabs the
screen and compares what the machine drew against the model.

## Where things are

`layout.md` is the map: one directory a project, its tools inside it.
`costs.md` is every measured number, `tricks.md` is how they were got, and
`reports/` is what the machine actually printed for each of them. Start
with `costs.md` §1 for what the demos cost and §1b for why that is not the
number that binds.
