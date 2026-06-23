#!/usr/bin/env python3
"""
tangled_webhook_receiver.py

Minimal Tangled webhook receiver using only Python stdlib.
Accepts Tangled push webhooks, verifies optional HMAC signature,
writes raw events to Stage 0 inbox, and returns 2xx quickly.

Usage:
    python scripts/tangled_webhook_receiver.py [--host HOST] [--port PORT]
        [--inbox INBOX] [--secret SECRET]

Environment variables:
    TANGLED_WEBHOOK_HOST    default: 127.0.0.1
    TANGLED_WEBHOOK_PORT    default: 8787
    TANGLED_WEBHOOK_INBOX   default: cells/agent-escalation-log/inbox
    TANGLED_WEBHOOK_SECRET  optional, enables HMAC verification
    TANGLED_WEBHOOK_MAX_BYTES default: 10485760 (10 MiB)
"""

import argparse
import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler


def _parse_args():
    parser = argparse.ArgumentParser(description="Tangled webhook receiver")
    parser.add_argument("--host", default=os.environ.get("TANGLED_WEBHOOK_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("TANGLED_WEBHOOK_PORT", "8787")))
    parser.add_argument("--inbox", default=os.environ.get("TANGLED_WEBHOOK_INBOX", "cells/agent-escalation-log/inbox"))
    parser.add_argument("--secret", default=os.environ.get("TANGLED_WEBHOOK_SECRET", ""))
    parser.add_argument("--max-bytes", type=int, default=int(os.environ.get("TANGLED_WEBHOOK_MAX_BYTES", "10485760")))
    return parser.parse_args()


class WebhookHandler(BaseHTTPRequestHandler):
    receiver = None  # class-level ref to pass config
    health_paths = ("/", "/healthz", "/webhooks/tangled")

    def log_message(self, format, *args):
        # Suppress default stderr noise; errors go to stderr via server
        pass

    def send_json(self, status: int, data: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_GET(self):
        if self.path in self.health_paths:
            self.send_json(200, {"ok": True, "service": "sunstead-tangled-webhook"})
        else:
            self.send_json(404, {"error": "not found"})

    def do_HEAD(self):
        if self.path in self.health_paths:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != "/webhooks/tangled":
            self.send_json(404, {"error": "not found"})
            return

        # Read raw body immediately so subclasses can verify signature
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > self.receiver.max_bytes:
            self.send_json(413, {"error": "payload too large"})
            return
        raw_body = self.rfile.read(content_length) if content_length > 0 else b""

        # Optional HMAC verification
        secret = self.receiver.secret
        if secret:
            sig_header = self.headers.get("X-Tangled-Signature-256", "")
            expected = "sha256=" + hmac.new(
                secret.encode("utf-8"), raw_body, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(sig_header, expected):
                self.send_json(401, {"error": "invalid signature"})
                return

        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except Exception:
            self.send_json(400, {"error": "invalid json payload"})
            return

        # Parse delivery ID from header or derive
        delivery = self.headers.get("X-Tangled-Delivery", "")
        if delivery:
            # Sanitize delivery ID (alphanumeric, dash, underscore only)
            delivery = re.sub(r"[^a-zA-Z0-9_-]", "_", delivery)[:48]
        else:
            # Try to find "after" field in payload for meaningful suffix
            after = payload.get("after", "")
            if after:
                delivery = after[:12]
            else:
                delivery = uuid.uuid4().hex[:12]

        # Build timestamped filename
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{timestamp}-{delivery}-push.json"

        # Capture metadata envelope
        received_at = datetime.now(timezone.utc).isoformat()
        remote_addr = self.client_address[0] or "unknown"

        # Capture relevant headers (subset, no secrets)
        captured_headers = {}
        for key in ["X-Tangled-Delivery", "X-Tangled-Signature-256",
                    "X-Tangled-Event", "X-Tangled-Host",
                    "Content-Type", "User-Agent"]:
            val = self.headers.get(key)
            if val:
                captured_headers[key] = val

        envelope = {
            "received_at": received_at,
            "remote_addr": remote_addr,
            "headers": captured_headers,
            "payload": payload,
        }

        # Write to inbox
        inbox_dir = os.path.abspath(self.receiver.inbox)
        os.makedirs(inbox_dir, exist_ok=True)
        inbox_path = os.path.join(inbox_dir, filename)

        try:
            with open(inbox_path, "w", encoding="utf-8") as f:
                json.dump(envelope, f, indent=2)
        except Exception as e:
            self.send_json(500, {"error": f"failed to write inbox: {e}"})
            return

        self.send_json(200, {"ok": True, "delivery": delivery, "file": filename})


def main():
    args = _parse_args()
    WebhookHandler.receiver = args

    # Ensure inbox dir exists relative to CWD
    os.makedirs(args.inbox, exist_ok=True)

    server = HTTPServer((args.host, args.port), WebhookHandler)
    print(f"[tangled_webhook_receiver] listening on {args.host}:{args.port}")
    print(f"[tangled_webhook_receiver] inbox: {os.path.abspath(args.inbox)}")
    if args.secret:
        print(f"[tangled_webhook_receiver] HMAC verification ENABLED")
    else:
        print(f"[tangled_webhook_receiver] HMAC verification DISABLED (no secret)")
    print(f"[tangled_webhook_receiver] max payload bytes: {args.max_bytes}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[tangled_webhook_receiver] shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
