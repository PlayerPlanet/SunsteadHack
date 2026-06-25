#!/usr/bin/env bash
# Vendor the `cleanroom` package into the AgentCore CodeZip bundle.
#
# CodeZip only zips the runtime's codeLocation (sunsteadcontrol/app/sunstead_control/),
# so our multi-module package must be copied in beside main.py before `agentcore deploy`.
# The copy is gitignored (regenerated each deploy) — the repo keeps a single source of
# truth in ./cleanroom. Run from anywhere:
#
#   bash scripts/vendor_for_agentcore.sh && (cd sunsteadcontrol && agentcore deploy)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/sunsteadcontrol/app/sunstead_control/cleanroom"

rm -rf "$DEST"
cp -r "$ROOT/cleanroom" "$DEST"
find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
echo "vendored cleanroom -> $DEST"
