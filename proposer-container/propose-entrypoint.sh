#!/bin/bash
# Claude Code researcher entrypoint for Story A proposer.
# Reads TASK and MODEL from environment, invokes claude headless with read-only
# Postgres MCP, and prints raw JSON output for the Python wrapper to parse.
#
# DESIGN:
# - claude is invoked with a whitelist of allowed tools (only mcp__pg__query)
# - Bash, Write, Edit, WebFetch are explicitly disallowed to enforce read-only
# - The system prompt instructs the model to propose exactly one index
# - Output is raw JSON for direct parsing by the wrapper
#
# NOTE: We do NOT use --permission-mode bypassPermissions because that would
# defeat the read-only enforcement. Instead, we rely on the tool whitelist
# and the frozen permission model to keep the container truly read-only.

set -e

TASK="${TASK:-}"
MODEL="${MODEL:-claude-haiku-4-5-20251001}"

if [ -z "$TASK" ]; then
    echo '{"error":"TASK environment variable not set"}'
    exit 1
fi

# ---- MCP Config Regeneration (Cloud Support) --------
# If DB_DSN is set (from AWS Secrets Manager / cloud deployment), regenerate the MCP config
# to point to the real database instead of host.docker.internal (which doesn't exist on Fargate).
# Otherwise, fall back to the bundled config for local docker run.

MCP_CONFIG_PATH="/etc/readonly-pg.mcp.json"

if [ -n "${DB_DSN:-}" ]; then
    # Cloud deployment: regenerate MCP config from DB_DSN
    cat > "$MCP_CONFIG_PATH" <<EOF
{
  "mcpServers": {
    "pg": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-postgres",
        "$DB_DSN"
      ]
    }
  }
}
EOF
    echo "[proposer] Using cloud DB_DSN for MCP config" >&2
else
    # Local deployment: use bundled config (host.docker.internal:55432)
    echo "[proposer] Using local host.docker.internal for MCP config" >&2
fi

# System prompt instructs the model to propose exactly ONE index and return raw JSON.
SYSTEM_PROMPT="You are a Postgres performance researcher. Use ONLY the pg query tool (read-only) to inspect the schema, table sizes, and pg_stat_statements. Propose exactly ONE index to speed up the stated workload. Your FINAL message must be ONLY a raw JSON object and nothing else: {\"type\":\"index\",\"params\":{\"table\":\"<table>\",\"columns\":[\"<col>\",...]},\"reversible\":true}. Do not apply or benchmark anything; you cannot — you only propose."

# Invoke claude headless with:
# - MCP config pointing to the read-only Postgres server
# - Whitelist: only mcp__pg__query is allowed
# - Blacklist: Bash, Write, Edit, WebFetch are explicitly forbidden
# - Output format: json (structured, machine-parseable)
# - Append the system prompt
# Note: claude --output-format json will wrap the result in a JSON envelope with
# a "result" field containing the model's final output as a string.
claude \
  -p "$TASK" \
  --output-format json \
  --model "$MODEL" \
  --mcp-config "$MCP_CONFIG_PATH" \
  --allowedTools "mcp__pg__query" \
  --disallowedTools "Bash" "Write" "Edit" "WebFetch" \
  --append-system-prompt "$SYSTEM_PROMPT"
