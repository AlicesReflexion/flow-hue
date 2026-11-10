"""Flow Launcher entry point (JSON-RPC v1: one process per request).

Flow runs `python main.py '{"method": ..., "parameters": [...]}'`.
Queries answer with {"result": [...]}; actions may print one Flow API call.
Network modules are only imported inside actions so queries stay fast.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def api(method, *params):
    """Ask Flow Launcher to run one of its own API methods."""
    print(json.dumps({"method": "Flow.Launcher." + method, "parameters": list(params)}))


def toast(title, subtitle=""):
    api("ShowMsg", title, subtitle, "")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--refresh":
        from plugin import actions
        try:
            actions.refresh()
        except Exception:
            pass
        return

    try:
        request = json.loads(sys.argv[1])
    except (IndexError, ValueError):
        request = {"method": "query", "parameters": [""]}
    method = request.get("method", "query")
    params = request.get("parameters") or []

    if method == "query":
        from plugin import query
        print(json.dumps({"result": query.results(params[0] if params else "")}))
        return

    from plugin import actions
    handler = {
        "setup": actions.setup,
        "scene": actions.scene,
        "light": actions.light,
        "refresh": actions.refresh_now,
    }.get(method)
    if handler is None:
        return
    try:
        outcome = handler(*params)
    except Exception as exc:
        toast("Hue: " + (str(exc) or type(exc).__name__))
        return
    if outcome:
        api(*outcome)


if __name__ == "__main__":
    main()
