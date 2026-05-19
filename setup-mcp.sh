#!/bin/bash
# CyberHawk MCP Setup — points Claude Code at your running Docker stack
# Usage: ./setup-mcp.sh <server-ip>
# Example: ./setup-mcp.sh 192.168.1.100

set -e

SERVER_IP="${1:-localhost}"
SETTINGS_FILE=".claude/settings.json"

mkdir -p .claude

cat > "$SETTINGS_FILE" <<EOF
{
  "mcpServers": {
    "cyberhawk": {
      "type": "sse",
      "url": "http://${SERVER_IP}:3002/sse"
    }
  }
}
EOF

echo "✓ MCP configured → http://${SERVER_IP}:3002/sse"
echo "  Restart Claude Code, then type /mcp to verify the cyberhawk server is connected."
