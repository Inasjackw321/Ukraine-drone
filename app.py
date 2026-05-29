#!/usr/bin/env python3
"""
Ukraine Drone Map
Run:  python app.py           (prompts for credentials on first run)
      python app.py --setup   (re-run credential setup)
      python app.py --browser (open in browser instead of desktop window)
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Dependency pre-check — show a readable error before anything can crash
# ─────────────────────────────────────────────────────────────────────────────
def _check_deps() -> None:
    import importlib.util as _ilu
    required = {
        "fastapi":   "pip install fastapi",
        "uvicorn":   "pip install uvicorn[standard]",
        "telethon":  "pip install telethon",
        "aiofiles":  "pip install aiofiles",
        "websockets":"pip install websockets",
    }
    missing = [f"  {pkg:12s}  →  {cmd}" for pkg, cmd in required.items()
               if _ilu.find_spec(pkg) is None]
    if missing:
        print("\n  ── Missing packages ──────────────────────────────────")
        print("\n".join(missing))
        print("\n  Fix all at once:  pip install -r requirements.txt")
        print("─" * 54)
        input("\n  Press Enter to close…")
        sys.exit(1)

_check_deps()

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("ukraine-drone")

HERE   = Path(__file__).parent
WEB    = HERE / "web"
CONFIG = HERE / "config.json"

# ─────────────────────────────────────────────────────────────────────────────
# Ukrainian Locations  (lat, lon)
# ─────────────────────────────────────────────────────────────────────────────
LOCS: dict[str, tuple[float, float]] = {
    # ── oblasts ──────────────────────────────────────────────────────────────
    "київська": (50.52, 30.87),     "київщина": (50.52, 30.87),
    "харківська": (49.99, 36.23),   "харківщина": (49.99, 36.23),
    "дніпропетровська": (48.46, 35.05), "дніпровська": (48.46, 35.05),
    "одеська": (46.48, 30.72),      "одещина": (46.48, 30.72),
    "запорізька": (47.84, 35.14),   "запоріжжя область": (47.84, 35.14),
    "миколаївська": (46.98, 31.99), "миколаївщина": (46.98, 31.99),
    "херсонська": (46.64, 32.62),   "херсонщина": (46.64, 32.62),
    "донецька": (48.02, 37.80),     "донеччина": (48.02, 37.80),
    "луганська": (48.57, 39.31),    "луганщина": (48.57, 39.31),
    "сумська": (50.91, 34.80),      "сумщина": (50.91, 34.80),
    "чернігівська": (51.50, 31.29), "чернігівщина": (51.50, 31.29),
    "полтавська": (49.59, 34.55),   "полтавщина": (49.59, 34.55),
    "черкаська": (49.44, 32.06),    "черкащина": (49.44, 32.06),
    "кіровоградська": (48.51, 32.26),
    "вінницька": (49.23, 28.47),    "вінниччина": (49.23, 28.47),
    "житомирська": (50.25, 28.66),  "житомирщина": (50.25, 28.66),
    "хмельницька": (49.42, 26.99),  "хмельниччина": (49.42, 26.99),
    "тернопільська": (49.55, 25.59),"тернопільщина": (49.55, 25.59),
    "рівненська": (50.62, 26.25),   "рівненщина": (50.62, 26.25),
    "волинська": (50.75, 25.33),    "волинь": (50.75, 25.33),
    "львівська": (49.84, 24.03),    "львівщина": (49.84, 24.03),
    "закарпатська": (48.62, 22.29), "закарпаття": (48.62, 22.29),
    "івано-франківська": (48.92, 24.71), "прикарпаття": (48.92, 24.71),
    "чернівецька": (48.29, 25.94),  "буковина": (48.29, 25.94),

    # ── major cities ─────────────────────────────────────────────────────────
    "київ": (50.45, 30.52),       "kyiv": (50.45, 30.52),
    "харків": (49.99, 36.23),     "kharkiv": (49.99, 36.23),
    "харкові": (49.99, 36.23),    "харкова": (49.99, 36.23),
    "дніпро": (48.46, 35.05),     "dnipro": (48.46, 35.05),
    "одеса": (46.48, 30.72),      "одесі": (46.48, 30.72),
    "запоріжжя": (47.84, 35.14),
    "миколаїв": (46.98, 31.99),   "миколаєві": (46.98, 31.99),
    "миколаєвом": (46.98, 31.99), "миколаєва": (46.98, 31.99),
    "херсон": (46.64, 32.62),     "херсоні": (46.64, 32.62),
    "донецьк": (48.02, 37.80),
    "луганськ": (48.57, 39.31),
    "суми": (50.91, 34.80),       "сумах": (50.91, 34.80),
    "чернігів": (51.50, 31.29),   "чернігові": (51.50, 31.29),
    "полтава": (49.59, 34.55),    "полтаві": (49.59, 34.55),
    "черкаси": (49.44, 32.06),
    "вінниця": (49.23, 28.47),    "вінниці": (49.23, 28.47),
    "житомир": (50.25, 28.66),    "житомирі": (50.25, 28.66),
    "хмельницький": (49.42, 26.99),
    "тернопіль": (49.55, 25.59),  "тернополі": (49.55, 25.59),
    "рівне": (50.62, 26.25),      "рівного": (50.62, 26.25),
    "луцьк": (50.75, 25.33),
    "львів": (49.84, 24.03),
    "ужгород": (48.62, 22.29),
    "івано-франківськ": (48.92, 24.71),
    "чернівці": (48.29, 25.94),
    "кропивницький": (48.51, 32.26),
    "маріуполь": (47.10, 37.54),  "маріуполі": (47.10, 37.54),
    "краматорськ": (48.72, 37.58),
    "слов'янськ": (48.86, 37.63),
    "бахмут": (48.60, 37.99),
    "кривий ріг": (47.91, 33.39),
    "кременчук": (49.07, 33.42),
    "нікополь": (47.57, 34.40),
    "мелітополь": (46.85, 35.37),
    "бердянськ": (46.76, 36.80),
    "запоріжжям": (47.84, 35.14),
    "енергодар": (47.50, 34.65),
    "нова каховка": (46.76, 33.38),
    "буча": (50.55, 30.23),
    "ірпінь": (50.52, 30.25),
    "бровари": (50.51, 30.79),
    "біла церква": (49.80, 30.12),
    "конотоп": (51.24, 33.21),
    "шостка": (51.87, 33.47),
    "охтирка": (50.31, 34.90),
    "куп'янськ": (49.71, 37.61), "куп'янська": (49.71, 37.61),
    "ізюм": (49.21, 37.27),
    "лозова": (48.89, 36.32),
    "чугуїв": (49.83, 36.68),

    # ── geographic / cross-border ─────────────────────────────────────────────
    "крим": (44.95, 34.10),       "crimea": (44.95, 34.10),
    "чорне море": (45.50, 31.50),
    "азовське море": (46.00, 36.50),
    "білорусь": (52.50, 28.00),
    "росія": (51.00, 38.00),
}


def find_locations(text: str) -> list[dict]:
    """Return list of {name, lat, lon} found in text (longest match wins)."""
    tl = text.lower()
    results: list[dict] = []
    covered: list[tuple[int, int]] = []
    for key in sorted(LOCS, key=len, reverse=True):
        i = tl.find(key)
        if i == -1:
            continue
        end = i + len(key)
        if any(s <= i and end <= e for s, e in covered):
            continue
        covered.append((i, end))
        lat, lon = LOCS[key]
        results.append({"name": text[i:end], "lat": lat, "lon": lon})
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Message Parser
# ─────────────────────────────────────────────────────────────────────────────

# Ordered by priority — first match wins for primary type
THREAT_RE: list[tuple[re.Pattern, str]] = [
    (re.compile(r"кинджал|kinzhal", re.I),           "kinzhal"),
    (re.compile(r"іскандер|iskander",  re.I),         "iskander"),
    (re.compile(r"х-22|x-22",         re.I),          "x22"),
    (re.compile(r"х-101|x-101|х101",  re.I),          "x101"),
    (re.compile(r"х-59|x-59",         re.I),          "x59"),
    (re.compile(r"онікс|oniks",        re.I),          "oniks"),
    (re.compile(r"калібр|kalibr",      re.I),          "kalibr"),
    (re.compile(r"шахед|shaheed|shahed", re.I),        "shahed"),
    (re.compile(r"герань|geran",       re.I),          "geran"),
    (re.compile(r"балістич",           re.I),          "ballistic"),
    (re.compile(r"ракет",              re.I),          "missile"),
    (re.compile(r"бпла|дрон",          re.I),          "drone"),
]

STATUS_RE = {
    "destroyed": re.compile(r"збито|знищено|перехоплено|ліквідовано|збили|знищили", re.I),
    "moving":    re.compile(r"рухається|летить|летять|прямує|рухаються|летів|летіла", re.I),
    "launch":    re.compile(r"запущено|пуск|виліт|вилетів|зафіксовано", re.I),
    "alert":     re.compile(r"тривога|загроза|увага|небезпека|попередження", re.I),
}

FROM_RE = re.compile(
    r"(?:з боку|з напрямку|від|із)\s+([\w\-'іїєА-ЯіїєҐґЄєІіЇї]{3,}(?:\s+[\w\-'іїєА-ЯіїєҐґЄєІіЇї]{3,})?)",
    re.I,
)
TO_RE = re.compile(
    r"(?:у напрямку|в напрямку|\bдо\b|towards?)\s+([\w\-'іїєА-ЯіїєҐґЄєІіЇї]{3,}(?:\s+[\w\-'іїєА-ЯіїєҐґЄєІіЇї]{3,})?)",
    re.I,
)
COUNT_RE = re.compile(r"(\d+)\s*(?:шахед|бпла|ракет|дрон|калібр|кинджал)", re.I)

CHANNEL_NAMES = {
    "kpszsu":    "КПСЗСУ",
    "war_monitor": "War Monitor",
    "mon1tor_ua":  "Monitor UA",
    "eradar_ua":   "eRadar UA",
}


def parse_message(text: str, channel: str, msg_id: int = 0) -> dict | None:
    if not text or len(text) < 15:
        return None

    # Detect primary threat type
    threat = "unknown"
    for pat, name in THREAT_RE:
        if pat.search(text):
            threat = name
            break

    locs = find_locations(text)
    if not locs and threat in ("unknown", "missile", "drone"):
        return None  # not a useful event

    # Status
    status = "unknown"
    for st, pat in STATUS_RE.items():
        if pat.search(text):
            status = st
            break

    # Count
    m = COUNT_RE.search(text)
    count = int(m.group(1)) if m else 1

    # Directions
    frm = (FROM_RE.search(text) or type("", (), {"group": lambda s, i: None})()).group(1)
    to  = (TO_RE.search(text)   or type("", (), {"group": lambda s, i: None})()).group(1)

    import random
    primary = locs[0] if locs else None

    return {
        "id":        str(uuid.uuid4()),
        "ts":        datetime.now(timezone.utc).isoformat(),
        "channel":   CHANNEL_NAMES.get(channel, channel),
        "msg_id":    msg_id,
        "text":      text[:400],
        "type":      threat,
        "status":    status,
        "count":     count,
        "from":      frm,
        "to":        to,
        "lat":       (primary["lat"] + random.uniform(-0.04, 0.04)) if primary else None,
        "lon":       (primary["lon"] + random.uniform(-0.04, 0.04)) if primary else None,
        "location":  primary["name"] if primary else None,
        "waypoints": [{"lat": l["lat"], "lon": l["lon"], "name": l["name"]} for l in locs],
    }


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI + WebSocket hub
# ─────────────────────────────────────────────────────────────────────────────
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

_events: deque[dict] = deque(maxlen=500)
_clients: set[WebSocket] = set()
_loop: asyncio.AbstractEventLoop | None = None
_stats = {"total": 0, "channels": set()}


@asynccontextmanager
async def _lifespan(app):
    global _loop
    _loop = asyncio.get_running_loop()
    yield


web_app = FastAPI(lifespan=_lifespan)


def push_event(evt: dict) -> None:
    _events.appendleft(evt)
    _stats["total"] += 1
    _stats["channels"].add(evt.get("channel", ""))
    if _loop and _loop.is_running():
        asyncio.run_coroutine_threadsafe(_broadcast({"type": "event", "data": evt}), _loop)


async def _broadcast(msg: dict) -> None:
    text = json.dumps(msg)
    dead: set[WebSocket] = set()
    for ws in _clients.copy():
        try:
            await ws.send_text(text)
        except Exception:
            dead.add(ws)
    _clients -= dead


@web_app.get("/")
def _index():
    return FileResponse(WEB / "index.html")


@web_app.get("/api/events")
def _get_events():
    return {"events": list(_events)[:100]}


@web_app.get("/api/stats")
def _get_stats():
    return {**_stats, "channels": list(_stats["channels"]), "clients": len(_clients)}


_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

# ── Tile proxy — serves map tiles through localhost so pywebview can load them
_tile_cache: dict[str, bytes] = {}

_TILE_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "image/png,image/*,*/*",
    "Referer": "https://www.openstreetmap.org/",
}

# Candidate tile URLs tried in order until one succeeds
def _tile_urls(z: int, x: int, y: int) -> list[str]:
    sub = "abc"[int(x + y) % 3]
    return [
        f"https://{sub}.basemaps.cartocdn.com/dark_matter_nolabels/{z}/{x}/{y}.png",
        f"https://cartodb-basemaps-{sub}.global.ssl.fastly.net/dark_matter_nolabels/{z}/{x}/{y}.png",
        f"https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    ]


def _fetch_tile_sync(z: int, x: int, y: int) -> bytes | None:
    import urllib.request
    cache_key = f"{z}/{x}/{y}"
    if cache_key in _tile_cache:
        return _tile_cache[cache_key]
    for url in _tile_urls(z, x, y):
        try:
            req = urllib.request.Request(url, headers=_TILE_HEADERS)
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
            if len(_tile_cache) < 4000:
                _tile_cache[cache_key] = data
            return data
        except Exception:
            continue
    return None


@web_app.get("/tiles/{z}/{x}/{y}.png")
async def _tile_dark(z: int, x: int, y: int):
    data = await asyncio.to_thread(_fetch_tile_sync, z, x, y)
    if data is None:
        return Response(status_code=503)
    return Response(content=data, media_type="image/png",
                    headers={"Cache-Control": "max-age=86400", "Access-Control-Allow-Origin": "*"})


@web_app.websocket("/ws")
async def _ws(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "history", "data": list(_events)[:80]}))
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=25)
            except asyncio.TimeoutError:
                await ws.send_text('{"type":"ping"}')
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _clients.discard(ws)


if WEB.exists():
    web_app.mount("/static", StaticFiles(directory=str(WEB)), name="static")


# ─────────────────────────────────────────────────────────────────────────────
# Telegram polling  (10-minute cycle)
# ─────────────────────────────────────────────────────────────────────────────
CHANNELS  = ["kpszsu", "war_monitor", "mon1tor_ua", "eradar_ua"]
POLL_SECS = 60  # 1 minute


async def _telegram_loop(cfg: dict) -> None:
    try:
        from telethon import TelegramClient
    except ImportError:
        log.error("telethon not installed — pip install telethon")
        return

    tg = cfg.get("telegram", {})
    client = TelegramClient(
        str(HERE / "session"),
        int(tg["api_id"]),
        tg["api_hash"],
    )

    phone = tg.get("phone", "")

    async def _code_cb() -> str:
        # Must use terminal input here — tkinter can't be called safely from threads
        print(f"\n  [Telegram] Check your phone ({phone}) for a verification code.")
        return input("  Code: ").strip()

    async def _pw_cb() -> str:
        import getpass
        return getpass.getpass("  [Telegram] 2FA password: ").strip()

    await client.start(phone=phone, code_callback=_code_cb, password=_pw_cb)
    log.info("Telegram authenticated")

    entities: dict[int, str] = {}
    for slug in cfg.get("channels", CHANNELS):
        try:
            ent = await client.get_entity(slug)
            entities[ent.id] = slug
            log.info("  channel ready: @%s", slug)
        except Exception as e:
            log.warning("  can't resolve @%s — %s", slug, e)

    last_ids: dict[str, int] = {s: 0 for s in entities.values()}
    first_pass = True

    while True:
        for eid, slug in entities.items():
            try:
                msgs = await client.get_messages(
                    eid,
                    limit=30 if first_pass else 50,
                    min_id=0 if first_pass else last_ids[slug],
                )
            except Exception as e:
                log.warning("fetch error %s: %s", slug, e)
                continue

            for msg in reversed(msgs or []):
                if msg.id <= last_ids[slug]:
                    continue
                last_ids[slug] = msg.id
                evt = parse_message(msg.message or "", slug, msg.id)
                if evt:
                    log.info("[%s] %-10s  %s", slug, evt["type"], evt.get("location", "?"))
                    push_event(evt)

        first_pass = False

        nxt = (datetime.now(timezone.utc) + timedelta(seconds=POLL_SECS)).isoformat()
        if _loop and _loop.is_running():
            asyncio.run_coroutine_threadsafe(
                _broadcast({"type": "next_update", "at": nxt}), _loop
            )
        log.info("Next Telegram poll in %d minutes", POLL_SECS // 60)
        await asyncio.sleep(POLL_SECS)


def _run_telegram(cfg: dict) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_telegram_loop(cfg))
    except Exception as e:
        log.error("Telegram monitor crashed: %s", e)
    finally:
        loop.close()



# ─────────────────────────────────────────────────────────────────────────────
# GUI helpers — use tkinter dialogs so the user can paste freely
# ─────────────────────────────────────────────────────────────────────────────
def _ask(title: str, prompt: str, password: bool = False) -> str:
    """Show a tkinter input dialog; returns stripped text or raises SystemExit."""
    try:
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk()
        root.withdraw()
        root.lift()
        root.attributes("-topmost", True)
        val = simpledialog.askstring(title, prompt, parent=root, show="*" if password else None)
        root.destroy()
        if val is None:
            raise SystemExit("Cancelled")
        return val.strip()
    except ImportError:
        # tkinter not available — fall back to terminal
        import getpass
        if password:
            return getpass.getpass(f"{prompt}: ").strip()
        return input(f"{prompt}: ").strip()


def _show_info(title: str, message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo(title, message, parent=root)
        root.destroy()
    except ImportError:
        print(f"\n  [{title}] {message}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Setup wizard
# ─────────────────────────────────────────────────────────────────────────────
def _run_setup() -> dict:
    print("\n" + "━" * 54)
    print("  Ukraine Drone Map — Telegram Setup")
    print("━" * 54)
    print("  Popup dialogs will appear — you can paste into them.\n")
    _show_info(
        "Telegram Setup",
        "Get free API credentials at:\nhttps://my.telegram.org/apps\n\n"
        "You will be asked for:\n  • API ID\n  • API Hash\n  • Phone number",
    )
    api_id   = _ask("Telegram Setup", "API ID (number from my.telegram.org/apps)")
    api_hash = _ask("Telegram Setup", "API Hash (long hex string)")
    phone    = _ask("Telegram Setup", "Phone number (e.g. +380XXXXXXXXX)")
    cfg = {
        "telegram": {"api_id": int(api_id), "api_hash": api_hash, "phone": phone},
        "channels": CHANNELS,
    }
    with open(CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)
    print("\n  ✓ Saved to config.json — starting app now…\n")
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# Download Leaflet + ant-path once so the desktop window works fully offline
# ─────────────────────────────────────────────────────────────────────────────
_LIB_ASSETS = {
    "leaflet.css": [
        "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css",
        "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
    ],
    "leaflet.js": [
        "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js",
        "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
    ],
    "ant-path.js": [
        "https://cdn.jsdelivr.net/npm/leaflet-ant-path@1.3.0/dist/leaflet-ant-path.js",
        "https://unpkg.com/leaflet-ant-path@1.3.0/dist/leaflet-ant-path.js",
    ],
}

def _ensure_web_libs() -> None:
    import urllib.request
    lib = WEB / "lib"
    lib.mkdir(exist_ok=True)
    for name, urls in _LIB_ASSETS.items():
        path = lib / name
        if path.exists():
            continue
        for url in urls:
            try:
                log.info("Downloading %s …", name)
                req = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA})
                with urllib.request.urlopen(req, timeout=10) as r:
                    path.write_bytes(r.read())
                log.info("  ✓ %s", name)
                break
            except Exception as e:
                log.warning("  ✗ %s from %s: %s", name, url, e)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="Ukraine Drone Map")
    ap.add_argument("--setup",   action="store_true", help="Configure Telegram")
    ap.add_argument("--browser", action="store_true", help="Open in browser only")
    ap.add_argument("--port",    type=int, default=8765)
    args = ap.parse_args()

    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║  🛡️  UKRAINE DRONE MAP                ║")
    print("  ╚══════════════════════════════════════╝")
    print()

    # ── Config ────────────────────────────────────────────────────────────────
    if args.setup or not CONFIG.exists():
        cfg = _run_setup()
    else:
        with open(CONFIG) as f:
            cfg = json.load(f)

    # ── Server ────────────────────────────────────────────────────────────────
    import uvicorn
    t = threading.Thread(
        target=lambda: uvicorn.run(
            web_app, host="127.0.0.1", port=args.port,
            log_level="warning", reload=False,
        ),
        daemon=True, name="server",
    )
    t.start()
    time.sleep(1.2)
    url = f"http://127.0.0.1:{args.port}"
    log.info("Server ready at %s", url)

    # ── Background: download Leaflet libs + start Telegram ────────────────────
    threading.Thread(target=_ensure_web_libs, daemon=True, name="libs").start()
    threading.Thread(target=_run_telegram, args=(cfg,), daemon=True, name="telegram").start()

    # ── Open UI ────────────────────────────────────────────────────────────────
    if not args.browser:
        try:
            import webview
            log.info("Opening desktop window")
            webview.create_window(
                "Ukraine Drone Map", url=url,
                width=1440, height=900, resizable=True,
                background_color="#080c10",
            )
            webview.start(private_mode=False)
            return
        except Exception as e:
            if not isinstance(e, ImportError):
                log.warning("pywebview failed (%s) — falling back to browser", e)

    import webbrowser
    webbrowser.open(url)
    log.info("Opened in browser — press Ctrl+C to quit")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Shutting down")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        msg = traceback.format_exc()
        # Write to a file so the error is readable even if the window closes
        try:
            (Path(__file__).parent / "error.log").write_text(msg)
        except Exception:
            pass
        print("\n" + "─" * 54)
        print("  APP CRASHED — error also saved to error.log")
        print("─" * 54)
        print(msg)
        print("─" * 54)
        input("\n  Press Enter to close…")
