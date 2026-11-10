"""Generate Images/*.png: the plugin icon and one swatch per colour name.

Run after changing the colour table:  python tools/make_icons.py
"""
import colorsys
import math
import os
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from plugin import colors  # noqa: E402

SIZE = 64
OUT = os.path.join(ROOT, "Images")


def write_png(path, pixel):
    """pixel(x, y) -> (r, g, b, a) with 0-255 ints."""
    rows = b"".join(
        b"\0" + bytes(c for x in range(SIZE) for c in pixel(x, y)) for y in range(SIZE)
    )

    def chunk(kind, data):
        body = kind + data
        return struct.pack("!I", len(data)) + body + struct.pack("!I", zlib.crc32(body))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack("!2I5B", SIZE, SIZE, 8, 6, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(rows, 9)))
        f.write(chunk(b"IEND", b""))


def _polar(x, y):
    dx, dy = x + 0.5 - SIZE / 2, y + 0.5 - SIZE / 2
    return math.hypot(dx, dy), math.atan2(dy, dx)


def _coverage(distance, radius):
    return max(0.0, min(1.0, radius - distance + 0.5))  # 1px anti-aliased edge


def disc(rgb, ring=None):
    """Filled circle, with a thin darker rim so pale colours show on light themes."""
    rim = ring or tuple(int(c * 0.72) for c in rgb)

    def pixel(x, y):
        d, _ = _polar(x, y)
        inner = _coverage(d, 25)
        color = tuple(int(rim[i] + (rgb[i] - rim[i]) * inner) for i in range(3))
        return color + (int(255 * _coverage(d, 27)),)
    return pixel


def ring(rgb):
    def pixel(x, y):
        d, _ = _polar(x, y)
        return rgb + (int(255 * _coverage(d, 27) * (1 - _coverage(d, 22))),)
    return pixel


def wheel(x, y):
    d, angle = _polar(x, y)
    r, g, b = colorsys.hsv_to_rgb((angle / (2 * math.pi)) % 1, min(1.0, d / 27) * 0.9, 1)
    return int(r * 255), int(g * 255), int(b * 255), int(255 * _coverage(d, 27))


def main():
    os.makedirs(OUT, exist_ok=True)
    write_png(os.path.join(OUT, "hue.png"), wheel)
    write_png(os.path.join(OUT, "light.png"), disc((255, 214, 120)))
    write_png(os.path.join(OUT, "on.png"), disc((255, 236, 170)))
    write_png(os.path.join(OUT, "off.png"), ring((120, 120, 120)))
    for name, rgb in colors.COLORS:
        write_png(os.path.join(OUT, "c_%s.png" % colors.slug(name)), disc(rgb))
    for name, (_, rgb) in colors.WHITES:
        write_png(os.path.join(OUT, "c_%s.png" % colors.slug(name)), disc(rgb))
    print("wrote %d icons to %s" % (len(os.listdir(OUT)), OUT))


if __name__ == "__main__":
    main()
