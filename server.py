"""
FastAPI backend: REST + WebSocket hub.
All connected frontends receive real-time threat events pushed from the
Telegram monitor. Also serves the web UI static files.
"""

import asyncio
import json
import logging
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

log = logging.getLogger("server")

app = FastAPI(title="Ukraine Drone Map")

WEB_DIR = Path(__file__).parent / "web"

# Shared state -----------------------------------------------------------

# Recent events ring-buffer (newest first)
MAX_EVENTS = 300
_events: deque[dict] = deque(maxlen=MAX_EVENTS)

# Active WebSocket connections
_clients: set[WebSocket] = set()

# Stats
_stats: dict[str, Any] = {
    "total_messages": 0,
    "total_threats": 0,
    "channels_seen": set(),
    "started": datetime.now(timezone.utc).isoformat(),
}

# The running event loop — set on startup so background threads can post to it
_loop: asyncio.AbstractEventLoop | None = None


@app.on_event("startup")
async def _on_startup():
    global _loop
    _loop = asyncio.get_running_loop()


# Public helpers used by telegram_monitor --------------------------------

def add_event(event: dict) -> None:
    """Append a parsed event and broadcast to all WS clients (thread-safe)."""
    _events.appendleft(event)
    _stats["total_threats"] += 1
    _stats["channels_seen"].add(event.get("channel_raw", ""))
    if _loop is not None and _loop.is_running():
        asyncio.run_coroutine_threadsafe(_broadcast(event), _loop)


def increment_message_count() -> None:
    _stats["total_messages"] += 1


async def _broadcast(payload: dict) -> None:
    dead = set()
    msg = json.dumps({"type": "event", "data": payload})
    for ws in _clients.copy():
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)


# Routes -----------------------------------------------------------------

@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/events")
async def get_events():
    """Return up to 100 recent events for initial page load."""
    return {"events": list(_events)[:100]}


@app.get("/api/stats")
async def get_stats():
    return {
        **_stats,
        "channels_seen": list(_stats["channels_seen"]),
        "active_clients": len(_clients),
        "buffered_events": len(_events),
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    log.info("WS client connected (%d total)", len(_clients))
    try:
        # Send recent events on connect so map populates immediately
        recent = list(_events)[:50]
        await ws.send_text(json.dumps({"type": "history", "data": recent}))

        # Keep alive — wait for client to close
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.debug("WS closed: %s", exc)
    finally:
        _clients.discard(ws)
        log.info("WS client disconnected (%d total)", len(_clients))


# Mount static files (CSS / JS)
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
