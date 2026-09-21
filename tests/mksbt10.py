#!/usr/bin/env python3
"""Build chequer10 into a file a SAM Coupe boots.

    python3 tests/mksbt10.py            # writes build/chequer10.sbt
    simcoupe build/chequer10.sbt        # or copy it to a blank disk, BOOT

`layout.md` called this the one thing between these demos and a
machine: an entry stub, a page map starting at page 1, and an image
built with each chunk at its page offset. This is it.

**A SAM CODE file loaded at 32768** fills page 1, then 2, then 3, so
byte offset n lands at page 1 + n/16384 and the image could simply BE
the memory map, with the buffers as holes in it. Two things stop that:

- **page 0 cannot be loaded into.** The map the bench verified puts the
  bank's first chunk there, with the stack at 0x7FFE.
- **a .sbt stops at the end of side 0.** SimCoupe presents the file as a
  chain of sectors and the chain does not survive the side change - the
  side 1 tracks under 4 are read as directory tracks and come back
  empty - so the file has **387,600 bytes**, and the 64K of holes over
  the buffers does not fit inside it.

So the image ships the chunks back to back and the loader puts them
where they belong: 23 pages, 376,832 bytes, and the map assembled at
run time in about two seconds of LDIR.

    page 1        the loader, the move table and the resident block
    pages 2-23    the eleven chunks, back to back, in bench order

`tests/sam_chq10_load.asm` is the loader and the comment at the top of
it is how it gets out of its own way.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from bench import assemble                          # noqa: E402
from sam import PAGE, SCREEN                        # noqa: E402

RESIDENT = "sam_chq10.asm"
CHUNKS = ("harness_chq9c0.asm", "harness_chq9c1.asm",
          "harness_chq9c2.asm",
          "harness_chq9msk0.asm", "harness_chq9msk1.asm",
          "harness_chq9c3.asm", "harness_chq9c4.asm",
          "harness_desert9_0.asm", "harness_desert9_1.asm",
          "harness_jetmove.asm", "harness_tree.asm")
SCREENS = (10, 12)              # what chequer4.z80s's CHQ4_SCR0/1 say
CODE_AT = 0xE000                # and where the resident block sits
HOME = 26                       # the pair the loader copies itself into
BOOT = 0x7500                   # and the six instructions that hand over,
                                # in chunk 0's spare: it is 29,832 of 32,768
TABLE = 0x1000                  # in the loader's page: the moves,
RES = 0x2000                    # and the resident block


def pages_for(chunks, screens):
    """The bench's allocation: two pages at a time, round the buffers."""
    taken, out, p = set(), [], 0
    for s in screens:
        taken |= {s, s + 1}
    while len(out) < len(chunks):
        if p not in taken and p + 1 not in taken:
            out.append(p)
        p += 2
    return out


def moves(chunk_pages):
    """Which page goes where, in an order that never loses one.

    The file has the chunks back to back from page 2; the map wants
    them at the bench's pages. Every chunk moves by two pages one way
    or the other, so the ones going up are done from the top down and
    the ones coming down from the bottom up, and no chunk is ever
    written over before it has been read.
    """
    want = []
    for i, p in enumerate(chunk_pages):
        for k in (0, 1):
            want.append((2 + 2 * i + k, p + k))     # file page, map page
    up = sorted((s, d) for s, d in want if d > s)
    down = sorted((s, d) for s, d in want if d < s)
    return [m for m in reversed(up)] + down


def build(out_path=None, quiet=False):
    resident, syms = assemble(RESIDENT)
    defs = {"CHQ4_RET": syms["chq4_ret"], "CHQ4_SCR": syms["CHQ4_SCREEN"],
            "C9_RET": syms["c9_ret"], "CQ9_R": syms["cq10_pret"],
            "CQ10_R": syms["cq10_ret"]}
    if len(resident) > 2 * PAGE - (CODE_AT & 0x3FFF):
        sys.exit("the resident block is %d bytes and the screen leaves %d"
                 % (len(resident), 2 * PAGE - (CODE_AT & 0x3FFF)))

    pages = pages_for(CHUNKS, SCREENS)
    bank = []
    for h, p in zip(CHUNKS, pages):
        img, s = assemble(h, defines=defs)
        bank.append((h, p, img))
        syms.update(s)

    image = bytearray((1 + 2 * len(CHUNKS)) * PAGE)     # pages 1..23

    def at(page, offset=0):
        return (page - 1) * PAGE + offset

    for i, (h, p, img) in enumerate(bank):              # back to back
        image[at(2 + 2 * i):at(2 + 2 * i) + len(img)] = img

    boot, _ = assemble("sam_chq10_boot.asm",
                       defines={"DEMO_BOOT": BOOT, "DEMO_GO": syms["demo_go"],
                                "DEMO_SCR0": SCREENS[0]})
    first = bank[0][2]                                  # chunk 0's own image,
    at0 = at(2, BOOT)                                   # where the file has it
    image[at0:at0 + len(boot)] = boot

    load, lsyms = assemble("sam_chq10_load.asm",
                           defines={"LOAD_SCR0": SCREENS[0],
                                    "LOAD_SCR1": SCREENS[1],
                                    "LOAD_RESLEN": len(resident),
                                    "LOAD_BOOT": BOOT})
    if len(load) > TABLE:
        sys.exit("the loader is %d bytes and the table is at 0x%04X"
                 % (len(load), TABLE))
    image[at(1):at(1) + len(load)] = load
    tab = bytearray()
    for src, dst in moves(pages):
        tab += bytes([src, dst])
    tab += b"\xFF"
    image[at(1, TABLE):at(1, TABLE) + len(tab)] = tab
    image[at(1, RES):at(1, RES) + len(resident)] = resident
    if len(first) > BOOT:
        sys.exit("chunk 0 is %d bytes and the hand-over stub is at 0x%04X"
                 % (len(first), BOOT))

    out_path = out_path or os.path.join(ROOT, "build", "chequer10.sbt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, "wb").write(bytes(image))
    if not quiet:
        report(out_path, image, resident, bank, load, tab, syms)
    return out_path, syms


def report(path, image, resident, bank, load, tab, syms):
    cap = 387600                # what a .sbt can hold: side 0 of the disk
    print("  %-40s %7d bytes, %d pages, %d spare under the .sbt limit"
          % (os.path.basename(path), len(image), len(image) // PAGE,
             cap - len(image)))
    print("  %-40s %7d bytes at 0x%04X, behind each buffer"
          % ("the resident block and the driver", len(resident), CODE_AT))
    print("  %-40s %7d bytes in %d chunks, moved into place as %d pages"
          % ("the bank", sum(len(i) for _, _, i in bank), len(bank),
             (len(tab) - 1) // 2))
    for i, (h, p, img) in enumerate(bank):
        name = h.replace("harness_", "").replace(".asm", "")
        print("    %-24s file %2d,%2d -> pages %2d,%2d  %6d bytes"
              % (name, 2 + 2 * i, 3 + 2 * i, p, p + 1, len(img)))
    print("  %-40s %7d bytes, and runs from page %d"
          % ("the loader", len(load), HOME))
    print("  %-40s 0x%04X, buffers on pages %s"
          % ("the demo starts at", syms["demo_go"],
             " and ".join(str(s) for s in SCREENS)))


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else None)
