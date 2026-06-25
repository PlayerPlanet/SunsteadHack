"""Agent self-improvement domain (Issue #43 — Tier B flywheel).

Exports the four adapters for the optimization loop:
  - AgentBenchmark: Maps agent quality to p99_ms (lower=better).
  - CodeActions: Applies/rolls back source edits via snapshot stack.
  - AgentPore: Gates out-of-scope or frozen-boundary-touching edits.
  - CuratedSourceProposer: Tier-B stable proposer (curated threshold steps).

The loop iterates: propose → gate (pore) → apply (actions) → benchmark.
"""

from .benchmark import AgentBenchmark
from .actions import CodeActions
from .pore import AgentPore
from .proposer import CuratedSourceProposer

__all__ = ["AgentBenchmark", "CodeActions", "AgentPore", "CuratedSourceProposer"]
