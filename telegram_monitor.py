"""
Telethon-based Telegram channel monitor.
Subscribes to public channels and forwards parsed messages to the server.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("telegram")

CHANNELS = [
    "kpszsu",       # Air Force of Ukraine
    "war_monitor",  # War Monitor aggregator
    "mon1tor_ua",   # Monitor UA
]


async def start_monitor(config: dict, event_callback) -> None:
    """
    Connect to Telegram and listen for new messages on CHANNELS.
    event_callback(event_dict) is called for each parsed threat event.

    Imports Telethon lazily so the app can start even without credentials.
    """
    try:
        from telethon import TelegramClient, events
        from telethon.errors import SessionPasswordNeededError
    except ImportError:
        log.error("telethon not installed — run: pip install telethon")
        return

    from message_parser import parse_message
    import server

    tg_cfg = config.get("telegram", {})
    api_id = tg_cfg.get("api_id")
    api_hash = tg_cfg.get("api_hash")
    phone = tg_cfg.get("phone", "")
    channels = config.get("channels", CHANNELS)

    if not api_id or not api_hash:
        log.error("Telegram api_id / api_hash not configured. Edit config.json.")
        return

    session_path = str(Path(__file__).parent / "drone_monitor")
    client = TelegramClient(session_path, int(api_id), api_hash)

    log.info("Connecting to Telegram …")
    await client.start(phone=phone)
    log.info("Connected as %s", await client.get_me())

    # Resolve channel entities upfront
    channel_entities = {}
    for ch in channels:
        try:
            entity = await client.get_entity(ch)
            channel_entities[entity.id] = ch
            log.info("Subscribed to: %s (id=%s)", ch, entity.id)
        except Exception as exc:
            log.warning("Could not resolve channel %s: %s", ch, exc)

    @client.on(events.NewMessage(chats=list(channel_entities.keys())))
    async def handler(event_msg):
        server.increment_message_count()
        text = event_msg.message.message or ""
        chat_id = event_msg.chat_id
        channel_slug = channel_entities.get(chat_id, "unknown")

        parsed = parse_message(text, channel_slug, message_id=event_msg.id)
        if parsed:
            log.debug("Event: %s @ %s", parsed["threat_type"], parsed.get("location_name"))
            server.add_event(parsed)
            if event_callback:
                event_callback(parsed)

    log.info("Monitoring %d channels. Waiting for messages …", len(channel_entities))
    await client.run_until_disconnected()


def run_monitor_thread(config: dict, event_callback=None) -> None:
    """
    Run the async monitor in a dedicated event loop (call from a thread).
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(start_monitor(config, event_callback))
    except Exception as exc:
        log.error("Monitor error: %s", exc)
    finally:
        loop.close()
