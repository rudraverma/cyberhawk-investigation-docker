#!/bin/bash
# ── CyberHawk GhidraMCP — Binary Loader ────────────────────────────────────
# Imports + auto-analyzes a binary into a named Ghidra project using
# analyzeHeadless (batch mode — no GUI required).
#
# Usage:
#   load_binary.sh <binary_path> [project_name]
#
# Examples:
#   load_binary.sh /workspace/upload/malware.exe
#   load_binary.sh /workspace/upload/malware.exe ransomware_analysis
#
# After loading, open the project in Ghidra GUI to use GhidraMCP tools.
# Project is saved to /workspace/ghidra-projects/<project_name>/
# ─────────────────────────────────────────────────────────────────────────────
set -e

BINARY="${1:?Usage: load_binary.sh <binary_path> [project_name]}"
PROJECT="${2:-$(basename "$BINARY" | sed 's/\.[^.]*$//')_$(date +%Y%m%d_%H%M%S)}"
PROJECT_DIR="/workspace/ghidra-projects"
LOG_FILE="${PROJECT_DIR}/${PROJECT}_analysis.log"

if [ ! -f "$BINARY" ]; then
    echo "[load_binary] ERROR: File not found: $BINARY"
    exit 1
fi

echo "[load_binary] ─────────────────────────────────────────────────────────"
echo "[load_binary] Binary:  $BINARY"
echo "[load_binary] Project: $PROJECT_DIR/$PROJECT"
echo "[load_binary] Log:     $LOG_FILE"
echo "[load_binary] ─────────────────────────────────────────────────────────"

mkdir -p "$PROJECT_DIR"

/ghidra/support/analyzeHeadless \
    "$PROJECT_DIR" "$PROJECT" \
    -import "$BINARY" \
    -overwrite \
    -log "$LOG_FILE" \
    "$@"  # forward any extra flags (e.g. -postScript, -processor)

EXIT_CODE=$?
echo "[load_binary] ─────────────────────────────────────────────────────────"
if [ $EXIT_CODE -eq 0 ]; then
    echo "[load_binary] SUCCESS — project saved to: $PROJECT_DIR/$PROJECT"
    echo "[load_binary] Analysis log: $LOG_FILE"
    echo "[load_binary]"
    echo "[load_binary] Next step: open $PROJECT in Ghidra GUI, then use"
    echo "[load_binary] GhidraMCP tools via Claude Code (MCP SSE on :8081)."
else
    echo "[load_binary] ERROR — analyzeHeadless exited with code $EXIT_CODE"
    echo "[load_binary] Check log: $LOG_FILE"
fi
echo "[load_binary] ─────────────────────────────────────────────────────────"
exit $EXIT_CODE
