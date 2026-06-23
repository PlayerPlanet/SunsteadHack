#!/bin/bash
# healthcheck.sh — SunsteadHack self-healing probe
# ──────────────────────────────────────────────────
# Probes http://127.0.0.1:8787/healthz
# If failing: attempts sudo systemctl restart sunstead-webhook.service
# Wait and re-probe. Exit 0 if healthy/self-healed, 1 otherwise.
#
# Driven by sunstead-healthcheck.timer every 15 minutes.

set -uo pipefail

HOST="${TANGLED_WEBHOOK_HOST:-127.0.0.1}"
PORT="${TANGLED_WEBHOOK_PORT:-8787}"
HEALTH_URL="http://${HOST}:${PORT}/healthz"
SERVICE="sunstead-webhook.service"
MAX_WAIT=30

now() { date +%s; }

echo "[healthcheck] Probing $HEALTH_URL ..."

if curl -sf -m 10 -o /dev/null "$HEALTH_URL" 2>/dev/null; then
    echo "[healthcheck] OK: webhook receiver is healthy"
    exit 0
fi

echo "[healthcheck] DOWN: attempting self-heal ..."

# Attempt restart if sudo available
if command -v systemctl >/dev/null 2>&1; then
    if sudo systemctl restart "$SERVICE" 2>/dev/null; then
        echo "[healthcheck] Restart issued — waiting up to ${MAX_WAIT}s for recovery..."
    else
        echo "[healthcheck] WARN: could not restart $SERVICE (sudo may require password)"
    fi
else
    echo "[healthcheck] WARN: systemctl not available"
fi

# Re-probe with backoff
deadline=$(( $(now) + MAX_WAIT ))
while [ "$(now)" -lt "$deadline" ]; do
    sleep 5
    if curl -sf -m 10 -o /dev/null "$HEALTH_URL" 2>/dev/null; then
        echo "[healthcheck] HEALED: webhook receiver recovered after restart"
        exit 0
    fi
done

echo "[healthcheck] FAILED: webhook receiver did not recover within ${MAX_WAIT}s"
exit 1
