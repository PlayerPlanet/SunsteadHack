"""Stationarity tripwire — the frozen `authority ∝ stationarity` PROXY (Story F, #16).

WHAT THIS IS
------------
A composable pore that adds exactly ONE fixed rule on top of the base frozen gate:

    escalate if drift_level > T          (T is a hardcoded constant, default 0.5)

This is the shippable, crude proxy for the manifesto's "authority is proportional to
stationarity": below the line the agent has earned trust and acts; above it, it has
left the region it can stand behind and must ask. It exists so the spatial boundary
curve (escalation rate vs drift) RISES — the base pore is drift-blind, so without a
drift-coupled rule the curve is flat no matter how far the world moves.

WHY IT IS A SEPARATE MODULE (load-bearing)
------------------------------------------
It does NOT modify `cleanroom.pore.evaluate`. The base gate stays drift-blind on
purpose: the deep probe (cleanroom/probe) measures the EMERGENT escalation signal —
drift forcing riskier proposals that trip the unchanged gate — and that reading is
only clean while the base pore cannot see drift. So this tripwire wraps the base gate
for the Story-F demo sweep instead of contaminating it. Two honest instruments:
  * base pore + deep probe  -> emergent edge (graded, proposer-driven)
  * base pore + this wrapper -> the reliable thresholded proxy curve (#16)

FROZEN. T is a constructor constant, never learned or tuned per-run. A self-tuning
threshold would reintroduce the runaway-threshold failure that issue #4's benchmark
exists to detect — you could no longer tell "the world drifted" from "the gate moved".
Always label the resulting curve a PROXY / lower bound, not the calibrated OOD membrane
(that is the deferred Stage-2 bet).
"""

from cleanroom import pore as _base_pore
from cleanroom.types import Candidate, PoreResult

# The frozen stationarity threshold. A CONSTANT — do not learn, tune, or adapt it.
DEFAULT_THRESHOLD = 0.5


class StationarityProxyPore:
    """Frozen drift tripwire composed over the base gate.

    One sweep run is one drift level, so the drift is bound at construction and the
    `evaluate(candidate)` contract stays identical to the base pore (run_loop passes
    only the candidate). Above the threshold every candidate escalates (the agent has
    left its trusted region); at or below it, the base drift-blind gate decides.

    Args:
        drift_level: The stationarity distance for this run, in [0, 1].
        threshold: The frozen constant T. Default 0.5. NOT tunable per-run by design.
        base: The base pore module/object (defaults to the frozen cleanroom.pore).
    """

    def __init__(self, *, drift_level: float, threshold: float = DEFAULT_THRESHOLD, base=_base_pore):
        self.drift_level = float(drift_level)
        self.threshold = float(threshold)
        self._base = base

    def evaluate(self, candidate: Candidate) -> PoreResult:
        if self.drift_level > self.threshold:
            return PoreResult(
                pore="stationarity_proxy",
                risk_level="high",
                requires_human_judgment=True,
                decision="escalate",
            )
        # Inside the trusted region: defer entirely to the base drift-blind gate.
        return self._base.evaluate(candidate)
