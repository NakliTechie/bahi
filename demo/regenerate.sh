#!/usr/bin/env bash
#
# Regenerate all Bahi demo screenshots and rebuild demo/index.html.
#
# What it does:
#   1. Ensures a dev server is running at http://localhost:8101/ serving Bahi/
#      (starts `python3 -m http.server 8101` in Bahi/ if nothing is listening)
#   2. Runs capture.py (Playwright → Chromium headless) to generate every
#      screenshot under demo/screenshots/<company>/NN-<slug>.png
#   3. Runs build_index.py to assemble demo/index.html from the captures
#
# Prerequisites (one-time):
#   pip3 install playwright
#   python3 -m playwright install chromium
#
# Usage:
#   cd Bahi/demo && ./regenerate.sh
#

set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
BAHI_DIR="$(cd "$DEMO_DIR/.." && pwd)"
PORT=8101
BASE="http://localhost:${PORT}/"

echo "[regenerate] demo dir:  $DEMO_DIR"
echo "[regenerate] bahi dir:  $BAHI_DIR"

# --- 1. make sure a server is serving Bahi/ on 8101 -------------------------
started_server=0
if curl -sf -o /dev/null "${BASE}index.html"; then
  echo "[regenerate] dev server already running at $BASE"
else
  echo "[regenerate] no server on :$PORT — starting python3 -m http.server in $BAHI_DIR"
  ( cd "$BAHI_DIR" && python3 -m http.server "$PORT" >/tmp/bahi-demo-server.log 2>&1 ) &
  SERVER_PID=$!
  started_server=1
  # wait up to 5s for it to come up
  for _ in 1 2 3 4 5; do
    if curl -sf -o /dev/null "${BASE}index.html"; then
      echo "[regenerate] server up (pid $SERVER_PID)"
      break
    fi
    sleep 1
  done
  if ! curl -sf -o /dev/null "${BASE}index.html"; then
    echo "[regenerate] ERROR: server failed to start. tail of /tmp/bahi-demo-server.log:"
    tail -n 20 /tmp/bahi-demo-server.log || true
    exit 1
  fi
fi

cleanup() {
  if [ "$started_server" -eq 1 ] && [ -n "${SERVER_PID:-}" ]; then
    echo "[regenerate] stopping dev server (pid $SERVER_PID)"
    kill "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# --- 2. run capture.py ------------------------------------------------------
echo "[regenerate] running capture.py..."
( cd "$DEMO_DIR" && python3 capture.py )

# --- 3. rebuild demo/index.html --------------------------------------------
echo "[regenerate] rebuilding index.html..."
( cd "$DEMO_DIR" && python3 build_index.py )

echo ""
echo "[regenerate] done."
echo "[regenerate] open:   file://$DEMO_DIR/index.html"
echo "[regenerate] or:     (cd \"$DEMO_DIR\" && python3 -m http.server 8202) and visit http://localhost:8202/"
