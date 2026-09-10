"""The model for scroll8.z80s: a MODE 4 screen scrolled up by eight lines.

The whole of it is "everything moves down SHIFT bytes and the bottom
SHIFT bytes go black", which is not much of a model - but it is the
thing the Z80 has to match byte for byte, and the pattern generator
here is what makes a mis-copy show up rather than hide in a picture
that is mostly one colour.
"""

SCR = 0x8000            # where the display file lives in the harness
BPL = 128               # bytes a scanline in MODE 4
ROWS = 192
SIZE = BPL * ROWS       # 24,576
LINES = 8               # scanlines scrolled by
SHIFT = BPL * LINES     # 1,024
MOVE = SIZE - SHIFT     # 23,552, the bytes that actually move


def scroll(screen, lines=LINES):
    """The whole scroll: up by `lines`, black underneath."""
    n = BPL * lines
    return screen[n:] + bytes(n)


def clear(screen, lines=LINES):
    """Just the bottom `lines` scanlines blacked out."""
    n = BPL * lines
    return screen[:SIZE - n] + bytes(n)


def pattern(seed=0xACE1, n=SIZE):
    """n bytes off a 16-bit LFSR.

    Every byte differs from its neighbours and from the byte a line, a
    page and 1,024 bytes away, so a block copied to the wrong place, in
    the wrong order, or off by one shows as a mismatch rather than as a
    picture that still looks plausible.
    """
    out = bytearray(n)
    s = seed
    for i in range(n):
        for _ in range(8):
            bit = (s ^ (s >> 2) ^ (s >> 3) ^ (s >> 5)) & 1
            s = (s >> 1) | (bit << 15)
        out[i] = s & 0xFF
    return bytes(out)
