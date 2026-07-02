#!/bin/bash
# CyberHawk GhidraMCP — bethington headless entrypoint
# No GUI, no Xvfb, no plugin activation.
# Starts the Java headless server then the Python MCP bridge.
set -e

GHIDRA_MCP_PORT="${GHIDRA_MCP_PORT:-8089}"
MCP_BRIDGE_PORT="${MCP_BRIDGE_PORT:-8081}"
JAVA_OPTS="${JAVA_OPTS:--Xmx4g -XX:+UseG1GC}"

echo "[GhidraMCP] ── Building classpath ──────────────────────────────────────"
CLASSPATH="/app/GhidraMCP.jar"
for jar in "${GHIDRA_HOME}"/Ghidra/Framework/*/lib/*.jar; do CLASSPATH="${CLASSPATH}:${jar}"; done
for jar in "${GHIDRA_HOME}"/Ghidra/Features/*/lib/*.jar;  do CLASSPATH="${CLASSPATH}:${jar}"; done
for jar in "${GHIDRA_HOME}"/Ghidra/Processors/*/lib/*.jar; do CLASSPATH="${CLASSPATH}:${jar}"; done
for jar in "${GHIDRA_HOME}"/Ghidra/Debug/*/lib/*.jar;     do CLASSPATH="${CLASSPATH}:${jar}"; done

echo "[GhidraMCP] ── Starting Ghidra headless server on :${GHIDRA_MCP_PORT} ─"
java ${JAVA_OPTS} \
    -Dghidra.home="${GHIDRA_HOME}" \
    -Dapplication.name=GhidraMCP \
    -classpath "${CLASSPATH}" \
    com.xebyte.headless.GhidraMCPHeadlessServer \
    --port "${GHIDRA_MCP_PORT}" \
    --bind 127.0.0.1 \
    --data /data \
    --projects /workspace/ghidra-projects &

echo "[GhidraMCP] ── Waiting for headless server ─────────────────────────────"
READY=0
for i in $(seq 1 40); do
    if curl -sf "http://127.0.0.1:${GHIDRA_MCP_PORT}/check_connection" >/dev/null 2>&1; then
        READY=1
        echo "[GhidraMCP] Headless server UP after $((i*3))s ✓"
        break
    fi
    echo "[GhidraMCP]  ... attempt $i/40 ($((i*3))s elapsed)"
    sleep 3
done

if [ "$READY" -ne 1 ]; then
    echo "[GhidraMCP] WARNING: headless server did not respond in 120s"
    echo "[GhidraMCP] Bridge starting anyway — will retry on each tool call"
fi

echo "[GhidraMCP] ── Starting MCP bridge on :${MCP_BRIDGE_PORT} ─────────────"
exec python3 /app/bridge_mcp_ghidra.py \
    --transport streamable-http \
    --mcp-host 0.0.0.0 \
    --mcp-port "${MCP_BRIDGE_PORT}"
