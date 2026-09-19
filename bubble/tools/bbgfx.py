#!/usr/bin/env python3
"""
bbgfx.py - Bubble Bobble asset pipeline for the SAM Coupe.

Emits bubble/gen/bb_gfx.z80s containing:

  * the 16-entry MODE 4 palette, in SAM CLUT encoding
  * the tile bank: tile 0 is the backdrop, tiles 1..16 are the autotiler's
    edge variants (4 bytes x 8 rows each)
  * the level bitmaps, 4 bytes x 24 rows, one bit per 8x8 cell
  * COMPILED SPRITES - straight-line Z80 that draws one sprite frame with
    no inner loop and no per-pixel branching - plus their descriptor table

Two compilers, because the two object classes have completely different
cost profiles on a contended SAM (see docs/BUBBLE_BOBBLE_SAM.md section 1):

  opaque  stack blitter. PUSH writes 2 bytes for 3 memory accesses, which
          is 1.5 acc/byte - the floor on this machine. A 16x16 circle is
          not a rectangle, so this variant bakes the backdrop colour into
          the transparent corners: correct, and self-erasing, wherever the
          object's box sits entirely on plain backdrop. Every solid object
          gets one, and bb_draw_one picks it when bb_box_is_flat agrees.

  masked  HL walker. Bubble Bobble's bubbles are hollow, so they cannot be
          drawn opaquely; transparent bytes are skipped with INC HL at
          1 access each, solid bytes cost 2-3, and only true nibble edges
          pay the 8-access read-modify-write.

Artwork: arcade rips are not redistributed with this repo. Drop 16x16 PNGs
into bubble/tools/art/ (bubble.png, player.png, enemy.png, fruit.png) with index 0
of their palette meaning transparent, and they are used as-is. Without them
the generator synthesises stand-ins at identical geometry so the prototype
still builds and runs.
"""

import os
import sys

OUT = os.path.join(os.path.dirname(__file__), "..", "gen", "bb_gfx.z80s")
ART = os.path.join(os.path.dirname(__file__), "art")

SPR_W, SPR_H = 16, 16          # arcade object geometry
CELL = 8
MAP_W, MAP_H = 32, 24

# --------------------------------------------------------------------------
# SAM colour encoding
#
# From the SAM Coupe Technical Manual: the CLUT byte is
#   bit 6 GRN1   bit 5 RED1   bit 4 BLU1
#   bit 3 BRIGHT
#   bit 2 GRN0   bit 1 RED0   bit 0 BLU0
# Two bits per channel plus one shared half-intensity bit: 128 colours.
# --------------------------------------------------------------------------

def sam_colour(r, g, b):
    """r, g, b in 0..7. Returns the CLUT byte."""
    def split(v):
        return (v >> 2) & 1, (v >> 1) & 1        # high bit, low bit
    rh, rl = split(r)
    gh, gl = split(g)
    bh, bl = split(b)
    bright = 1 if (r & 1) and (g & 1) and (b & 1) else 0
    return (gh << 6) | (rh << 5) | (bh << 4) | (bright << 3) \
         | (gl << 2) | (rl << 1) | bl

# Index 0 is the backdrop and must stay the level's background colour,
# because the erase fast path fills with it.
PALETTE = [
    (0, 0, 0),      #  0 backdrop, black
    (2, 0, 4),      #  1 platform shadow
    (4, 1, 6),      #  2 platform body
    (6, 3, 7),      #  3 platform highlight
    (0, 5, 0),      #  4 Bub green dark
    (2, 7, 2),      #  5 Bub green
    (5, 7, 5),      #  6 Bub green light
    (7, 7, 7),      #  7 white
    (7, 0, 0),      #  8 red
    (7, 4, 0),      #  9 orange
    (7, 7, 0),      # 10 yellow
    (0, 4, 7),      # 11 bubble sheen
    (3, 6, 7),      # 12 bubble body
    (0, 0, 5),      # 13 deep blue
    (5, 0, 5),      # 14 magenta
    (3, 3, 3),      # 15 grey
]

# --------------------------------------------------------------------------
# Artwork
# --------------------------------------------------------------------------

def load_png(name):
    """Return a 16x16 grid of palette indices, None meaning transparent."""
    path = os.path.join(ART, name)
    if not os.path.exists(path):
        return None
    try:
        import png                                   # pypng, optional
    except ImportError:
        sys.stderr.write("note: %s present but pypng is not installed; "
                         "using the synthesised stand-in\n" % name)
        return None
    r = png.Reader(filename=path)
    w, h, rows, info = r.read()
    if not info.get("palette"):
        sys.stderr.write("note: %s is not palettised; skipping\n" % name)
        return None
    out = []
    for row in rows:
        out.append([None if v == 0 else v for v in list(row)[:SPR_W]])
    return out[:SPR_H]


def disc(cx, cy, r):
    return lambda x, y: (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def make_bubble():
    """A hollow ring: the defining Bubble Bobble shape, and the reason the
    masked compiler exists at all."""
    g = [[None] * SPR_W for _ in range(SPR_H)]
    outer, inner = disc(7.5, 7.5, 7.6), disc(7.5, 7.5, 5.6)
    for y in range(SPR_H):
        for x in range(SPR_W):
            if outer(x, y) and not inner(x, y):
                g[y][x] = 12
    # sheen on the upper left, the way the arcade draws it
    for y in range(3, 7):
        for x in range(3, 7):
            if outer(x, y) and not inner(x, y):
                g[y][x] = 7
    for y in range(2, 5):
        for x in range(9, 12):
            if outer(x, y) and not inner(x, y):
                g[y][x] = 11
    return g


def make_blob(body, dark, light, eye=True):
    """A solid 16x16 actor: opaque, so it takes the stack blitter."""
    g = [[None] * SPR_W for _ in range(SPR_H)]
    d = disc(7.5, 8.5, 7.2)
    for y in range(SPR_H):
        for x in range(SPR_W):
            if d(x, y):
                g[y][x] = body
            elif y >= 13 and 2 <= x <= 13:
                g[y][x] = dark                        # feet
    for y in range(2, 6):
        for x in range(4, 11):
            if g[y][x] is not None:
                g[y][x] = light
    if eye:
        for y in range(5, 8):
            for x in range(8, 11):
                g[y][x] = 7
        g[6][9] = 0
    return g


def make_fruit():
    g = [[None] * SPR_W for _ in range(SPR_H)]
    d = disc(7.5, 9.0, 5.8)
    for y in range(SPR_H):
        for x in range(SPR_W):
            if d(x, y):
                g[y][x] = 8
    for y in range(5, 8):
        for x in range(5, 8):
            if g[y][x] is not None:
                g[y][x] = 9
    for y in range(1, 4):
        g[y][8] = 4
        g[y][9] = 4
    return g


# --------------------------------------------------------------------------
# Tiles
# --------------------------------------------------------------------------

def make_tiles():
    """Tile 0 is the backdrop. Tiles 1..16 are solid cells shaded by which
    of their four neighbours are also solid - the mask is %URDL, matching
    bb_autotile."""
    tiles = []
    tiles.append([[0] * CELL for _ in range(CELL)])          # backdrop
    for mask in range(16):
        up, right, down, left = (mask >> 3) & 1, (mask >> 2) & 1, \
                                (mask >> 1) & 1, mask & 1
        t = [[2] * CELL for _ in range(CELL)]
        if not up:
            t[0] = [3] * CELL                                # lit top edge
        if not down:
            t[CELL - 1] = [1] * CELL                         # shadow underneath
        for y in range(CELL):
            if not left:
                t[y][0] = 3 if not up or y == 0 else 2
            if not right:
                t[y][CELL - 1] = 1
        tiles.append(t)
    while len(tiles) < 32:
        tiles.append([[0] * CELL for _ in range(CELL)])
    return tiles


# --------------------------------------------------------------------------
# Levels
# --------------------------------------------------------------------------

def make_levels():
    """32x24 cells, one bit per cell, 4 bytes per row. A solid border makes
    the wind current a clean closed loop; the interior platforms are laid
    out the way an arcade screen is, in symmetric pairs."""
    levels = []

    def blank():
        g = [[0] * MAP_W for _ in range(MAP_H)]
        for x in range(MAP_W):
            g[0][x] = g[1][x] = 1
            g[MAP_H - 1][x] = g[MAP_H - 2][x] = 1
        for y in range(MAP_H):
            g[y][0] = g[y][MAP_W - 1] = 1
        return g

    g = blank()
    for x in range(4, 13):
        g[7][x] = 1
    for x in range(19, 28):
        g[7][x] = 1
    for x in range(8, 24):
        g[12][x] = 1
    for x in range(3, 11):
        g[17][x] = 1
    for x in range(21, 29):
        g[17][x] = 1
    levels.append(g)

    g = blank()
    for x in range(2, 30):
        if not (14 <= x <= 17):
            g[6][x] = 1
    for x in range(6, 26):
        if not (10 <= x <= 13) and not (18 <= x <= 21):
            g[11][x] = 1
    for x in range(2, 30):
        if not (14 <= x <= 17):
            g[16][x] = 1
    levels.append(g)

    return levels


def pack_level(g):
    out = []
    for y in range(MAP_H):
        for byte in range(MAP_W // 8):
            v = 0
            for bit in range(8):
                if g[y][byte * 8 + bit]:
                    v |= 0x80 >> bit
            out.append(v)
    return out


# --------------------------------------------------------------------------
# MODE 4 packing: two pixels per byte, high nibble is the left pixel
# --------------------------------------------------------------------------

def pack_row(pixels):
    """Returns a list of (value, mask) pairs, one per byte. mask has a set
    nibble wherever the byte must be left alone."""
    out = []
    for i in range(0, len(pixels), 2):
        hi, lo = pixels[i], pixels[i + 1]
        val = ((hi or 0) & 15) << 4 | ((lo or 0) & 15)
        mask = (0xF0 if hi is None else 0) | (0x0F if lo is None else 0)
        out.append((val, mask))
    return out


# --------------------------------------------------------------------------
# Sprite compilers
# --------------------------------------------------------------------------

class Emit:
    def __init__(self):
        self.lines = []
        self.acc = 0                                  # memory accesses

    def __call__(self, text, accesses, comment=""):
        pad = " " * max(1, 32 - len(text) - 16)
        self.lines.append("                %s%s; [%da]%s"
                          % (text, pad, accesses, (" " + comment) if comment else ""))
        self.acc += accesses


def compile_opaque(name, grid):
    """Stack blitter. SP walks the row right to left because PUSH writes
    downward and puts the low register byte at the lower address."""
    e = Emit()
    rows = [pack_row(r) for r in grid]
    width = len(rows[0])

    freq = {}
    for r in rows:
        for i in range(0, width, 2):
            pair = (r[i][0], r[i + 1][0])
            freq[pair] = freq.get(pair, 0) + 1
    hot = sorted(freq, key=lambda k: -freq[k])[:2]
    ix = hot[0] if len(hot) > 0 else None
    iy = hot[1] if len(hot) > 1 else None

    def word(pair):
        # PUSH rr writes the low register at the lower address, so the byte
        # at the lower screen address goes in the low half of the word.
        return pair[1] << 8 | pair[0]

    e("LD   (bb_savesp),SP", 6)
    e("LD   BC,SCR_STRIDE", 3)
    if ix is not None:
        e("LD   IX,$%04X" % word(ix), 4, "hottest byte pair")
    if iy is not None:
        e("LD   IY,$%04X" % word(iy), 4, "second hottest")
    e("LD   A,L", 1)
    e("ADD  A,%d" % width, 2, "HL -> one past the end of row 0")
    e("LD   L,A", 1)
    e("ADC  A,H", 1)
    e("SUB  L", 1)
    e("LD   H,A", 1)

    de = None
    for y, r in enumerate(rows):
        e("LD   SP,HL", 1, "row %d" % y)
        for i in range(width - 2, -2, -2):            # right to left
            pair = (r[i][0], r[i + 1][0])
            if pair == ix:
                e("PUSH IX", 4)
            elif pair == iy:
                e("PUSH IY", 4)
            else:
                if de != pair:
                    e("LD   DE,$%04X" % word(pair), 3)
                    de = pair
                e("PUSH DE", 3)
        e("ADD  HL,BC", 1)
    e("LD   SP,(bb_savesp)", 6)
    e("RET", 3)
    return e, "opaque"


def compile_masked(name, grid):
    """HL walker. Transparent bytes cost one access to step over, solid
    bytes two or three, and only genuine nibble edges pay the 8-access
    read-modify-write."""
    e = Emit()
    rows = [pack_row(r) for r in grid]
    width = len(rows[0])

    freq = {}
    for r in rows:
        for val, mask in r:
            if mask == 0:
                freq[val] = freq.get(val, 0) + 1
    hot = sorted(freq, key=lambda k: -freq[k])[:2]
    regc = hot[0] if len(hot) > 0 else None
    regb = hot[1] if len(hot) > 1 else None

    if regc is not None:
        e("LD   C,$%02X" % regc, 2, "most common solid byte")
    if regb is not None:
        e("LD   B,$%02X" % regb, 2, "second most common")

    for y, r in enumerate(rows):
        first = True
        for x, (val, mask) in enumerate(r):
            if mask == 0xFF:
                e("INC  HL", 1, "row %d skip" % y if first else "")
            elif mask == 0:
                if val == regc:
                    e("LD   (HL),C", 2, "row %d" % y if first else "")
                elif val == regb:
                    e("LD   (HL),B", 2, "row %d" % y if first else "")
                else:
                    e("LD   (HL),$%02X" % val, 3, "row %d" % y if first else "")
                e("INC  HL", 1)
            else:
                e("LD   A,(HL)", 2, "row %d edge" % y if first else "")
                e("AND  $%02X" % mask, 2)
                e("OR   $%02X" % (val & ~mask & 0xFF), 2)
                e("LD   (HL),A", 2)
                e("INC  HL", 1)
            first = False
        if y != len(rows) - 1:
            e("LD   A,L", 1)
            e("ADD  A,%d" % (128 - width), 2, "next row")
            e("LD   L,A", 1)
            e("ADC  A,H", 1)
            e("SUB  L", 1)
            e("LD   H,A", 1)
    e("RET", 3)
    return e, "masked"


# --------------------------------------------------------------------------

def opaque_grid(grid):
    """Same art with transparent pixels forced to the backdrop colour, so
    the frame becomes a solid rectangle the stack blitter can push."""
    return [[0 if p is None else p for p in row] for row in grid]


def compile_both(label, grid, hollow):
    """A hollow sprite gets only the masked routine - baking a backdrop
    rectangle behind a bubble would blank whatever it is floating over.
    Everything else gets both, and the renderer chooses per frame."""
    masked, _ = compile_masked(label, grid)
    if hollow:
        return masked, None
    opaque, _ = compile_opaque(label, opaque_grid(grid))
    return masked, opaque


def main():
    sprites = []                  # (label, grid, hollow)
    art = [("bubble", "bubble.png", make_bubble, True),
           ("player", "player.png", lambda: make_blob(5, 4, 6), False),
           ("enemy",  "enemy.png",  lambda: make_blob(14, 13, 8, eye=True), False),
           ("fruit",  "fruit.png",  make_fruit, False)]
    for label, png, gen, masked in art:
        grid = load_png(png) or gen()
        sprites.append((label, grid, masked))

    tiles = make_tiles()
    levels = make_levels()

    L = []
    w = L.append
    w(";" + "-" * 66)
    w("; bb_gfx.z80s - GENERATED by bubble/tools/bbgfx.py, do not edit by hand")
    w(";")
    w("; Compiled sprites: straight-line code, one instruction sequence per")
    w("; byte, chosen offline from that byte's transparency. Access counts")
    w("; in the right margin are exact, so the per-object figures in")
    w("; docs/BUBBLE_BOBBLE_SAM.md can be checked against the real code.")
    w(";" + "-" * 66)
    w("")

    w("; ---- palette -------------------------------------------------")
    w("bb_palette:")
    for i in range(0, 16, 8):
        vals = ", ".join("$%02X" % sam_colour(*PALETTE[j]) for j in range(i, i + 8))
        w("                DEFB %s" % vals)
    w("")

    w("; ---- tile bank (copied to bb_tilebank at startup) ------------")
    w("bb_tilesrc:")
    for n, t in enumerate(tiles):
        body = []
        for row in t:
            body.extend(v for v, m in pack_row(row))
        w("                ; tile %d" % n)
        for i in range(0, 32, 8):
            w("                DEFB %s" % ", ".join("$%02X" % b for b in body[i:i + 8]))
    w("BB_TILESRC_LEN  EQU $ - bb_tilesrc")
    w("")

    w("; ---- levels: 4 bytes x 24 rows, one bit per 8x8 cell ---------")
    w("bb_leveldata:")
    for n, g in enumerate(levels):
        packed = pack_level(g)
        w("                ; level %d" % n)
        for y in range(MAP_H):
            w("                DEFB %s"
              % ", ".join("$%02X" % b for b in packed[y * 4:y * 4 + 4]))
    w("BB_LEVEL_COUNT  EQU %d" % len(levels))
    w("")

    compiled = [(label, grid, hollow) + compile_both(label, grid, hollow)
                for label, grid, hollow in sprites]

    w("; ---- sprite descriptors --------------------------------------")
    w(";")
    w("; S_DRAW  is the general (masked) routine, always present.")
    w("; S_FILL  is the opaque stack-blitted routine, or 0 for a hollow")
    w(";         sprite. bb_draw_one uses it whenever the object's box is")
    w(";         entirely over plain backdrop.")
    for i, (label, _, _, _, _) in enumerate(compiled):
        w("SPR_%-11s EQU %d" % (label.upper(), i))
    w("bb_sprite_table:")
    for label, grid, hollow, m, o in compiled:
        w("                DEFB %d, %d, 0, 0" % (len(grid[0]) // 2, len(grid)))
        w("                DEFW bb_spr_%s, %s"
          % (label, ("bb_spro_%s" % label) if o else "0"))
    w("")

    for label, grid, hollow, m, o in compiled:
        w("; ---- bb_spr_%s: masked, %d accesses per draw" % (label, m.acc))
        w("bb_spr_%s:" % label)
        L.extend(m.lines)
        w("")
        if o:
            w("; ---- bb_spro_%s: opaque stack blit, %d accesses per draw"
              % (label, o.acc))
            w("bb_spro_%s:" % label)
            L.extend(o.lines)
            w("")

    w("; Measured, per 16x16 frame:")
    for label, grid, hollow, m, o in compiled:
        w(";   %-8s masked %4da%s"
          % (label, m.acc, ("   opaque %4da" % o.acc) if o else "   (hollow)"))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("\n".join(L) + "\n")

    print("wrote %s" % os.path.normpath(OUT))
    for label, grid, hollow, m, o in compiled:
        print("  %-8s masked %4da (%5d T in display)%s"
              % (label, m.acc, m.acc * 8,
                 "   opaque %4da (%5d T)" % (o.acc, o.acc * 8) if o else
                 "   hollow: no opaque variant"))


if __name__ == "__main__":
    main()
