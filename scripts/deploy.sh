#!/bin/bash
# deploy.sh — SunsteadHack homeserver deployment
# -----------------------------------------------
# Push-to-deploy entry point for the homeserver.
# Runs on every push to main via the post-receive hook.
#
# Smoke checks:
#   - Syntax validation of Python scripts
#   - stage_membrane_unit.py --output /tmp/sunsteadhack-staged-unit.json
#
# Then reloads/restarts the webhook service via systemd (if sudo available).
# Never fails on sudo errors — warns only.

set -uo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/server/sunsteadhack}"
cd "$PROJECT_DIR" || { echo "FATAL: $PROJECT_DIR missing"; exit 1; }

# ── Current revision ──────────────────────────────────────────────────────────
CURRENT_REV="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
PREV_REV="$(git rev-parse --short HEAD@{1} 2>/dev/null || echo "$CURRENT_REV")"
echo "=== Deploy $CURRENT_REV (prev: $PREV_REV) ==="

# ── Smoke checks ─────────────────────────────────────────────────────────────
echo "[1/3] Smoke: py_compile all scripts..."
for script in scripts/*.py; do
    if [ -f "$script" ]; then
        python3 -m py_compile "$script" 2>&1 || {
            echo "FAIL: py_compile $script failed"
            exit 1
        }
        echo "      OK: $script"
    fi
done

echo "[2/3] Smoke: stage_membrane_unit..."
python3 scripts/stage_membrane_unit.py \
    --output /tmp/sunsteadhack-staged-unit.json 2>&1 || {
    echo "FAIL: stage_membrane_unit smoke failed"
    exit 1
}
echo "      OK: stage_membrane_unit"

echo "[3/3] Restarting webhook service..."
if command -v systemctl >/dev/null 2>&1; then
    # daemon-reload if unit files changed
    sudo systemctl daemon-reload 2>/dev/null || true
    if sudo systemctl restart sunstead-webhook.service 2>/dev/null; then
        echo "      OK: sunstead-webhook.service restarted"
    else
        # systemctl may fail if service doesn't exist yet (first deploy)
        echo "WARN: could not restart sunstead-webhook.service (may not be installed yet)"
        echo "      Install with: sudo cp deploy/sunstead-webhook.service /etc/systemd/system/"
        echo "      Then: sudo systemctl daemon-reload && sudo systemctl enable --now sunstead-webhook.service"
    fi
else
    echo "WARN: systemctl not available — skipping service restart"
fi

echo "=== Deploy $CURRENT_REV complete ==="
exit 0
