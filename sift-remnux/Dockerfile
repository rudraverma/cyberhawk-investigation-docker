# ── CyberHawk REMnux — Malware Analysis + RE MCP ─────────────────────────────
# Base: official REMnux distro (Ubuntu 24.04 noble)
# Includes: Ghidra, capa, FLOSS, Speakeasy, radare2, Volatility3, apktool,
#           jadx, YARA, binwalk, exiftool, pefile, and 100+ more RE tools.
#
# MCP server on port 3004 (streamable-http) — Claude Code connects here.
# Shared volume: cyberhawk-data → /workspace (same as all other containers)
#
# Build: docker compose build sift-remnux
# Start: docker compose up -d sift-remnux

FROM remnux/remnux-distro:noble

LABEL maintainer="CyberHawk Consultancy"
LABEL role="remnux-mcp"
LABEL description="REMnux malware analysis suite with FastMCP bridge for Claude Code"

ENV DEBIAN_FRONTEND=noninteractive
ENV REMNUX_MCP_PORT=3004

# ── Install FastMCP + pefile in isolated venv (avoids debian package conflicts)
RUN python3 -m venv /opt/remnux-venv && \
    /opt/remnux-venv/bin/pip install --no-cache-dir \
    "mcp[cli]>=1.2.0" \
    "pefile>=2023.2.7"

# ── Copy MCP server ───────────────────────────────────────────────────────────
RUN mkdir -p /app
COPY remnux_mcp.py /app/remnux_mcp.py

# ── Workspace ─────────────────────────────────────────────────────────────────
RUN mkdir -p /workspace
WORKDIR /workspace

EXPOSE 3004

CMD ["/opt/remnux-venv/bin/python3", "/app/remnux_mcp.py"]
