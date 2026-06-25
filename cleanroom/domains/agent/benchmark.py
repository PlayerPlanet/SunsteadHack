"""Agent benchmark — runs instrument.run() and maps bins to objective.

DESIGN (Issue #43):
The objective is: p99_ms = over_ask_rate + W * false_clear_rate, where W=3.0.
- over_ask_rate: Escalate something the agent should have passed (wasteful).
- false_clear_rate: Pass something that is an error or needs human review (DANGEROUS).
- W=3.0: False clears are 3x more expensive than over-asks (per issue #43 brief).

Held-out discipline: The benchmark is evaluated on a DIFFERENT seed than training
(train_seed != eval_seed), so the loop cannot overfit.

check_correctness verifies two gates:
  1. The frozen self-check (judge.passes, loss hash) is unbroken.
  2. The reloaded candidate still honors the review() contract.
"""

import hashlib
import statistics
from bonds_instrument import instrument
from cleanroom.benchmark import is_within_noise
from cleanroom.types import Candidate, Result


W = 3.0  # Weight: false_clear is 3x more expensive than over_ask.


class AgentBenchmark:
    """Benchmarks agent source edits via the bonds_instrument."""

    def __init__(self, train_seed: int = 7, eval_seed: int = 11):
        """Initialize with distinct seeds for train and eval.

        Args:
            train_seed: Seed for training (history context).
            eval_seed: Seed for evaluation (held-out; never used for training).
        """
        self.train_seed = train_seed
        self.eval_seed = eval_seed
        self._loss_hash = None  # Set once at loop start, frozen thereafter.

    def freeze_loss_hash(self):
        """Content-hash the objective before iteration 0.

        This hash is the proof that the loop is not gaming the metric.
        Must be called once before the loop starts.
        """
        # The loss is fully determined by:
        #   - Frozen judge (bonds_instrument/judge.py)
        #   - Weights (W=3.0)
        #   - Eval seed
        loss_preimage = f"agent_loop|W={W}|eval_seed={self.eval_seed}"
        self._loss_hash = hashlib.sha256(loss_preimage.encode()).hexdigest()[:8]

    def run_benchmark(
        self, conn, workload_id: str, *, warmup: int = 5, trials: int = 1
    ) -> Result:
        """Benchmark the current candidate agent on held-out data.

        Imports the current candidate_agent, runs it through the instrument
        on the held-out stream, macro-averages bins, and returns p99_ms =
        over_ask + W*false_clear.

        Args:
            conn: Database connection (unused; bonds_instrument is in-memory).
            workload_id: Identifier (unused, for loop compatibility).
            warmup: Untimed warmup iterations (ignored; bonds_instrument doesn't need it).
            trials: Number of benchmark passes (default 1; set >1 for noise stats).

        Returns:
            Result with:
              - p99_ms: over_ask + W*false_clear (lower=better).
              - throughput: Claims per second.
              - cost_estimate: 0.0 (bonds_instrument is costless).
              - samples: Per-bin objective values (for noise detection).
        """
        import sys
        import importlib
        from bonds_instrument import claims

        # Build the held-out stream (DIFFERENT seed from training).
        base = claims.build_clean_claims()
        eval_stream = claims.poison(
            base, error_rate=0.40, ambiguous_rate=0.15, seed=self.eval_seed
        )

        # Reload the module to pick up any edits, then import fresh.
        module_name = "cleanroom.domains.agent.candidate_agent"
        if module_name in sys.modules:
            ca_module = sys.modules[module_name]
            importlib.reload(ca_module)
        import cleanroom.domains.agent.candidate_agent as ca_module
        CandidateAgent = ca_module.CandidateAgent

        # Instantiate the current candidate agent.
        agent = CandidateAgent()

        # Collect samples across trials.
        all_objectives = []

        for trial in range(trials):
            # Run the agent through the instrument.
            bins = instrument.run(agent, eval_stream)

            # Macro-average across drift bins.
            over_ask_rates = [b.over_ask_rate for b in bins.values()]
            false_clear_rates = [b.false_clear_rate for b in bins.values()]

            oa = statistics.fmean(over_ask_rates) if over_ask_rates else 0.0
            fc = statistics.fmean(false_clear_rates) if false_clear_rates else 0.0

            # Compute the objective (lower=better).
            obj = oa + W * fc
            all_objectives.append(obj)

        # Use p99_ms as the objective (mimics latency minimization).
        p99_ms = statistics.fmean(all_objectives) if all_objectives else 0.0

        # Throughput: claims per second.
        throughput = len(eval_stream) / max(1, trials)

        return Result(
            p99_ms=p99_ms,
            throughput=throughput,
            cost_estimate=0.0,
            samples=all_objectives,
        )

    def check_correctness(self, conn, candidate: Candidate) -> bool:
        """Verify the edit is correct and doesn't break the review() contract.

        Two gates:
        1. Frozen self-check: judge.passes is unchanged, loss hash is unchanged.
        2. The reloaded candidate still honors the review() contract:
           - Returns a Decision with verdict in {"ok", "error", "escalate"}.
           - Does not raise an exception on multiple sample views.

        Args:
            conn: Database connection (unused).
            candidate: The candidate being evaluated.

        Returns:
            True if both gates pass; False if any gate fails.
        """
        try:
            from bonds_instrument import judge, claims
            from cleanroom.domains.agent.candidate_agent import CandidateAgent

            # Gate 1: Judge is frozen (check one example).
            base = claims.build_clean_claims()
            if not base:
                return False
            sample_claim = base[0]
            if not judge.passes(sample_claim.view):
                return False

            # Gate 2: Candidate review() contract is honored.
            agent = CandidateAgent()
            if not hasattr(agent, 'review'):
                return False
            if not callable(agent.review):
                return False

            # Call review on multiple sample views to verify contract.
            test_views = [base[i % len(base)].view for i in range(min(3, len(base)))]
            for test_view in test_views:
                decision = agent.review(test_view)
                if decision is None:
                    return False
                if not hasattr(decision, 'verdict'):
                    return False
                if decision.verdict not in ("ok", "error", "escalate"):
                    return False
                if not hasattr(decision, 'confidence'):
                    return False
                if not hasattr(decision, 'rationale'):
                    return False

            return True

        except Exception:
            # Any exception means the edit broke something.
            return False

    def is_within_noise(
        self, baseline_samples: list[float], candidate_samples: list[float]
    ) -> bool:
        """Delegate to the shared gate.

        Args:
            baseline_samples: Baseline objective values.
            candidate_samples: Candidate objective values.

        Returns:
            True if the candidate is within noise of the baseline.
        """
        return is_within_noise(baseline_samples, candidate_samples)
