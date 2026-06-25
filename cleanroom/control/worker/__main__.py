"""Run the dispatch worker as a process: `python -m cleanroom.control.worker`.

Wires the same backends the MCP server uses (cleanroom.control.server.wiring), so the
worker shares the Aiven run store + governance log with the web tier. Intended to run
as its own container/ECS service alongside the web tier (see docs/deploy-aws.md).
"""

import os
import signal
import threading

from cleanroom.control.server.wiring import (
    assert_serving_safe,
    make_dispatch_ctx,
    make_logclient,
    make_operator,
)
from cleanroom.control.worker import run_worker


def main() -> int:
    # Same truth-boundary guard as the web tier: never run as a Postgres superuser.
    assert_serving_safe()
    operator = make_operator()
    stop = threading.Event()

    def _handle(_signum, _frame):
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle)
        except (ValueError, OSError):  # e.g. not in main thread on some platforms
            pass

    poll = float(os.environ.get("CLEANROOM_WORKER_POLL_SECONDS", "1.0"))
    print(f"[worker] polling for queued runs every {poll}s (Ctrl-C to stop)")
    run_worker(
        run_store=operator.run_store,
        registry=operator.registry,
        ctx_factory=lambda: make_dispatch_ctx(make_logclient()),
        poll_interval=poll,
        stop=stop,
    )
    print("[worker] stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
