# Homeserver Deployment Guide — SunsteadHack
# ===========================================
#
# This document describes the deployment topology for the SunsteadHack
# webhook receiver on a homeserver, modeled on the geo-helsinki-solar
# deployment pattern.

## Topology Overview

```
Internet
   │
   ▼
Cloudflare Tunnel (webhooks.ease-health.org)
   │  (token-based dashboard-managed tunnel)
   │
   ▼
sunstead-webhook.service
   │  (Python stdlib HTTPServer on 127.0.0.1:8787)
   │
   ▼
cells/agent-escalation-log/inbox/
   │  (raw JSON webhook envelopes, Stage 0)
   │
   ▼
Tangled workflow (polling or external trigger)
```

### Components

| Component | Type | Purpose |
|-----------|------|---------|
| `sunstead-webhook.service` | systemd unit | Runs the webhook receiver |
| `sunstead-healthcheck.timer` | systemd timer | Fires healthcheck every 15 min |
| `sunstead-healthcheck.service` | systemd oneshot | Probes `/healthz`, self-heals |
| Cloudflare Tunnel | Cloudflare Access | Public ingress `webhooks.ease-health.org` |
| Bare repo | `/home/server/git/sunsteadhack.git` | Receives git pushes |
| Working tree | `/home/server/sunsteadhack` | Deployed code |

### Push-to-Deploy Flow

1. Developer pushes to `main` on the bare repo:
   ```bash
   git push /home/server/git/sunsteadhack.git main
   ```
2. The `post-receive` hook checks out the pushed branch to the working tree.
3. The hook runs `scripts/deploy.sh` which:
   - Validates Python syntax (`py_compile`)
   - Runs `stage_membrane_unit.py` smoke check
   - Reloads and restarts `sunstead-webhook.service` via systemd

### Webhook Receiver

The receiver (`scripts/tangled_webhook_receiver.py`) is a minimal Python stdlib
HTTP server that:

- `GET /healthz` → `200 {"ok": true}` — liveness probe
- `POST /webhooks/tangled` → verifies HMAC-SHA256 if `TANGLED_WEBHOOK_SECRET` is set,
  writes the raw envelope to `cells/agent-escalation-log/inbox/`, returns `200 {"ok": true}`

Envelope filename format: `YYYYMMDDTHHMMSSZ-<delivery>-push.json`

Where `<delivery>` is:
- `X-Tangled-Delivery` header value if present
- First 12 chars of the `after` field in the payload if present
- Random 12-char hex suffix

Envelope schema:
```json
{
  "received_at": "2026-06-23T12:00:00+00:00",
  "remote_addr": "203.0.113.50",
  "headers": { "X-Tangled-Delivery": "...", "X-Tangled-Event": "..." },
  "payload": { /* raw Tangled push payload */ }
}
```

## Homeserver Install Commands

Run these on the homeserver as a one-time setup:

```bash
# ── 1. Create deployment user and directories ────────────────────────────────
sudo useradd -r -s /bin/bash server || true
sudo mkdir -p /home/server/sunsteadhack
sudo mkdir -p /home/server/git
sudo chown server:server /home/server/sunsteadhack /home/server/git

# ── 2. Clone/create bare repo ────────────────────────────────────────────────
# If starting fresh:
git clone --bare <your-repo-url> /home/server/git/sunsteadhack.git
sudo chown -R server:server /home/server/git/sunsteadhack.git

# ── 3. Install post-receive hook ─────────────────────────────────────────────
sudo -u server tee /home/server/git/sunsteadhack.git/hooks/post-receive <<'HOOK'
#!/bin/bash
WORK_TREE="/home/server/sunsteadhack"
GIT_DIR="/home/server/git/sunsteadhack.git"
DEPLOY_BRANCH="main"

while read -r oldrev newrev refname; do
    branch="${refname#refs/heads/}"
    git --work-tree="$WORK_TREE" --git-dir="$GIT_DIR" checkout -f "$branch"
    if [ "$branch" = "$DEPLOY_BRANCH" ]; then
        cd "$WORK_TREE" || exit 1
        PROJECT_DIR="$WORK_TREE" bash "$WORK_TREE/scripts/deploy.sh"
    fi
done
HOOK
sudo chmod +x /home/server/git/sunsteadhack.git/hooks/post-receive

# ── 4. Clone working tree ────────────────────────────────────────────────────
sudo -u server git clone /home/server/git/sunsteadhack.git /home/server/sunsteadhack
cd /home/server/sunsteadhack

# ── 5. Install systemd units ──────────────────────────────────────────────────
sudo cp deploy/sunstead-webhook.service /etc/systemd/system/
sudo cp deploy/sunstead-healthcheck.service /etc/systemd/system/
sudo cp deploy/sunstead-healthcheck.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sunstead-webhook.service
sudo systemctl enable --now sunstead-healthcheck.timer

# ── 6. Cloudflare Tunnel ─────────────────────────────────────────────────────
# Option A — Token-based (managed in dashboard):
#   1. In Cloudflare dashboard → Access → Tunnels → Create a tunnel
#   2. Choose "Cloudflared" as the connector type
#   3. Save the tunnel token
#   4. On the server, create /etc/cloudflared/config.yml:
#      tunnel: YOUR_TOKEN_HERE
#      protocol: http2
#   5. sudo systemctl enable --now cloudflared
#   6. In dashboard, set public hostname: webhooks.ease-health.org → localhost:8787

# Option B — Named tunnel (traditional):
#   1. cloudflared tunnel login
#   2. cloudflared tunnel create sunstead-webhook
#   3. Copy deploy/cloudflared-config.yml to /etc/cloudflared/config.yml
#   4. Fill in the Tunnel UUID and credentials path
#   5. In Cloudflare dashboard → DNS: CNAME webhooks.ease-health.org → <uuid>.cfargotunnel.com
#   6. sudo systemctl enable --now cloudflared

# ── 7. Create .env for receiver settings/secrets ────────────────────────────
# Use the same secret in Tangled's webhook UI. If you leave this secret blank,
# requests are accepted unsigned; that is okay for a first smoke test only.
sudo -u server tee /home/server/sunsteadhack/.env >/dev/null <<'ENV'
TANGLED_WEBHOOK_SECRET=replace_with_tangled_webhook_secret
TANGLED_WEBHOOK_HOST=127.0.0.1
TANGLED_WEBHOOK_PORT=8787
TANGLED_WEBHOOK_INBOX=/home/server/sunsteadhack/cells/agent-escalation-log/inbox
TANGLED_WEBHOOK_MAX_BYTES=10485760
ENV
sudo chmod 600 /home/server/sunsteadhack/.env

# ── 8. Test webhook receiver ─────────────────────────────────────────────────
curl http://127.0.0.1:8787/healthz
# Expected: {"ok": true}

# ── 9. Trigger a test push ───────────────────────────────────────────────────
git push /home/server/git/sunsteadhack.git main
```

## Tangled UI Configuration

In the Tangled UI, configure a Tangled push webhook:

1. Go to your workflow configuration.
2. Add a webhook receiver pointing to:
   ```
   https://webhooks.ease-health.org/webhooks/tangled
   ```
3. If HMAC verification is enabled in `.env`:
   - Set the secret to match `TANGLED_WEBHOOK_SECRET`
   - Tangled will sign requests with `X-Tangled-Signature-256: sha256=<hex>`
4. Delivery ID is passed via `X-Tangled-Delivery` header.

## Service Management

```bash
# View logs
sudo journalctl -u sunstead-webhook.service -f
sudo journalctl -u sunstead-healthcheck.service -f

# Manual restart
sudo systemctl restart sunstead-webhook.service

# Check status
sudo systemctl status sunstead-webhook.service

# Disable healthcheck timer (if needed)
sudo systemctl stop sunstead-healthcheck.timer
sudo systemctl disable sunstead-healthcheck.timer
```

## Comparison with geo-helsinki-solar

| Aspect | geo | sunsteadhack |
|--------|-----|--------------|
| Deployed code | `/home/server/geo-infra` | `/home/server/sunsteadhack` |
| Bare repo | `/home/server/git/geo-infra.git` | `/home/server/git/sunsteadhack.git` |
| Deploy branch | `master` | `main` |
| Service | `geo-controlbot.service` + others | `sunstead-webhook.service` |
| Healthcheck | 4-probe self-healing | single-probe self-healing |
| Tunnel | Named tunnel via config.yml | Token-based (dashboard) |
| Public URL | `crm.ease-health.org` | `webhooks.ease-health.org` |
| Database | PostgreSQL + Docker | None (file-based inbox) |
| Deploy steps | uv sync + migrations + blue-green | py_compile + smoke + systemctl restart |
