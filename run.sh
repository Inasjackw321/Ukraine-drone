#!/usr/bin/env bash
# Ukraine Drone Map — launch script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Install dependencies if needed ────────────────────────────────────────────
if ! python3 -c "import fastapi" 2>/dev/null; then
  echo "Installing dependencies…"
  pip3 install -r requirements.txt
fi

# ── Parse args ────────────────────────────────────────────────────────────────
ARGS="$*"

if [ -z "$ARGS" ]; then
  if [ ! -f config.json ]; then
    echo ""
    echo "No config.json found."
    echo "Run with --demo to try the app without Telegram, or --setup to configure."
    echo ""
    echo "Options:"
    echo "  --demo     Demo mode (no Telegram needed)"
    echo "  --setup    First-time Telegram setup"
    echo "  --browser  Open in browser instead of desktop window"
    echo ""
    ARGS="--demo"
  fi
fi

python3 main.py $ARGS
