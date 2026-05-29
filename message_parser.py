"""
Parse Ukrainian air-defense Telegram messages to extract structured threat data.
Handles Ukrainian text with regex patterns and the locations database.
"""

import re
import uuid
from datetime import datetime, timezone
from locations_db import find_locations_in_text

# ── Threat type patterns (Ukrainian + transliteration) ────────────────────────
THREAT_PATTERNS = [
    # Shahed drones
    (r"шахед(?:и|ів)?|shahed|shaheed|бпла[- ]шахед", "shahed", "drone"),
    # Geran (Shahed rebranded)
    (r"герань|geran", "geran", "drone"),
    # General UAV/drone
    (r"бпла|дрон(?:и|ів)?|uav|drone", "drone", "drone"),
    # Kalibr cruise missile
    (r"калібр(?:и|ів)?|kalibr|caliber", "kalibr", "missile"),
    # Kinzhal hypersonic
    (r"кинджал(?:и|ів)?|kinzhal|kindjal|кинджали", "kinzhal", "missile"),
    # Iskander
    (r"іскандер(?:и|ів)?|iskander", "iskander", "missile"),
    # X-101/X-555 cruise missiles
    (r"х-101|x-101|х-555|x-555|х101|x101", "x101", "missile"),
    # X-22
    (r"х-22|x-22|х22|x22", "x22", "missile"),
    # X-59
    (r"х-59|x-59|х59|x59", "x59", "missile"),
    # X-47 Kinzhal (same)
    (r"х-47|x-47", "kinzhal", "missile"),
    # Onix anti-ship
    (r"онікс|oniks|оникс", "oniks", "missile"),
    # Balistic missile (generic)
    (r"балістична|балістичні|ballistic", "ballistic", "missile"),
    # General missile
    (r"ракет(?:а|и|ою|ами|ній)?", "missile", "missile"),
]

# Pre-compile threat regexes
COMPILED_THREATS = [
    (re.compile(pat, re.IGNORECASE), name, category)
    for pat, name, category in THREAT_PATTERNS
]

# ── Status patterns ────────────────────────────────────────────────────────────
STATUS_PATTERNS = {
    "destroyed": re.compile(
        r"збито|знищено|перехоплено|ліквідовано|пошкоджено|впав|впала|збили|знищили",
        re.IGNORECASE,
    ),
    "alert": re.compile(
        r"тривога|загроза|увага|небезпека|alert|попередження",
        re.IGNORECASE,
    ),
    "moving": re.compile(
        r"рухається|летить|летять|рухаються|летів|летіли|flying|moving|прямує|прямують",
        re.IGNORECASE,
    ),
    "launch": re.compile(
        r"запущено|пуск|виліт|вилетів|вилетіла|launch|fired|зафіксовано",
        re.IGNORECASE,
    ),
}

# ── Direction / origin patterns ────────────────────────────────────────────────
DIRECTION_FROM = re.compile(
    r"(?:з боку|з напрямку|від|from|із)\s+([\w\-'іїєА-ЯіїєҐґЄєІіЇї]{3,}(?:\s+[\w\-'іїєА-ЯіїєҐґЄєІіЇї]{3,})?)",
    re.IGNORECASE,
)
DIRECTION_TO = re.compile(
    r"(?:у напрямку|в напрямку|\bдо\b|towards?|toward)\s+([\w\-'іїєА-ЯіїєҐґЄєІіЇї]{3,}(?:\s+[\w\-'іїєА-ЯіїєҐґЄєІіЇї]{3,})?)",
    re.IGNORECASE,
)

# ── Count pattern ─────────────────────────────────────────────────────────────
COUNT_PATTERN = re.compile(r"(\d+)\s*(?:шахед|бпла|ракет|дрон|калібр|кинджал)", re.IGNORECASE)

# ── Air-defense success pattern ────────────────────────────────────────────────
INTERCEPT_COUNT = re.compile(
    r"збито[:\s]+(\d+)|знищено[:\s]+(\d+)|перехоплено[:\s]+(\d+)", re.IGNORECASE
)


def detect_threats(text: str) -> list[dict]:
    """Return list of detected threat types with name and category."""
    found = []
    seen = set()
    for pattern, name, category in COMPILED_THREATS:
        if pattern.search(text) and name not in seen:
            found.append({"name": name, "category": category})
            seen.add(name)
    return found


def detect_status(text: str) -> str:
    """Return primary status string from message text."""
    for status, pattern in STATUS_PATTERNS.items():
        if pattern.search(text):
            return status
    return "unknown"


def extract_count(text: str) -> int:
    """Extract number of threats mentioned, or 1 if not specified."""
    m = COUNT_PATTERN.search(text)
    if m:
        return int(m.group(1))
    return 1


def extract_directions(text: str) -> dict:
    """Extract origin and destination directions from text."""
    directions = {}
    m = DIRECTION_FROM.search(text)
    if m:
        directions["from"] = m.group(1).strip()
    m = DIRECTION_TO.search(text)
    if m:
        directions["to"] = m.group(1).strip()
    return directions


def extract_channel_name(channel_username: str) -> str:
    mapping = {
        "kpszsu": "КПСЗСУ",
        "war_monitor": "War Monitor",
        "mon1tor_ua": "Monitor UA",
    }
    return mapping.get(channel_username.lower().lstrip("@"), channel_username)


def parse_message(text: str, channel: str, message_id: int = 0) -> dict | None:
    """
    Parse a Telegram message into a structured threat event.
    Returns None if the message doesn't appear to be a threat report.
    """
    if not text or len(text) < 10:
        return None

    threats = detect_threats(text)
    locations = find_locations_in_text(text)
    status = detect_status(text)
    count = extract_count(text)
    directions = extract_directions(text)

    # Reject messages with no identifiable threat type and no location
    if not threats and not locations:
        return None

    # At minimum need a location OR a specific threat type (not just generic terms)
    specific_threats = [t for t in threats if t["name"] not in ("missile", "drone")]
    if not locations and not specific_threats:
        return None

    # Build the event
    now = datetime.now(timezone.utc)
    primary_threat = threats[0] if threats else {"name": "unknown", "category": "unknown"}
    primary_location = locations[0] if locations else None

    event: dict = {
        "id": str(uuid.uuid4()),
        "timestamp": now.isoformat(),
        "channel": extract_channel_name(channel),
        "channel_raw": channel,
        "message_id": message_id,
        "text": text[:500],
        "threat_type": primary_threat["name"],
        "threat_category": primary_threat["category"],
        "all_threats": threats,
        "status": status,
        "count": count,
        "directions": directions,
        "locations": locations,
        "lat": primary_location["lat"] if primary_location else None,
        "lon": primary_location["lon"] if primary_location else None,
        "location_name": primary_location["name"] if primary_location else None,
        "waypoints": [{"lat": loc["lat"], "lon": loc["lon"], "name": loc["name"]} for loc in locations],
    }

    # Jitter coordinates slightly so overlapping markers are visible
    if event["lat"] is not None:
        import random
        event["lat"] += random.uniform(-0.03, 0.03)
        event["lon"] += random.uniform(-0.03, 0.03)

    return event


# ── Human-readable threat labels ─────────────────────────────────────────────
THREAT_LABELS = {
    "shahed": "Shahed",
    "geran": "Geranium",
    "drone": "БПЛА / Drone",
    "kalibr": "Kalibr",
    "kinzhal": "Kinzhal",
    "iskander": "Iskander",
    "x101": "X-101",
    "x22": "X-22",
    "x59": "X-59",
    "oniks": "Oniks",
    "ballistic": "Ballistic",
    "missile": "Missile",
    "unknown": "Unknown",
}

THREAT_COLORS = {
    "shahed": "#ff6600",
    "geran": "#ff4400",
    "drone": "#ffaa00",
    "kalibr": "#ff0000",
    "kinzhal": "#cc00ff",
    "iskander": "#ff0066",
    "x101": "#ff3300",
    "x22": "#dd2200",
    "x59": "#ee1100",
    "oniks": "#ff0044",
    "ballistic": "#ff00aa",
    "missile": "#ff2200",
    "unknown": "#888888",
}

STATUS_COLORS = {
    "destroyed": "#00ff44",
    "alert": "#ffdd00",
    "moving": "#ff6600",
    "launch": "#ff2200",
    "unknown": "#888888",
}
