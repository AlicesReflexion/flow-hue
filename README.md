# Hue for Flow Launcher

Control Philips Hue lights and scenes from [Flow Launcher](https://www.flowlauncher.com/).

| Type | What happens |
|---|---|
| `hue scene Precious` | Recalls the scene |
| `hue light floor lamp green` | Turns the light on and sets its colour |
| `hue light floor lamp warm white` | Colour temperature (candlelight, warm/soft/neutral/cool white, daylight) |
| `hue light floor lamp 70` | Brightness as a percentage (`0` turns the light off) |
| `hue light floor lamp coral 30` | Colour and brightness together, either order (`90 yellow`) |
| `hue light floor lamp off` | `on` / `off` |
| `hue refresh` | Reloads lights and scenes from the bridge now |
| `hue setup [ip]` | Pair again, optionally with a bridge at a given address |

Tab or Enter completes each step.

## First use

Type `hue`, press the link button on the bridge, then press Enter. The plugin finds the
bridge (mDNS, then Philips' discovery service), pairs, and loads your lights and scenes.

## How it works

- Pure standard-library Python; Flow starts `main.py` once per keystroke, so the query
  path only reads a local cache and never touches the network.
- Lights and scenes are cached and reloaded in the background once they are a day old.
- Bridge address, application key and cache live in
  `%APPDATA%\FlowLauncher\Settings\Plugins\Flow-hue\`.
- Bridge calls use HTTPS without certificate verification (the bridge's certificate is
  issued to its id, not its IP address); they stay on the local network.

## Development

```
python tools/make_icons.py    # regenerate Images/ after editing plugin/colors.py
python tests/test_offline.py  # parsing and colour checks, no bridge needed
```

If you change the action keyword in Flow's settings, also change `KEYWORD` in
`plugin/query.py`, otherwise completions insert the old keyword.
