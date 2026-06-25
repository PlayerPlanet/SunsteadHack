"""AgentCore Runtime entrypoint for the SunsteadHack control plane.

Delegates to the cleanroom control-plane server, which serves streamable-HTTP MCP at
0.0.0.0:8000/mcp (stateless) with the AgentCore identity middleware (per-tool scope
from the platform-validated token) and connects to Aiven as the non-superuser
sunstead_app role. The `cleanroom` package is vendored beside this file at deploy time
(scripts/vendor_for_agentcore.sh) so it travels in the CodeZip bundle.
"""

from cleanroom.control.server.runtime_mcp import main

if __name__ == "__main__":
    raise SystemExit(main())
