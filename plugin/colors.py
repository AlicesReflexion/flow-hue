"""Colour names and their conversion to what the Hue API wants."""

# name -> sRGB
COLORS = [
    ("red", (255, 0, 0)),
    ("orange", (255, 120, 0)),
    ("amber", (255, 170, 0)),
    ("yellow", (255, 225, 0)),
    ("lime", (160, 255, 0)),
    ("green", (0, 255, 0)),
    ("mint", (90, 255, 170)),
    ("teal", (0, 200, 170)),
    ("turquoise", (0, 230, 210)),
    ("cyan", (0, 255, 255)),
    ("sky blue", (70, 170, 255)),
    ("blue", (0, 0, 255)),
    ("indigo", (75, 0, 255)),
    ("violet", (130, 60, 255)),
    ("purple", (160, 0, 255)),
    ("lavender", (190, 150, 255)),
    ("magenta", (255, 0, 255)),
    ("pink", (255, 90, 180)),
    ("hot pink", (255, 0, 130)),
    ("rose", (255, 60, 100)),
    ("coral", (255, 110, 80)),
    ("peach", (255, 180, 130)),
    ("gold", (255, 195, 60)),
]

# name -> (kelvin, sRGB used only for the swatch icon)
WHITES = [
    ("candlelight", (2000, (255, 147, 41))),
    ("warm white", (2700, (255, 180, 107))),
    ("soft white", (3000, (255, 196, 137))),
    ("neutral white", (4000, (255, 223, 190))),
    ("white", (4000, (255, 223, 190))),
    ("cool white", (5000, (255, 241, 224))),
    ("daylight", (6500, (235, 240, 255))),
]


def slug(name):
    return name.replace(" ", "_")


def rgb_to_xy(rgb):
    """sRGB -> CIE xy, using the wide-gamut D65 matrix Hue recommends."""
    r, g, b = (
        ((c / 255 + 0.055) / 1.055) ** 2.4 if c / 255 > 0.04045 else c / 255 / 12.92
        for c in rgb
    )
    x = r * 0.664511 + g * 0.154324 + b * 0.162028
    y = r * 0.283881 + g * 0.668433 + b * 0.047685
    z = r * 0.000088 + g * 0.072310 + b * 0.986039
    total = x + y + z
    return (x / total, y / total) if total else (0.3127, 0.3290)


def kelvin_to_xy(kelvin):
    """Planckian locus approximation (Kim et al.), valid 1667 K - 25000 K."""
    t = float(kelvin)
    if t <= 4000:
        x = -0.2661239e9 / t**3 - 0.2343589e6 / t**2 + 0.8776956e3 / t + 0.179910
    else:
        x = -3.0258469e9 / t**3 + 2.1070379e6 / t**2 + 0.2226347e3 / t + 0.240390
    if t <= 2222:
        y = -1.1063814 * x**3 - 1.34811020 * x**2 + 2.18555832 * x - 0.20219683
    elif t <= 4000:
        y = -0.9549476 * x**3 - 1.37418593 * x**2 + 2.09137015 * x - 0.16748867
    else:
        y = 3.0817580 * x**3 - 5.87338670 * x**2 + 3.75112997 * x - 0.37001483
    return x, y


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _closest_on_segment(p, a, b):
    ab = (b[0] - a[0], b[1] - a[1])
    length = ab[0] ** 2 + ab[1] ** 2
    t = ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / length if length else 0
    t = max(0.0, min(1.0, t))
    return (a[0] + t * ab[0], a[1] + t * ab[1])


def clamp_to_gamut(xy, gamut):
    """Move xy to the nearest point the light can show. gamut = [red, green, blue]."""
    if not gamut:
        return xy
    r, g, b = gamut
    signs = [_cross(r, g, xy), _cross(g, b, xy), _cross(b, r, xy)]
    if all(s >= 0 for s in signs) or all(s <= 0 for s in signs):
        return xy
    candidates = [_closest_on_segment(xy, *edge) for edge in ((r, g), (g, b), (b, r))]
    return min(candidates, key=lambda c: (c[0] - xy[0]) ** 2 + (c[1] - xy[1]) ** 2)


def _xy_body(xy, gamut):
    x, y = clamp_to_gamut(xy, gamut)
    return {"on": {"on": True}, "color": {"xy": {"x": round(x, 4), "y": round(y, 4)}}}


def options(light):
    """What can be said to this light: [(name, icon, PUT body)], in display order."""
    out = []
    gamut = light.get("gamut")
    if light.get("color"):
        for name, rgb in COLORS:
            out.append((name, "c_" + slug(name), _xy_body(rgb_to_xy(rgb), gamut)))
    if light.get("ct"):
        low, high = light.get("mirek") or (153, 500)
        for name, (kelvin, _) in WHITES:
            mirek = max(low, min(high, round(1e6 / kelvin)))
            body = {"on": {"on": True}, "color_temperature": {"mirek": mirek}}
            out.append((name, "c_" + slug(name), body))
    elif light.get("color"):
        for name, (kelvin, _) in WHITES:
            out.append((name, "c_" + slug(name), _xy_body(kelvin_to_xy(kelvin), gamut)))
    out.append(("on", "on", {"on": {"on": True}}))
    out.append(("off", "off", {"on": {"on": False}}))
    return out
