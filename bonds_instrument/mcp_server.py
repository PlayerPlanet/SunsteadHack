"""MCP server exposing the input-driven benchmark as a single tool.

Lazy-imports `mcp` (like `cleanroom.control.server.mcp`) so this module imports
without the dependency present; the plugin's `.mcp.json` launches it where `mcp`
is installed. The tool takes the two INPUTS — materials + candidate agent — and
returns the candidate's trustworthy-region scorecard. The judge stays frozen and
non-agentic (issue #28): this server never grades with a model.
"""

from __future__ import annotations

from .runner import run_benchmark


def tool_benchmark_agent(agent_import: str, materials_path: str = "",
                         use_llm: bool = False) -> dict:
    """Benchmark a candidate agent against bond materials -> trustworthy-region scorecard.

    Args:
        agent_import: "module.path:Attr" exposing `review(view) -> Decision` and a
            `name` (the BYO-agent contract). Reference adapter for the Arctal
            take-home agent: "bonds_instrument.candidates:DQAgentCandidate".
        materials_path: directory of bond CSVs (issuances/cat/geo/impacts). Empty
            string = the bundled sample.
        use_llm: enable the candidate's LLM tier if it has one (needs ANTHROPIC_API_KEY).

    Returns:
        Scorecard dict: region (trustworthy ceiling), overall false-clear / over-ask /
        justified-ask, the per-drift-bin curve, and the planted-error composition.
    """
    return run_benchmark(materials_path or None, agent_import, use_llm=use_llm)


def build_server():
    """Build the FastMCP server. Lazy-imports mcp so the module imports without it."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:
        raise ImportError("mcp library not found. Install it with: pip install mcp") from e

    server = FastMCP(
        name="sunstead-bench",
        instructions="Benchmark a candidate agent's trustworthy region against materials. "
                     "The judge is frozen and non-agentic (re-derivation + planted labels, "
                     "issue #28) — never score with a model; the interpretive layer is human "
                     "territory and is not measured.",
    )
    server.add_tool(
        tool_benchmark_agent, name="benchmark_agent",
        description="Benchmark a candidate agent (module:Attr) against bond materials; "
                    "returns its trustworthy-region scorecard.",
    )
    return server


def main():
    build_server().run()


if __name__ == "__main__":
    main()
