"""Turn what the user has typed into Flow Launcher results.

Runs on every keystroke: reads only the local cache, never the network.
"""
import json
import re

from . import colors, store

KEYWORD = "hue"  # must match ActionKeyword in plugin.json
ICON = "Images/hue.png"


def _norm(text):
    return " ".join(text.lower().split())


def _match(needle, name):
    """Rank how well `needle` matches `name`; None when it doesn't."""
    n = _norm(name)
    if not needle:
        return 50
    if n.startswith(needle):
        return 100
    if any(word.startswith(needle) for word in n.split()):
        return 80
    if needle in n:
        return 60
    if all(token in n for token in needle.split()):
        return 40
    return None


def _result(title, subtitle, icon, score, complete, action=None):
    """A result row. Without `action`, Enter just completes the query like Tab."""
    complete = "%s %s" % (KEYWORD, complete)
    if action is None:
        action = {
            "method": "Flow.Launcher.ChangeQuery",
            "parameters": [complete, True],
            "dontHideAfterAction": True,
        }
    return {
        "Title": title,
        "SubTitle": subtitle,
        "IcoPath": icon,
        "Score": score,
        "AutoCompleteText": complete,
        "JsonRPCAction": action,
    }


def _ranked(needle, items, name_of):
    """Yield (score, item) for items matching needle, keeping cache order on ties."""
    for index, item in enumerate(items):
        base = _match(needle, name_of(item))
        if base is not None:
            yield base * 100 - index, item


def _setup(rest):
    ip = rest.split()[0] if rest.split() else ""
    return [_result(
        "Press the link button on your Hue bridge, then press Enter",
        ("Pair with the bridge at %s" % ip) if ip
        else "Finds the bridge on your network and pairs with it. "
             "Not found? Type: %s setup <bridge ip>" % KEYWORD,
        ICON, 100, ("setup " + ip).strip(),
        {"method": "setup", "parameters": [ip], "dontHideAfterAction": True},
    )]


def _commands(needle):
    rows = [
        ("scene", "Recall a scene", ICON, "scene "),
        ("light", "Set the colour of a light", "Images/light.png", "light "),
        ("refresh", "Reload lights and scenes from the bridge", ICON, "refresh"),
    ]
    out = []
    for score, (name, subtitle, icon, complete) in _ranked(needle, rows, lambda r: r[0]):
        action = None
        if name == "refresh":
            action = {"method": "refresh", "parameters": []}
        out.append(_result(name, subtitle, icon, score, complete, action))
    return out


def _scenes(needle, cache):
    out = []
    for score, scene in _ranked(needle, cache["scenes"], lambda s: s["name"]):
        out.append(_result(
            scene["name"], "Recall scene", ICON, score, "scene " + scene["name"],
            {"method": "scene", "parameters": [scene["id"], scene["name"]]},
        ))
    return out or [_empty("scene", needle)]


def _dimmable(light):
    # Caches written before "dim" was recorded: colour and white bulbs all dim.
    return light.get("dim", light.get("color") or light.get("ct"))


_PERCENT = r"(\d{1,3})\s*%?"


def _split_percent(needle):
    """'coral 30', '30 coral' or '30' -> (colour text, percent); percent is None if absent."""
    for pattern, colour, percent in (
        (_PERCENT, None, 1),
        (r"(.+?)\s+" + _PERCENT, 1, 2),
        (_PERCENT + r"\s+(.+)", 2, 1),
    ):
        match = re.fullmatch(pattern, needle)
        if match:
            return (match.group(colour) if colour else ""), int(match.group(percent))
    return needle, None


def _percent_problem(light, percent, with_colour):
    """A result explaining why this brightness can't be used, or None if it can."""
    name = light["name"]
    if not _dimmable(light):
        title, subtitle = "%s can't be dimmed" % name, "It can only be turned on or off"
    elif percent > 100:
        title, subtitle = "Brightness goes up to 100%", "Type a number from 0 to 100"
    elif percent == 0 and with_colour:
        title, subtitle = "0%% would turn %s off" % name, "Use 1 to 100 with a colour, or type off"
    else:
        return None
    return _result(title, subtitle, ICON, 0, "light %s " % name)


def _brightness_only(light, percent):
    name = light["name"]
    if percent == 0:
        body, subtitle = {"on": {"on": False}}, "Turn %s off" % name
    else:
        body = {"on": {"on": True}, "dimming": {"brightness": percent}}
        subtitle = "Set %s to %d%% brightness" % (name, percent)
    return _result(
        "%d%%" % percent, subtitle, "Images/light.png", 10000,
        "light %s %d" % (name, percent),
        {"method": "light", "parameters": [light["id"], json.dumps(body), subtitle]},
    )


def _light_rows(needle, lights, penalty=0):
    return [
        _result(light["name"],
                "Choose a colour, or type a brightness %" if _dimmable(light)
                else "Turn on or off", "Images/light.png",
                score - penalty, "light %s " % light["name"])
        for score, light in _ranked(needle, lights, lambda l: l["name"])
    ]


def _lights(rest, cache):
    lights = cache["lights"]
    # The light is the longest light name the text starts with; the rest is the colour.
    chosen = None
    for light in lights:
        name = _norm(light["name"])
        if (rest == name or rest.startswith(name + " ")) and (
                chosen is None or len(name) > len(_norm(chosen["name"]))):
            chosen = light
    if chosen is None:
        return _light_rows(rest, lights) or [_empty("light", rest)]

    needle = rest[len(_norm(chosen["name"])):].strip()
    colour, percent = _split_percent(needle)
    if percent is not None:
        problem = _percent_problem(chosen, percent, bool(colour))
        if problem:
            return [problem]
        if not colour:
            return [_brightness_only(chosen, percent)]
    name_ = chosen["name"]
    out = []
    for score, (name, icon, body) in _ranked(colour, colors.options(chosen), lambda o: o[0]):
        if percent is None:
            title, complete = name, "light %s %s" % (name_, name)
            if name in ("on", "off"):
                subtitle = "Turn %s %s" % (name_, name)
            else:
                subtitle = "Set %s to %s" % (name_, name)
        else:
            if name == "off":
                continue
            body = dict(body, on={"on": True}, dimming={"brightness": percent})
            title = "%s %d%%" % (name, percent)
            complete = "light %s %s %d" % (name_, name, percent)
            if name == "on":
                subtitle = "Turn %s on at %d%% brightness" % (name_, percent)
            else:
                subtitle = "Set %s to %s at %d%% brightness" % (name_, name, percent)
        out.append(_result(
            title, subtitle, "Images/%s.png" % icon, score, complete,
            {"method": "light", "parameters": [chosen["id"], json.dumps(body), subtitle]},
        ))
    if not needle:
        # "lamp" may be a whole name and also the start of "Lamp 2": offer those too.
        others = [l for l in lights if l is not chosen]
        out += _light_rows(rest, others, penalty=20000)
    return out or [_result(
        "No colour called '%s'" % colour, "Try red, warm white, off, or a brightness like 70",
        ICON, 0, "light %s " % chosen["name"])]


def _empty(kind, needle):
    if needle:
        return _result("No %s matching '%s'" % (kind, needle), "",
                       ICON, 0, kind + " ")
    return _result("No %ss cached" % kind, "Press Enter to reload from the bridge",
                   ICON, 0, "refresh", {"method": "refresh", "parameters": []})


def _refresh_in_background():
    import os
    import subprocess
    import sys
    store.mark_refresh()
    main = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        [sys.executable, main, "--refresh"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=flags, close_fds=True,
    )


def results(raw):
    text = _norm(raw)
    command, _, rest = text.partition(" ")

    if store.load_config() is None or command == "setup":
        return _setup(rest if command == "setup" else "")

    cache = store.load_cache()
    if store.refresh_due(cache):
        try:
            _refresh_in_background()
        except Exception:
            pass

    if command == "scene":
        return _scenes(rest, cache)
    if command == "light":
        return _lights(rest, cache)
    return _commands(text)
