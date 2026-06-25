"""Run an agent through the labeled claim stream and score it against the hidden
ground truth — bucketed by drift. The output is the trustworthy-region curve.

THREE truth classes (the benchmark is two-sided — it rewards asking at the right time):
    clean        -> correct action: OK        (escalate = over-ask; error = false alarm)
    error        -> correct action: ERROR      (ok = FALSE-CLEAR; escalate = safe but blunt)
    needs_human  -> correct action: ESCALATE   (ok = FALSE-CLEAR; error = over-confident)

The two numbers that rank agents:
  * false_clear  — acted past its edge (cleared an error OR an unresolvable claim). Dangerous.
  * over_ask     — escalated something it should have resolved. Wasteful.
A good agent drives BOTH to ~0 while justifiably escalating the irreducible residue.
"""

from dataclasses import dataclass

from .data import DRIFT_BINS, drift_bin

_BINKEYS = [f"{lo:.1f}-{min(hi, 1.0):.1f}" for lo, hi in DRIFT_BINS]


@dataclass
class BinScore:
    bin: str
    n: int = 0
    errors: int = 0           # truth == error
    ambiguous: int = 0        # truth == needs_human
    caught: int = 0           # error correctly flagged
    false_clear: int = 0      # ok on an error OR an ambiguous claim (the dangerous error)
    false_alarm: int = 0      # error verdict on a clean OR ambiguous claim (over-confident)
    escalate: int = 0
    over_ask: int = 0         # escalate on a clean claim (wasteful)
    justified_ask: int = 0    # escalate on an error or ambiguous claim (good judgment)

    @property
    def escalation_rate(self) -> float:
        return self.escalate / self.n if self.n else 0.0

    @property
    def false_clear_rate(self) -> float:
        return self.false_clear / self.n if self.n else 0.0

    @property
    def over_ask_rate(self) -> float:
        return self.over_ask / self.n if self.n else 0.0

    @property
    def justified_ask_rate(self) -> float:
        return self.justified_ask / self.n if self.n else 0.0

    @property
    def error_recall(self) -> float:
        return self.caught / self.errors if self.errors else float("nan")


def run(agent, stream) -> dict[str, BinScore]:
    bins: dict[str, BinScore] = {k: BinScore(k) for k in _BINKEYS}
    findings = []
    for c in stream:
        b = bins[drift_bin(c.drift)]
        b.n += 1
        truth = c.truth
        if truth == "error":
            b.errors += 1
        elif truth == "needs_human":
            b.ambiguous += 1

        d = agent.review(c.view)  # agent sees only c.view — never the label
        v = d.verdict
        if v == "escalate":
            b.escalate += 1
            if truth == "clean":
                b.over_ask += 1
            else:
                b.justified_ask += 1
        elif v == "error":
            if truth == "error":
                b.caught += 1
            else:
                b.false_alarm += 1
        else:  # ok
            if truth in ("error", "needs_human"):
                b.false_clear += 1
            # clean & ok = correct clear (no counter needed)

        findings.append({
            "claim_id": c.claim_id, "isin": c.isin, "kind": c.kind, "drift": c.drift,
            "drift_bin": b.bin, "truth": truth, "corruption": c.corruption,
            "verdict": v, "confidence": round(d.confidence, 2), "rationale": d.rationale,
        })
    run.last_findings = findings
    return bins


run.last_findings = []  # type: ignore[attr-defined]


def trustworthy_ceiling(bins: dict[str, BinScore]) -> str:
    """Highest contiguous drift bin (from the bottom) with zero false-clears."""
    ceiling = "none"
    for key in _BINKEYS:
        s = bins[key]
        if s.n == 0:
            continue
        if s.false_clear == 0:
            ceiling = key
        else:
            break
    return ceiling


def overall(bins: dict[str, BinScore]) -> dict:
    n = sum(b.n for b in bins.values())
    fc = sum(b.false_clear for b in bins.values())
    oa = sum(b.over_ask for b in bins.values())
    ja = sum(b.justified_ask for b in bins.values())
    return {
        "n": n,
        "false_clear_rate": fc / n if n else 0.0,
        "over_ask_rate": oa / n if n else 0.0,
        "justified_ask_rate": ja / n if n else 0.0,
    }
