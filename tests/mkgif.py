#!/usr/bin/env python3
"""Record the renderers running on the emulated Z80 as animated GIFs.

GIF is a good fit for a MODE 4 screen: sixteen colours and a palette,
which is what the SAM has. Frames after the first are stored as just
the rectangle that changed, which for the cube is a small part of the
screen and for the room is the viewport without its letterbox.

    python3 tests/mkgif.py [outdir]
"""
import sys

import numpy as np

from bench import Bench

CLEAR_BITS = 4                          # sixteen colours


def lzw(data, mcs=CLEAR_BITS):
    """GIF's variable width LZW."""
    clear, end = 1 << mcs, (1 << mcs) + 1
    out = bytearray()
    buf = bits = 0

    def emit(code, width):
        nonlocal buf, bits
        buf |= code << bits
        bits += width
        while bits >= 8:
            out.append(buf & 0xFF)
            buf >>= 8
            bits -= 8

    width = mcs + 1
    table = {}
    nxt = end + 1
    emit(clear, width)
    it = iter(data)
    cur = next(it)
    for sym in it:
        k = (cur << 4) | sym
        v = table.get(k)
        if v is not None:
            cur = v
            continue
        emit(cur, width)
        if nxt < 4096:
            table[k] = nxt
            nxt += 1
            if nxt == (1 << width) and width < 12:
                width += 1
        else:
            emit(clear, width)
            table.clear()
            nxt = end + 1
            width = mcs + 1
        cur = sym
    emit(cur, width)
    emit(end, width)
    if bits:
        out.append(buf & 0xFF)
    return bytes(out)


def unlzw(blob, mcs=CLEAR_BITS):
    """The other way, so the encoder can be checked against itself."""
    clear, end = 1 << mcs, (1 << mcs) + 1
    width = mcs + 1
    table = {i: bytes([i]) for i in range(clear)}
    nxt = end + 1
    out = bytearray()
    buf = bits = pos = 0
    prev = None
    while True:
        while bits < width:
            if pos >= len(blob):
                return bytes(out)
            buf |= blob[pos] << bits
            bits += 8
            pos += 1
        code = buf & ((1 << width) - 1)
        buf >>= width
        bits -= width
        if code == clear:
            table = {i: bytes([i]) for i in range(clear)}
            nxt = end + 1
            width = mcs + 1
            prev = None
            continue
        if code == end:
            return bytes(out)
        if code in table:
            entry = table[code]
        else:
            entry = prev + prev[:1]
        out += entry
        if prev is not None and nxt < 4096:
            table[nxt] = prev + entry[:1]
            nxt += 1
            # the decoder's table is one entry behind the encoder's, so
            # it has to widen one code earlier than the encoder does
            if nxt == (1 << width) - 1 and width < 12:
                width += 1
        prev = entry


def blocks(blob):
    out = bytearray()
    for i in range(0, len(blob), 255):
        chunk = blob[i:i + 255]
        out.append(len(chunk))
        out += chunk
    out.append(0)
    return bytes(out)


def write_gif(path, frames, palette, delay, check=True):
    """frames: list of (H, W) uint8 arrays of palette indices."""
    h, w = frames[0].shape
    out = bytearray(b"GIF89a")
    out += bytes([w & 255, w >> 8, h & 255, h >> 8, 0xF3, 0, 0])
    for r, g, b in palette:
        out += bytes([r, g, b])
    out += b"\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00"
    prev = None
    for f in frames:
        if prev is None:
            x0, y0, sub = 0, 0, f
        else:
            ys, xs = np.nonzero(f != prev)
            if len(ys) == 0:                    # nothing moved: a dot
                x0, y0, sub = 0, 0, f[:1, :1]
            else:
                y0, y1 = int(ys.min()), int(ys.max()) + 1
                x0, x1 = int(xs.min()), int(xs.max()) + 1
                sub = f[y0:y1, x0:x1]
        sh, sw = sub.shape
        out += bytes([0x21, 0xF9, 0x04, 0x04, delay & 255, delay >> 8, 0, 0])
        out += bytes([0x2C, x0 & 255, x0 >> 8, y0 & 255, y0 >> 8,
                      sw & 255, sw >> 8, sh & 255, sh >> 8, 0x00])
        flat = sub.reshape(-1).tolist()
        blob = lzw(flat)
        if check:
            assert unlzw(blob) == bytes(flat), "LZW round trip failed"
        out += bytes([CLEAR_BITS]) + blocks(blob)
        prev = f
    out += b"\x3B"
    open(path, "wb").write(bytes(out))
    return len(out)


def unpack(raw):
    """A MODE 4 buffer into one byte a pixel."""
    b = np.frombuffer(raw, dtype=np.uint8).reshape(192, 128)
    img = np.empty((192, 256), np.uint8)
    img[:, 0::2] = b >> 4
    img[:, 1::2] = b & 15
    return img


BUF = {0x80: 0x8000, 0x20: 0x2000}

CUBE_PAL = ([(32 * i, 10 * i, 8 * i) for i in range(8)]
            + [(8 * i, 13 * i, 32 * i) for i in range(8)])

ROOM_PAL = ([(0, 0, 0)]
            + [(28 + 32 * i, 12 + 13 * i, 9 + 8 * i) for i in range(6)]
            + [(72, 60, 44)]
            + [(10 + 11 * i, 15 + 15 * i, 32 + 32 * i) for i in range(6)]
            + [(24, 24, 42)]
            + [(255, 255, 255)])


def cube(outdir, seconds=10):
    """renderlit at its measured rate: 112,221 T-states a frame, 50 Hz."""
    b = Bench("harness_renderlit.asm", org=0)
    s = b.syms
    b.call_regs(s["demo_init"])
    b.call_regs(s["rndl_init"])
    n = seconds * 50
    frames = []
    for _ in range(n):
        b.call_regs(s["demo_frame"])
        into = b.peek(s["rndl_back"], 1)[0]
        b.call_regs(s["rndl_frame"])
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/lit_cube.gif" % outdir
    size = write_gif(p, frames, CUBE_PAL, 2)
    print("  %-16s %d frames at 50 Hz, %.1f KB" % (p, n, size / 1024))


def room(outdir, seconds=10):
    """room3d at its measured rate: 291,953 T-states a frame, 20 Hz."""
    import math
    b = Bench("harness_room.asm", org=0)
    s = b.syms
    b.call_regs(s["r3d_init"])
    n = seconds * 20
    frames = []
    for t in range(n):
        cx = int(45 * math.sin(2 * math.pi * t / 200))   # a wander that
        cz = int(35 * math.cos(2 * math.pi * t / 150))   # keeps corners
        ca = (t * 3) & 255                               # in view
        b.poke(s["r3d_cx"], (cx & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["r3d_cz"], (cz & 0xFFFF).to_bytes(2, "little"))
        b.poke(s["r3d_ca"], bytes([ca]))
        into = b.peek(s["r3d_back"], 1)[0]
        b.call_regs(s["r3d_frame"])
        frames.append(unpack(b.peek(BUF[into], 128 * 192)))
    p = "%s/room.gif" % outdir
    size = write_gif(p, frames, ROOM_PAL, 5)
    print("  %-16s %d frames at 20 Hz, %.1f KB" % (p, n, size / 1024))


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "/tmp"
    cube(d)
    room(d)
