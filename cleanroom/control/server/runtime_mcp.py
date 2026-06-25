"""AgentCore Runtime entrypoint for the control-plane MCP server.

AgentCore expects an MCP container serving streamable-HTTP at 0.0.0.0:8000/mcp; this
is that process. Inbound OAuth is handled by AgentCore at the edge (configured at
`agentcore create`); this entrypoint just serves the tools, with a thin identity hint
for per-tool scope (see runtime_app). It connects to Aiven as the non-superuser
sunstead_app login (CLEANROOM_PG_APP_DSN) — the truth-boundary backstop.

Local:   python -m cleanroom.control.server.runtime_mcp   (then hit http://localhost:8000/mcp)
Deployed: `agentcore deploy` packages this and hosts it on AgentCore Runtime.
"""

import os


def main() -> int:
    import uvicorn

    from cleanroom.control.server.runtime_app import build_runtime_app
    from cleanroom.control.server.wiring import assert_serving_safe

    # Truth-boundary guard: refuse to serve as a Postgres superuser.
    assert_serving_safe()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    app = build_runtime_app(host=host, port=port)
    uvicorn.run(app, host=host, port=port, log_level=os.environ.get("LOG_LEVEL", "info"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
