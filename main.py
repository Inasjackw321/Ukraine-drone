"""
Entry point for the Ukraine Drone Map desktop app.

Usage:
    python main.py                    # normal start
    python main.py --setup            # re-run first-time setup
    python main.py --browser          # open in system browser instead of desktop window
    python main.py --demo             # inject demo events (no Telegram needed)
"""

import argparse
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

import uvicorn

CONFIG_PATH = Path(__file__).parent / "config.json"
EXAMPLE_PATH = Path(__file__).parent / "config.example.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")


# ── Config helpers ────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    log.info("Config saved to %s", CONFIG_PATH)


def run_setup() -> dict:
    print("\n" + "═" * 60)
    print("  Ukraine Drone Map — First-time Setup")
    print("═" * 60)
    print("\nYou need a Telegram API key from https://my.telegram.org/apps")
    print("(free, takes ~2 minutes)\n")

    cfg = {}
    api_id = input("  Telegram API ID (integer): ").strip()
    api_hash = input("  Telegram API Hash: ").strip()
    phone = input("  Your phone number (e.g. +380XXXXXXXXX): ").strip()

    cfg["telegram"] = {
        "api_id": int(api_id),
        "api_hash": api_hash,
        "phone": phone,
    }
    cfg["channels"] = ["kpszsu", "war_monitor", "mon1tor_ua"]
    cfg["server"] = {"host": "127.0.0.1", "port": 8765}
    cfg["map"] = {"threat_expire_minutes": 45, "max_threats": 200}

    save_config(cfg)
    print("\nSetup complete!\n")
    return cfg


# ── Demo mode: inject synthetic events ────────────────────────────────────────

def run_demo_injector():
    """Inject demo threat events so the map works without real Telegram creds."""
    import random
    import uuid
    from datetime import datetime, timezone
    import server

    demo_events = [
        {
            "threat_type": "shahed",
            "threat_category": "drone",
            "status": "moving",
            "count": 3,
            "lat": 49.9935, "lon": 36.2304,
            "location_name": "Харків",
            "waypoints": [
                {"lat": 51.0, "lon": 37.5, "name": "Бєлгород (RU)"},
                {"lat": 50.5, "lon": 36.8, "name": "Куп'янськ"},
                {"lat": 49.9935, "lon": 36.2304, "name": "Харків"},
            ],
            "directions": {"from": "Росія", "to": "Харків"},
            "channel": "War Monitor",
            "text": "🚨 3 Шахеди зафіксовані в Харківській області. Рухаються з боку Росії у напрямку Харкова.",
        },
        {
            "threat_type": "kalibr",
            "threat_category": "missile",
            "status": "moving",
            "count": 1,
            "lat": 47.0, "lon": 34.5,
            "location_name": "Запорізька",
            "waypoints": [
                {"lat": 45.5, "lon": 33.0, "name": "Крим"},
                {"lat": 46.6, "lon": 33.8, "name": "Херсон"},
                {"lat": 47.0, "lon": 34.5, "name": "Запоріжжя"},
            ],
            "directions": {"from": "Крим", "to": "Запоріжжя"},
            "channel": "КПСЗСУ",
            "text": "⚠️ Ракетна небезпека! Калібр зафіксований над Херсонщиною, рухається у напрямку Запоріжжя.",
        },
        {
            "threat_type": "drone",
            "threat_category": "drone",
            "status": "alert",
            "count": 5,
            "lat": 50.4501, "lon": 30.5234,
            "location_name": "Київ",
            "waypoints": [
                {"lat": 51.5, "lon": 31.0, "name": "Чернігів"},
                {"lat": 51.0, "lon": 30.8, "name": "Чернігівська"},
                {"lat": 50.4501, "lon": 30.5234, "name": "Київ"},
            ],
            "directions": {"from": "Білорусь", "to": "Київ"},
            "channel": "Monitor UA",
            "text": "❗️ Повітряна тривога в Київській, Чернігівській областях. Рухається 5 БПЛА.",
        },
        {
            "threat_type": "shahed",
            "threat_category": "drone",
            "status": "destroyed",
            "count": 2,
            "lat": 46.9750, "lon": 31.9946,
            "location_name": "Миколаїв",
            "waypoints": [
                {"lat": 46.0, "lon": 31.0, "name": "Чорне море"},
                {"lat": 46.6, "lon": 31.5, "name": "Миколаївська"},
                {"lat": 46.9750, "lon": 31.9946, "name": "Миколаїв"},
            ],
            "directions": {"from": "Чорне море"},
            "channel": "КПСЗСУ",
            "text": "✅ Збито: 2 Шахеди над Миколаєвом. ППО спрацювала успішно.",
        },
        {
            "threat_type": "x101",
            "threat_category": "missile",
            "status": "moving",
            "count": 2,
            "lat": 49.2331, "lon": 28.4682,
            "location_name": "Вінниця",
            "waypoints": [
                {"lat": 52.0, "lon": 25.0, "name": "Білорусь"},
                {"lat": 50.8, "lon": 26.5, "name": "Рівненська"},
                {"lat": 49.9, "lon": 27.5, "name": "Хмельницька"},
                {"lat": 49.2331, "lon": 28.4682, "name": "Вінниця"},
            ],
            "directions": {"from": "Білорусь", "to": "Захід"},
            "channel": "War Monitor",
            "text": "🚀 Х-101 зафіксовані в повітряному просторі. Рухаються з Білорусі через Рівненщину.",
        },
        {
            "threat_type": "kinzhal",
            "threat_category": "missile",
            "status": "launch",
            "count": 1,
            "lat": 49.5535, "lon": 25.5948,
            "location_name": "Тернопіль",
            "waypoints": [
                {"lat": 55.0, "lon": 37.0, "name": "Москва (RU)"},
                {"lat": 52.0, "lon": 32.0, "name": "Брянськ (RU)"},
                {"lat": 49.5535, "lon": 25.5948, "name": "Тернопіль"},
            ],
            "directions": {"from": "Росія"},
            "channel": "КПСЗСУ",
            "text": "🔴 Кинджал! Гіперзвукова ракета зафіксована в Тернопільській області.",
        },
    ]

    time.sleep(3)  # Wait for server to fully start
    log.info("[DEMO] Starting demo event injection")

    idx = 0
    while True:
        evt = dict(demo_events[idx % len(demo_events)])
        evt["id"] = str(uuid.uuid4())
        evt["timestamp"] = datetime.now(timezone.utc).isoformat()
        evt["message_id"] = 0
        evt["channel_raw"] = evt["channel"].lower().replace(" ", "_")
        evt["all_threats"] = [{"name": evt["threat_type"], "category": evt["threat_category"]}]

        # Randomise position slightly
        import random
        if evt["waypoints"]:
            base = evt["waypoints"][-1]
            evt["lat"] = base["lat"] + random.uniform(-0.15, 0.15)
            evt["lon"] = base["lon"] + random.uniform(-0.15, 0.15)

        server.add_event(evt)
        log.info("[DEMO] Injected: %s @ %s", evt["threat_type"], evt["location_name"])

        idx += 1
        time.sleep(random.uniform(8, 20))  # New event every 8-20 seconds


# ── Server thread ─────────────────────────────────────────────────────────────

def run_server(host: str, port: int) -> None:
    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        log_level="warning",
        reload=False,
    )


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ukraine Drone Map")
    parser.add_argument("--setup", action="store_true", help="Re-run first-time setup")
    parser.add_argument("--browser", action="store_true", help="Open in system browser")
    parser.add_argument("--demo", action="store_true", help="Run in demo mode (no Telegram)")
    parser.add_argument("--port", type=int, default=None, help="Override server port")
    args = parser.parse_args()

    # ── Setup / config ────────────────────────────────────────────────────────
    if args.setup or (not CONFIG_PATH.exists() and not args.demo):
        if not args.demo:
            cfg = run_setup()
        else:
            cfg = {}
    else:
        cfg = load_config()

    server_cfg = cfg.get("server", {})
    host = server_cfg.get("host", "127.0.0.1")
    port = args.port or server_cfg.get("port", 8765)
    url = f"http://{host}:{port}"

    # ── Start FastAPI server ──────────────────────────────────────────────────
    log.info("Starting server at %s", url)
    server_thread = threading.Thread(
        target=run_server, args=(host, port), daemon=True, name="uvicorn"
    )
    server_thread.start()
    time.sleep(1.5)  # Give server a moment to bind

    # ── Start Telegram monitor ────────────────────────────────────────────────
    if args.demo:
        log.info("DEMO mode — no Telegram connection")
        demo_thread = threading.Thread(
            target=run_demo_injector, daemon=True, name="demo"
        )
        demo_thread.start()
    elif cfg.get("telegram", {}).get("api_id"):
        from telegram_monitor import run_monitor_thread
        tg_thread = threading.Thread(
            target=run_monitor_thread,
            args=(cfg,),
            daemon=True,
            name="telegram",
        )
        tg_thread.start()
    else:
        log.warning("No Telegram credentials — run with --demo or --setup")

    # ── Open UI ───────────────────────────────────────────────────────────────
    if args.browser:
        import webbrowser
        webbrowser.open(url)
        log.info("Opened in browser. Press Ctrl+C to quit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            log.info("Shutting down.")
    else:
        try:
            import webview
            log.info("Opening desktop window …")
            webview.create_window(
                "Ukraine Drone Map",
                url=url,
                width=1400,
                height=900,
                resizable=True,
                min_size=(800, 600),
            )
            webview.start()
        except ImportError:
            log.warning("pywebview not installed — falling back to system browser")
            import webbrowser
            webbrowser.open(url)
            log.info("Press Ctrl+C to quit.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                log.info("Shutting down.")


if __name__ == "__main__":
    main()
