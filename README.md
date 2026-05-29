# Ukraine Drone Map

Live desktop app that monitors Ukrainian Telegram air-defense channels and plots drone/missile reports on an animated map.

## Features

- **Live Telegram monitoring** — `kpszsu`, `war_monitor`, `mon1tor_ua`
- **Full message analysis** — extracts threat type, location(s), direction, count, status
- **Animated trajectories** — ant-path animation showing reported flight paths
- **Moving markers** — icons animate along multi-waypoint routes
- **45-minute auto-expiry** — threats fade off the map automatically
- **Filter bar** — filter by drones / missiles / moving / destroyed
- **Dark military UI** with real-time sidebar feed
- **Demo mode** — works without Telegram credentials for testing

## Quick Start

### Demo mode (no Telegram needed)
```bash
pip install -r requirements.txt
python main.py --demo
```

### With real Telegram data

1. Get your free API key at https://my.telegram.org/apps
2. Run setup:
   ```bash
   python main.py --setup
   ```
3. Launch:
   ```bash
   python main.py
   ```

### Open in browser instead of desktop window
```bash
python main.py --demo --browser
```

## Options

| Flag | Description |
|------|-------------|
| `--demo` | Inject synthetic events — no Telegram needed |
| `--setup` | Re-run first-time config wizard |
| `--browser` | Open in system browser instead of pywebview window |
| `--port N` | Override server port (default 8765) |

## Requirements

- Python 3.10+
- See `requirements.txt`

On Linux you may need: `sudo apt install python3-gi gir1.2-webkit2-4.0` for pywebview.

## Channels monitored

| Channel | Description |
|---------|-------------|
| `@kpszsu` | Air Force of Ukraine official |
| `@war_monitor` | War Monitor aggregator |
| `@mon1tor_ua` | Monitor UA |

## Architecture

```
main.py             ← entry point, starts all threads
server.py           ← FastAPI + WebSocket hub
telegram_monitor.py ← Telethon channel listener
message_parser.py   ← regex + NLP threat extraction
locations_db.py     ← ~200 Ukrainian locations with coordinates
web/
  index.html        ← Leaflet map UI
  app.js            ← WebSocket client + animation engine
  style.css         ← dark military theme
```
