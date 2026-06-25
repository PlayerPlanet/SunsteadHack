"""Agent proposer — Tier-B risk mitigation via curated threshold edits.

DESIGN (Issue #43 — Tier B stability demo):
This proposer walks the THRESHOLD down from 0.95 (high false-clear risk) toward
the proven optimum (0.65) in deterministic steps. Each step is a known-good edit
that reduces the objective monotonically. This guarantees a clean bend curve for
the demo.

PRODUCTION NOTE: A real ClaudeCodeProposer would invoke an LLM to generate
source edits. The curated pool is the stable stand-in for the hackathon.
"""

from cleanroom.types import Candidate


# Proven optimal threshold (from _probe_agent_benchmark.py).
OPTIMUM = 0.65

# Curated descent path: strictly-decreasing thresholds leading to optimum.
# From the probe output: baseline 0.95→0.500, 0.80→0.468, 0.65→0.412 (best).
# The path does NOT include 0.95 (baseline) so iteration 1 is a real step.
DESCENT_PATH = [0.80, 0.65]


class CuratedSourceProposer:
    """Proposes threshold edits in a deterministic descent.

    For Tier B demo stability, this walks through a curated pool of thresholds
    that are proven to reduce the objective. After reaching the optimum, it
    proposes a no-op or a deliberately-bad edit to show the loop discards
    regressions.

    PRODUCTION SWAP: Replace this with an LLM-driven proposer that generates
    arbitrary source edits and relies on the pore + benchmark feedback to
    steer the search.
    """

    def __init__(self):
        """Initialize the proposer."""
        self.step = 0  # Index into DESCENT_PATH.
        self.history = []  # Accepted candidates so far.

    def propose(self, task_spec: dict, history: list) -> Candidate:
        """Propose the next threshold edit.

        Args:
            task_spec: Task specification (unused in this implementation).
            history: List of accepted Candidates so far.

        Returns:
            Candidate with type="source_edit" and params containing the
            new threshold or a regression test.
        """
        self.history = history

        if self.step < len(DESCENT_PATH):
            # Propose the next curated threshold.
            next_threshold = DESCENT_PATH[self.step]
            self.step += 1

            return Candidate(
                type="source_edit",
                params={"threshold": next_threshold},
                reversible=True,
            )
        else:
            # Past the optimum: test regressions by proposing worse thresholds.
            # Alternate between slightly worse proposals to demonstrate the loop
            # rejects regressions.
            bad_thresholds = [0.95, 0.80, 0.95, 0.80]
            idx = (self.step - len(DESCENT_PATH)) % len(bad_thresholds)
            self.step += 1
            bad_threshold = bad_thresholds[idx]

            return Candidate(
                type="source_edit",
                params={"threshold": bad_threshold},
                reversible=True,
            )
