#!/bin/bash
# ── CyberHawk GhidraMCP — One-time plugin enablement ────────────────────────
# Run this ONCE if Ghidra's HTTP server doesn't start automatically.
# It uses xdotool to navigate Ghidra's GUI and enable GhidraMCPPlugin.
#
# Usage (from your server):
#   docker exec -it cyberhawk-ghidra /enable-plugin.sh
# ─────────────────────────────────────────────────────────────────────────────
export DISPLAY=:1

echo "[enable-plugin] Waiting for Ghidra window..."
WID=""
for i in $(seq 1 30); do
    WID=$(xdotool search --name "Ghidra" 2>/dev/null | head -1)
    [ -n "$WID" ] && break
    echo "[enable-plugin]  ... waiting $i/30"
    sleep 2
done

if [ -z "$WID" ]; then
    echo "[enable-plugin] ERROR: No Ghidra window found. Is Ghidra running?"
    exit 1
fi

echo "[enable-plugin] Found Ghidra window: $WID"
xdotool windowfocus --sync "$WID"
sleep 1

echo "[enable-plugin] Opening File menu..."
xdotool key --clearmodifiers --window "$WID" alt+F
sleep 1

echo "[enable-plugin] Navigating to Configure..."
# Look for Configure menu item
xdotool key --clearmodifiers --window "$WID" c
sleep 1

# If that didn't work, try arrow keys to find Configure
# (Ghidra's File menu: New Project, Open Project, ..., Configure, ...)
# Typically Configure is about 8-10 items down from top
echo "[enable-plugin] Attempting keyboard navigation..."
xdotool key --clearmodifiers --window "$WID" Escape
sleep 0.5

# Alternative: use the menu bar shortcut
xdotool key --clearmodifiers --window "$WID" alt+F
sleep 0.8

# Navigate down to Configure (position varies by Ghidra version)
for i in $(seq 1 10); do
    xdotool key --clearmodifiers --window "$WID" Down
    sleep 0.1
done

# Look for "Configure" text
xdotool key --clearmodifiers --window "$WID" Return
sleep 2

echo "[enable-plugin] Looking for Configure window..."
CONFIG_WID=$(xdotool search --name "Configure" 2>/dev/null | head -1)
if [ -z "$CONFIG_WID" ]; then
    echo ""
    echo "[enable-plugin] ────────────────────────────────────────────────────"
    echo "[enable-plugin] Automated setup did not open Configure dialog."
    echo "[enable-plugin]"
    echo "[enable-plugin] MANUAL STEPS (run from server):"
    echo "[enable-plugin]   1. Open a VNC viewer to the container display"
    echo "[enable-plugin]      docker run --rm -it -e DISPLAY=:1 ..."
    echo "[enable-plugin]      OR: forward X11 / use xvfb2vnc"
    echo "[enable-plugin]   2. In Ghidra: File → Configure → Developer"
    echo "[enable-plugin]   3. Check 'GhidraMCPPlugin' → OK"
    echo "[enable-plugin]   4. Restart container"
    echo "[enable-plugin]"
    echo "[enable-plugin] ALTERNATIVE: inject the plugin via tool XML patch"
    echo "[enable-plugin]   docker exec cyberhawk-ghidra /patch-tool-xml.sh"
    echo "[enable-plugin] ────────────────────────────────────────────────────"
    exit 1
fi

echo "[enable-plugin] Configure dialog found. Looking for Developer section..."
# Search for "Developer" in the window
xdotool search --name "Developer" --windowfocus 2>/dev/null
sleep 0.5

echo "[enable-plugin] Done — if successful, restart the container:"
echo "[enable-plugin]   docker compose --profile reverse-eng restart ghidra"
echo "[enable-plugin]   docker logs -f cyberhawk-ghidra"
