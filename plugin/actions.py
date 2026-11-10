"""What happens when a result is chosen. Each returns None or a Flow API call
as a tuple, e.g. ("ShowMsg", title, subtitle, icon)."""
import json
import time

from . import bridge, store
from .query import KEYWORD

PAIR_WAIT = 20  # seconds to keep asking while the link button gets pressed


def _msg(title, subtitle=""):
    return ("ShowMsg", title, subtitle, "")


def _config():
    config = store.load_config()
    if config is None:
        raise bridge.BridgeError("not set up yet - type '%s'" % KEYWORD)
    return config


def _relocate(config):
    """The bridge may have a new IP address; find it again by its id."""
    for ip, bid in bridge.discover():
        if bid == config.get("bridge_id"):
            config["ip"] = ip
            store.save_config(config)
            return True
    return False


def _call(fn, *args):
    """Run fn(ip, key, *args), re-finding the bridge once if it has moved."""
    config = _config()
    try:
        return fn(config["ip"], config["key"], *args)
    except bridge.Unreachable:
        if not _relocate(config):
            raise
        return fn(config["ip"], config["key"], *args)


def setup(ip=""):
    if ip:
        bid = bridge.bridge_id(ip)
        if not bid:
            return _msg("Hue: no bridge at " + ip)
    else:
        found = bridge.discover()
        if not found:
            return _msg("Hue: no bridge found",
                        "Type '%s setup <bridge ip>' to enter its address" % KEYWORD)
        ip, bid = found[0]

    deadline = time.time() + PAIR_WAIT
    key = bridge.request_key(ip)
    while key is None and time.time() < deadline:
        time.sleep(1)
        key = bridge.request_key(ip)
    if key is None:
        return _msg("Hue: link button not pressed",
                    "Press the button on the bridge, then try again")

    store.save_config({"ip": ip, "bridge_id": bid, "key": key})
    lights, scenes = bridge.fetch(ip, key)
    store.save_cache(lights, scenes)
    return ("ChangeQuery", KEYWORD + " ", True)


def refresh():
    lights, scenes = _call(bridge.fetch)
    store.save_cache(lights, scenes)
    return lights, scenes


def refresh_now():
    lights, scenes = refresh()
    return _msg("Hue: %d lights, %d scenes" % (len(lights), len(scenes)))


def scene(scene_id, name=""):
    _call(bridge.recall_scene, scene_id)


def light(light_id, body, description=""):
    _call(bridge.set_light, light_id, json.loads(body))
