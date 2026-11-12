#!/usr/bin/env python3
"""coolest-art-01: a synthwave sunset rendered pixel-by-pixel, stdlib only.

Composes a 640x640 PNG in memory and writes entry.png to $MAKEFUN_OUTPUT_DIR:
  * vertical sky gradient (deep violet -> magenta -> orange horizon)
  * faint deterministic stars in the upper sky
  * a striped yellow sun with horizontal slit cutouts
  * two dark mountain silhouettes flanking the sun
  * a neon cyan/magenta perspective grid + sun reflection below the horizon
"""
import os, zlib, struct, math

W = H = 640


def clamp01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def lerp(a, b, t):
    return a + (b - a) * t


def mix(ca, cb, t):
    return tuple(lerp(ca[i], cb[i], t) for i in range(3))


def sd_circle(px, py, cx, cy, r):
    return math.hypot(px - cx, py - cy) - r


def sd_tri_up(px, py, cx, cy, halfw, h):
    """Signed distance to an upward triangle (apex at top)."""
    p0 = (cx, cy - h)          # apex
    p1 = (cx - halfw, cy)      # base-left
    p2 = (cx + halfw, cy)      # base-right
    return sd_triangle(px, py, p0, p1, p2)


def sd_triangle(px, py, p0, p1, p2):
    """Signed distance to an arbitrary triangle."""
    ax, ay = p0
    bx, by = p1
    x2, y2 = p2
    e0 = (bx - ax, by - ay)
    e1 = (x2 - bx, y2 - by)
    e2 = (ax - x2, ay - y2)
    v0 = (px - ax, py - ay)
    v1 = (px - bx, py - by)
    v2 = (px - x2, py - y2)

    def _proj(v, e):
        den = e[0] * e[0] + e[1] * e[1]
        t = (v[0] * e[0] + v[1] * e[1]) / den
        t = max(0.0, min(1.0, t))
        return (v[0] - e[0] * t, v[1] - e[1] * t)

    s = 1.0 if (e0[0] * e2[1] - e0[1] * e2[0]) >= 0.0 else -1.0
    pq = [_proj(v0, e0), _proj(v1, e1), _proj(v2, e2)]
    cr = [v0[0] * e0[1] - v0[1] * e0[0],
          v1[0] * e1[1] - v1[1] * e1[0],
          v2[0] * e2[1] - v2[1] * e2[0]]
    d2 = [p[0] * p[0] + p[1] * p[1] for p in pq]
    d_x = min(d2)
    d_y = min(s * c for c in cr)
    return -math.sqrt(d_x) * (1.0 if d_y >= 0.0 else -1.0)


def smooth(e0, e1, v):
    t = clamp01((v - e0) / (e1 - e0))
    return t * t * (3 - 2 * t)


def cov(d):
    return 1.0 - smooth(-1.0, 1.0, d)


def glow(d, strength):
    # neon glow falloff: peaks at the line, gaussian-ish decay outward
    return strength * math.exp(-(d * d) / (2.0 * 2.2 * 2.2))


# palette
SKY_TOP = (0.08, 0.04, 0.16)
SKY_MID = (0.38, 0.10, 0.34)
SKY_HOR = (1.00, 0.36, 0.28)
SUN_CORE = (1.00, 0.95, 0.55)
SUN_MID = (1.00, 0.60, 0.30)
SUN_RIM = (1.00, 0.25, 0.45)
MOUNTAIN = (0.10, 0.05, 0.20)
GRID_DARK = (0.04, 0.02, 0.09)
GRID_CYAN = (0.00, 0.90, 0.90)
GRID_PINK = (1.00, 0.32, 0.72)

CX = W * 0.5
YH = 400.0          # horizon
SUN_R = 88.0
SUN_CY = YH - 40.0


def _stars():
    """Deterministic star positions across the upper sky."""
    out = []
    s = 12345
    for _ in range(120):
        s = (s * 1103515245 + 12345) & 0x7fffffff
        out.append(((s % W) / W, (s % 260) / 640.0))
    return out


def render():
    rows = []
    stars = _stars()

    for y in range(H):
        row = bytearray()
        fy = float(y)
        for x in range(W):
            fx = float(x)

            # ---- sky gradient ----
            t = clamp01(fy / YH)
            if t < 0.5:
                sky = mix(SKY_TOP, SKY_MID, t * 2.0)
            else:
                sky = mix(SKY_MID, SKY_HOR, (t - 0.5) * 2.0)
            c = sky

            # ---- stars (well above the horizon, subtle) ----
            if fy < YH - 60:
                for (sx, sy) in stars:
                    if abs(fx - sx * W) < 1.5 and abs(fy - sy * H) < 1.5:
                        c = mix(c, (0.85, 0.85, 0.95), 0.7)

            # ---- sun ----
            d = sd_circle(fx, fy, CX, SUN_CY, SUN_R)
            if d < SUN_R:
                n = clamp01(d / SUN_R)
                sc = mix(mix(SUN_CORE, SUN_MID, n * 1.6), SUN_RIM,
                         smooth(0.25, 1.0, n))
                a = cov(d)
                c = mix(c, sc, a)
                # horizontal slit cutouts
                l = (fy - SUN_CY)
                slit = (abs(l) % 16.0) / 16.0
                if 0.35 < slit < 0.62 and d < SUN_R - 1:
                    c = mix(c, sky, 0.9)

            # ---- mountains (silhouettes flanking the sun) ----
            dm1 = sd_tri_up(fx, fy, 90.0, YH, 130.0, 120.0)
            dm2 = sd_tri_up(fx, fy, 550.0, YH, 130.0, 130.0)
            if (dm1 < 0 or dm2 < 0) and fy < YH + 2:
                c = MOUNTAIN

            # ---- perspective grid (below horizon) ----
            dy = fy - YH
            if dy > 4:
                # horizontal lines: spacing in 1/dy space
                S = 260.0
                n = S / dy
                nlo = math.floor(n)
                nhi = math.ceil(n)
                d_h = min(abs(dy - S / nlo) if nlo > 0 else 1e9,
                          abs(dy - S / nhi))
                # radial lines: angular spacing
                tdrop = (fx - CX) / dy
                step = 0.16
                k = round(tdrop / step)
                d_r = abs(tdrop - k * step) * dy * 0.82

                # fade the dense grid out right at the horizon
                fade = smooth(10.0, 60.0, dy)
                c = GRID_DARK

                # glow lines
                g1 = glow(d_h, 1.0) * fade
                g2 = glow(d_r, 0.8) * fade
                c = (c[0] + GRID_CYAN[0] * g1 + GRID_PINK[0] * g2,
                     c[1] + GRID_CYAN[1] * g1 + GRID_PINK[1] * g2,
                     c[2] + GRID_CYAN[2] * g1 + GRID_PINK[2] * g2)

                # sun reflection streak
                rd = abs(fx - CX)
                ref = glow(rd, 0.70) * math.exp(-dy / 220.0)
                c = (c[0] + SUN_RIM[0] * ref,
                     c[1] + SUN_RIM[1] * ref,
                     c[2] + SUN_RIM[2] * ref)

            c = (clamp01(c[0]), clamp01(c[1]), clamp01(c[2]))
            row += bytes((int(c[0] * 255 + 0.5),
                          int(c[1] * 255 + 0.5),
                          int(c[2] * 255 + 0.5)))
        rows.append(bytes(row))
    return rows


def write_png(path, rows):
    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data
                + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))

    raw = b''.join(b'\x00' + r for r in rows)
    ihdr = struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0)
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
           + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))
    with open(path, 'wb') as f:
        f.write(png)


def main():
    outdir = os.environ.get('MAKEFUN_OUTPUT_DIR', '/output')
    os.makedirs(outdir, exist_ok=True)
    write_png(os.path.join(outdir, 'entry.png'), render())


if __name__ == '__main__':
    main()