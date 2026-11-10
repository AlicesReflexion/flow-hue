"""Config and cache files, kept outside the plugin folder so updates keep them."""
import json
import os
import time

DATA_DIR = os.environ.get("FLOW_HUE_DATA_DIR") or os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"),
    "FlowLauncher", "Settings", "Plugins", "Flow-hue",
)
CONFIG = os.path.join(DATA_DIR, "config.json")   # ip, bridge_id, key
CACHE = os.path.join(DATA_DIR, "cache.json")     # lights, scenes, fetched_at
REFRESH_MARK = os.path.join(DATA_DIR, "refresh.mark")

MAX_AGE = 24 * 60 * 60      # refresh the cache once a day
RETRY_AFTER = 10 * 60       # don't relaunch a failed refresh more often than this


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _save(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def load_config():
    config = _load(CONFIG)
    return config if config and config.get("key") and config.get("ip") else None


def save_config(config):
    _save(CONFIG, config)


def load_cache():
    return _load(CACHE) or {"lights": [], "scenes": [], "fetched_at": 0}


def save_cache(lights, scenes):
    _save(CACHE, {"fetched_at": time.time(), "lights": lights, "scenes": scenes})


def refresh_due(cache):
    """True when the cache is over a day old and no refresh was started recently."""
    now = time.time()
    if now - cache.get("fetched_at", 0) < MAX_AGE:
        return False
    try:
        return now - os.path.getmtime(REFRESH_MARK) > RETRY_AFTER
    except OSError:
        return True


def mark_refresh():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(REFRESH_MARK, "w"):
        pass
