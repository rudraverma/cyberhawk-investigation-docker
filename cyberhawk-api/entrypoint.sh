#!/bin/bash
set -e

# ── Initialise workspace folder structure ─────────────────────────────────────
mkdir -p /workspace/upload
mkdir -p /workspace/investigations
mkdir -p /workspace/config
mkdir -p /workspace/.agents/skills

# ── Seed default branding if not present ──────────────────────────────────────
if [ ! -f /workspace/config/branding.json ]; then
  cp /app/app/defaults/branding.json /workspace/config/branding.json
fi

# ── Start API ─────────────────────────────────────────────────────────────────
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
