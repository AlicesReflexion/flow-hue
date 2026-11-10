"""Talking to the Hue bridge: discovery, pairing and the v2 (CLIP) API."""
import json
import socket
import ssl
import struct
import time
import urllib.error
import urllib.request

TIMEOUT = 3

# The bridge's certificate is issued to its bridge id, not its IP address, so it
# can't be verified the normal way. These calls never leave the local network.
_LOCAL_TLS = ssl.create_default_context()
_LOCAL_TLS.check_hostname = False
_LOCAL_TLS.verify_mode = ssl.CERT_NONE


class BridgeError(Exception):
    pass


class Unreachable(BridgeError):
    pass


def _http(method, url, body=None, key=None, context=None, timeout=TIMEOUT):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if key:
        request.add_header("hue-application-key", key)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            errors = json.loads(error.read().decode("utf-8")).get("errors") or []
            detail = errors[0].get("description", "") if errors else ""
        except Exception:
            pass
        if error.code in (401, 403):
            raise BridgeError("the bridge rejected the application key - run '%s'" % "hue setup")
        raise BridgeError(detail or "bridge returned HTTP %d" % error.code)
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise Unreachable("can't reach the Hue bridge (%s)" % getattr(error, "reason", error))


def _bridge(ip, method, path, body=None, key=None):
    return _http(method, "https://%s%s" % (ip, path), body, key, _LOCAL_TLS)


# ---------------------------------------------------------------- discovery

def _local_addresses():
    try:
        return socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        return []


def _mdns(wait=1.5):
    """Ask for _hue._tcp.local over multicast DNS; return the IPs that answer."""
    name = b"".join(bytes([len(p)]) + p for p in (b"_hue", b"_tcp", b"local")) + b"\0"
    # id 0, standard query, 1 question; type PTR, class IN with unicast-response bit
    packet = struct.pack("!6H", 0, 0, 1, 0, 0, 0) + name + struct.pack("!2H", 12, 0x8001)
    sockets = []
    for address in _local_addresses() or [""]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setblocking(False)
            s.bind((address, 0))
            if address:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(address))
            s.sendto(packet, ("224.0.0.251", 5353))
            sockets.append(s)
        except OSError:
            pass
    found = []
    deadline = time.time() + wait
    while sockets and time.time() < deadline and not found:
        for s in sockets:
            try:
                data, (ip, _) = s.recvfrom(4096)
            except OSError:
                continue
            if b"_hue" in data and ip not in found:
                found.append(ip)
        time.sleep(0.05)
    for s in sockets:
        s.close()
    return found


def _cloud():
    """Philips' discovery service: bridges seen from this public IP."""
    try:
        entries = _http("GET", "https://discovery.meethue.com/", timeout=5)
    except BridgeError:
        return []
    return [e["internalipaddress"] for e in entries if e.get("internalipaddress")]


def bridge_id(ip):
    """The bridge's id, or None if nothing Hue-like answers at this address."""
    try:
        config = _bridge(ip, "GET", "/api/0/config")
    except BridgeError:
        return None
    return (config.get("bridgeid") or "").lower() or None


def discover():
    """Find bridges on the network: [(ip, bridge_id)]."""
    for search in (_mdns, _cloud):
        found = [(ip, bridge_id(ip)) for ip in search()]
        found = [(ip, bid) for ip, bid in found if bid]
        if found:
            return found
    return []


# ------------------------------------------------------------------ pairing

def request_key(ip):
    """Ask for an application key. None until the link button has been pressed."""
    body = {"devicetype": "flow_hue#%s" % socket.gethostname()[:19], "generatekey": True}
    reply = _bridge(ip, "POST", "/api", body)
    entry = reply[0] if isinstance(reply, list) and reply else {}
    if "success" in entry:
        return entry["success"]["username"]
    error = entry.get("error", {})
    if error.get("type") == 101:
        return None
    raise BridgeError(error.get("description") or "unexpected reply from the bridge")


# --------------------------------------------------------------------- data

def fetch(ip, key):
    """Lights and scenes, reduced to what the plugin needs."""
    lights = []
    for item in _bridge(ip, "GET", "/clip/v2/resource/light", key=key).get("data", []):
        color = item.get("color")
        ct = item.get("color_temperature")
        gamut = (color or {}).get("gamut")
        schema = (ct or {}).get("mirek_schema") or {}
        lights.append({
            "id": item["id"],
            "name": (item.get("metadata") or {}).get("name", "Light"),
            "color": color is not None,
            "gamut": [[gamut[c]["x"], gamut[c]["y"]] for c in ("red", "green", "blue")]
                     if gamut else None,
            "ct": ct is not None,
            "mirek": [schema.get("mirek_minimum", 153), schema.get("mirek_maximum", 500)],
        })
    scenes = [
        {"id": item["id"], "name": (item.get("metadata") or {}).get("name", "Scene")}
        for item in _bridge(ip, "GET", "/clip/v2/resource/scene", key=key).get("data", [])
    ]
    lights.sort(key=lambda l: l["name"].lower())
    scenes.sort(key=lambda s: s["name"].lower())
    return lights, scenes


def set_light(ip, key, light_id, body):
    _bridge(ip, "PUT", "/clip/v2/resource/light/%s" % light_id, body, key)


def recall_scene(ip, key, scene_id):
    _bridge(ip, "PUT", "/clip/v2/resource/scene/%s" % scene_id,
            {"recall": {"action": "active"}}, key)
