"""Offline checks: query parsing and colour maths against a fixture cache.

Run:  python tests/test_offline.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = tempfile.mkdtemp(prefix="flow-hue-test-")
os.environ["FLOW_HUE_DATA_DIR"] = DATA
sys.path.insert(0, ROOT)

from plugin import colors, query, store  # noqa: E402

GAMUT_C = [[0.6915, 0.3083], [0.17, 0.7], [0.1532, 0.0475]]
LIGHTS = [
    {"id": "L1", "name": "Floor lamp", "color": True, "gamut": GAMUT_C, "ct": True, "mirek": [153, 500], "dim": True},
    {"id": "L2", "name": "Lamp", "color": False, "gamut": None, "ct": True, "mirek": [153, 454], "dim": True},
    {"id": "L3", "name": "Lamp 2", "color": False, "gamut": None, "ct": False, "mirek": [153, 500], "dim": False},
]
SCENES = [{"id": "S1", "name": "Precious"}, {"id": "S2", "name": "Savanna sunset"}]


def titles(text):
    return [r["Title"] for r in sorted(query.results(text), key=lambda r: -r["Score"])]


def first(text):
    return max(query.results(text), key=lambda r: r["Score"])


# --- not paired yet
assert first("")["JsonRPCAction"]["method"] == "setup"
assert first("setup 192.168.1.5")["JsonRPCAction"]["parameters"] == ["192.168.1.5"]

store.save_config({"ip": "192.0.2.1", "bridge_id": "abc", "key": "k"})
store.save_cache(LIGHTS, SCENES)

# --- sub-commands
assert titles("") == ["scene", "light", "refresh"]
assert titles("li") == ["light"]
assert first("li")["AutoCompleteText"] == "hue light "
assert first("li")["JsonRPCAction"]["method"] == "Flow.Launcher.ChangeQuery"

# --- scenes
assert titles("scene") == ["Precious", "Savanna sunset"]
assert titles("scene sun") == ["Savanna sunset"]
r = first("scene prec")
assert r["JsonRPCAction"] == {"method": "scene", "parameters": ["S1", "Precious"]}
assert r["AutoCompleteText"] == "hue scene Precious"
assert titles("scene zzz") == ["No scene matching 'zzz'"]

# --- choosing a light
assert titles("light") == ["Floor lamp", "Lamp", "Lamp 2"]
assert titles("light fl") == ["Floor lamp"]
assert first("light fl")["AutoCompleteText"] == "hue light Floor lamp "
assert titles("light la") == ["Lamp", "Lamp 2", "Floor lamp"]

# --- choosing a colour
r = first("light floor lamp green")
assert r["Title"] == "green" and r["IcoPath"] == "Images/c_green.png"
method, (light_id, body, _) = r["JsonRPCAction"]["method"], r["JsonRPCAction"]["parameters"]
assert (method, light_id) == ("light", "L1")
body = json.loads(body)
assert body["on"] == {"on": True}
assert body["color"]["xy"] == {"x": 0.17, "y": 0.7}, body   # clamped to the green corner

assert titles("light Floor  Lamp WARM") == ["warm white"]
body = json.loads(first("light floor lamp warm white")["JsonRPCAction"]["parameters"][1])
assert body["color_temperature"] == {"mirek": 370}
assert json.loads(first("light floor lamp off")["JsonRPCAction"]["parameters"][1]) == {"on": {"on": False}}

# white-only light: no colours offered, mirek clamped to its range
lamp = titles("light lamp")
assert "red" not in lamp and "warm white" in lamp and "Lamp 2" in lamp, lamp
body = json.loads(first("light lamp candle")["JsonRPCAction"]["parameters"][1])
assert body["color_temperature"] == {"mirek": 454}
# longest name wins; an on/off-only light offers just that
assert titles("light lamp 2") == ["on", "off"]
assert titles("light lamp 2 o") == ["on", "off"]
assert titles("light floor lamp zzz") == ["No colour called 'zzz'"]

# --- brightness
r = first("light floor lamp 70")
assert r["Title"] == "70%" and r["AutoCompleteText"] == "hue light Floor lamp 70"
assert json.loads(r["JsonRPCAction"]["parameters"][1]) == {"on": {"on": True}, "dimming": {"brightness": 70}}
assert titles("light floor lamp 70") == ["70%"]
assert titles("light floor lamp 5 %") == ["5%"]
assert json.loads(first("light floor lamp 0")["JsonRPCAction"]["parameters"][1]) == {"on": {"on": False}}
assert first("light floor lamp 150")["Title"] == "Brightness goes up to 100%"
assert "JsonRPCAction" in first("light floor lamp 150")  # completes, doesn't send
assert first("light lamp 2 50")["Title"] == "Lamp 2 can't be dimmed"
# caches written before "dim" existed still dim colour/white bulbs
legacy = dict(LIGHTS[0]); legacy.pop("dim")
assert query._percent_problem(legacy, 40, False) is None

# --- colour and brightness together, either order
def params(text):
    return json.loads(first(text)["JsonRPCAction"]["parameters"][1])

r = first("light floor lamp coral 30")
assert r["Title"] == "coral 30%" and r["AutoCompleteText"] == "hue light Floor lamp coral 30"
assert r["SubTitle"] == "Set Floor lamp to coral at 30% brightness"
assert params("light floor lamp coral 30")["dimming"] == {"brightness": 30}
assert params("light floor lamp coral 30")["color"] == params("light floor lamp coral")["color"]
assert params("light floor lamp 90 yellow") == dict(params("light floor lamp yellow"), dimming={"brightness": 90})
assert titles("light floor lamp 90 yel") == ["yellow 90%"]
assert params("light floor lamp warm white 40%") == {
    "on": {"on": True}, "color_temperature": {"mirek": 370}, "dimming": {"brightness": 40}}
assert params("light floor lamp 40 warm white")["dimming"] == {"brightness": 40}
assert "off 50%" not in titles("light floor lamp 50 o") and "on 50%" in titles("light floor lamp 50 o")
assert params("light floor lamp on 50") == {"on": {"on": True}, "dimming": {"brightness": 50}}
assert first("light floor lamp coral 0")["Title"] == "0% would turn Floor lamp off"
assert first("light floor lamp coral 101")["Title"] == "Brightness goes up to 100%"
assert first("light lamp 2 on 50")["Title"] == "Lamp 2 can't be dimmed"
assert titles("light floor lamp zzz 30") == ["No colour called 'zzz'"]

# --- colour maths
x, y = colors.rgb_to_xy((255, 255, 255))
assert abs(x - 0.3227) < 0.01 and abs(y - 0.329) < 0.01, (x, y)
inside = (0.4, 0.4)
assert colors.clamp_to_gamut(inside, GAMUT_C) == inside
x, y = colors.kelvin_to_xy(2700)
assert abs(x - 0.4599) < 0.005 and abs(y - 0.4106) < 0.005, (x, y)

# --- every colour has an icon
for name, icon, _ in colors.options(LIGHTS[0]):
    assert os.path.exists(os.path.join(ROOT, "Images", icon + ".png")), icon

# --- end to end through main.py, as Flow calls it
start = time.perf_counter()
out = subprocess.run(
    [sys.executable, os.path.join(ROOT, "main.py"),
     json.dumps({"method": "query", "parameters": ["light floor lamp gr"]})],
    capture_output=True, text=True, check=True).stdout
elapsed = (time.perf_counter() - start) * 1000
assert [r["Title"] for r in json.loads(out)["result"]] == ["green"], out

# --- a stale cache triggers one background refresh and still answers at once
store.save_cache(LIGHTS, SCENES)
cache = store.load_cache()
cache["fetched_at"] = time.time() - 25 * 3600
store._save(store.CACHE, cache)
assert store.refresh_due(store.load_cache())
assert titles("scene") == ["Precious", "Savanna sunset"]
assert os.path.exists(store.REFRESH_MARK)
assert not store.refresh_due(store.load_cache())   # not relaunched on the next keystroke

print("all offline checks passed (query via main.py: %.0f ms)" % elapsed)
