"""Model of the SAM Coupe MODE 4 cube renderer, to be matched exactly by the Z80."""
W, H, STRIDE = 256, 192, 128
FACES = [[3,1,0,2], [5,7,6,4], [1,5,4,0], [7,3,2,6], [4,6,2,0], [7,5,1,3]]  # +X -X +Y -Y +Z -Z

def cross(p0, p1, p2):
    return (p1[0]-p0[0])*(p2[1]-p0[1]) - (p1[1]-p0[1])*(p2[0]-p0[0])

def span(buf, y, x0, x1, colour):
    if x0 > x1 or y < 0 or y >= H:
        return
    x0 = max(0, x0); x1 = min(W-1, x1)
    base = y * STRIDE
    for x in range(x0, x1+1):
        i = base + (x >> 1)
        if x & 1:
            buf[i] = (buf[i] & 0xF0) | colour
        else:
            buf[i] = (buf[i] & 0x0F) | (colour << 4)

XL = [0]*192
XR = [0]*192

def fill_quad(buf, pts, colour):
    """Four screen points in winding order, convex, wound so cross > 0.

    Every edge is walked with Bresenham into one of two arrays - the
    descending edges into one, the ascending into the other - and then
    the spans between them are filled. No chain bookkeeping, no
    divisions, and each scanline gets exactly one entry per side.
    """
    ytop = min(p[1] for p in pts)
    ybot = max(p[1] for p in pts)
    if ytop == ybot:
        return
    for i in range(4):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) & 3]
        if y0 == y1:
            continue
        arr = XR if y1 > y0 else XL      # descending edges are the right side
        if y1 < y0:
            x0, y0, x1, y1 = x1, y1, x0, y0
        dxa = abs(x1 - x0)
        sx = 1 if x1 >= x0 else -1
        dy = y1 - y0
        err = dy >> 1
        x = x0
        for y in range(y0, y1):
            arr[y] = x
            err += dxa
            while err >= dy:
                err -= dy
                x += sx
    for y in range(ytop, ybot):
        span(buf, y, XL[y], XR[y], colour)

def render(screen_pts, colours):
    buf = bytearray(STRIDE * H)
    drawn = []
    for f, idx in enumerate(FACES):
        pts = [screen_pts[i] for i in idx]
        if cross(pts[0], pts[1], pts[2]) > 0:
            fill_quad(buf, pts, colours[f])
            drawn.append(f)
    return buf, drawn

def to_png(buf, path, pal=None):
    import zlib, struct
    pal = pal or [(0,0,0),(0,0,170),(170,0,0),(170,0,170),(0,170,0),(0,170,170),
                  (170,85,0),(170,170,170),(85,85,85),(85,85,255),(255,85,85),(255,85,255),
                  (85,255,85),(85,255,255),(255,255,85),(255,255,255)]
    raw = b""
    for y in range(H):
        row = b"\x00"
        for x in range(W):
            b = buf[y*STRIDE + (x>>1)]
            c = (b & 0x0F) if (x & 1) else (b >> 4)
            row += bytes(pal[c])
        raw += row
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t+d))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    open(path, "wb").write(png)
