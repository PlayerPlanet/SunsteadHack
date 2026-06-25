"""BYO-Agent benchmark and correctness judge.

DESIGN PRINCIPLE (Issue #28 — the benchmark paradox):
This module imports NO LLM client of any kind (anthropic, openai, boto3 LLM, etc.).
The judge is the REFEREE, not the contestant. It grounds truth ONLY in:
  1. User-planted/held-out labels (the answer key in env["_eval"])
  2. Deterministic graders (exact match, regex, or a pure callable)

The agent being measured (env["_agent"]) is the CONTESTANT. It can never see
the held-out data. Both must be frozen by a content hash before iteration 0
(env["_loss_hash"]).

If a task requests an LLM-as-judge or rubric grading, this vertical REFUSES
with a clear error — the paradox remains human territory, not auto-scored.
"""

import hashlib
import json
import re
import statistics as _stats

from cleanroom.benchmark import is_within_noise
from cleanroom.types import Candidate, Result


class BYOAgentBenchmark:
    """Benchmark a BYO agent against held-out labels using a deterministic grader.

    The grader grounds truth. The agent is measured only by its accuracy on
    the held-out split, never on the train split. The loss is frozen at the
    start (env["_loss_hash"]) so the proposer cannot tamper with the eval.
    """

    def run_benchmark(
        self, env: dict, workload_id: str, *, warmup: int = 0, trials: int = 5
    ) -> Result:
        """Benchmark the current agent config on held-out data.

        Returns error_rate as p99_ms (lower=better, per loop convention).
        The held-out split is the ONLY data the agent is measured on.

        Args:
            env: Domain environment dict with:
                - _agent: invoker with .invoke(prompt, config) -> {"result": str, "tokens": int}
                - _eval: dict with "train" and "holdout" lists of {input, expected}
                - _cur_config: dict, current agent config
                - _grader: (kind, callable) tuple
            workload_id: Identifier (unused, for loop compatibility).
            warmup: Untimed warmup iterations (ignored; present for compatibility).
            trials: Number of benchmark passes over holdout (default: 5).

        Returns:
            Result with p99_ms = error_rate (lower=better), throughput = items/sec,
            cost_estimate = total_tokens * unit_cost, samples = list of per-pass error rates.

        Raises:
            ValueError: If env is malformed or grader kind is unsupported/LLM-based.
        """
        agent = env.get("_agent")
        if not agent:
            raise ValueError("env['_agent'] is required (invoker object)")

        eval_dict = env.get("_eval")
        if not eval_dict:
            raise ValueError("env['_eval'] is required (dict with 'train' and 'holdout')")

        cur_config = env.get("_cur_config", {})
        grader_kind, grader_fn = env.get("_grader", ("exact", self._exact_grader))

        # Only held-out data is used for measurement (never train).
        holdout = eval_dict.get("holdout", [])
        if not holdout:
            # Edge case: no holdout data. Return neutral result.
            return Result(p99_ms=0.5, throughput=0.0, cost_estimate=0.0, samples=[0.5])

        # Run the benchmark trials times, collecting per-pass error rates.
        error_rates = []
        total_tokens = 0

        for trial in range(trials):
            correct = 0
            trial_tokens = 0

            for item in holdout:
                input_text = item.get("input", "")
                expected = item.get("expected", "")

                # Invoke the agent (the CONTESTANT, never the referee).
                response = agent.invoke(input_text, cur_config)
                result = response.get("result", "")
                trial_tokens += response.get("tokens", 0)

                # Grade using the frozen grader (the REFEREE).
                is_correct = grader_fn(result, expected)
                if is_correct:
                    correct += 1

            # Error rate for this trial: fraction wrong (lower=better, per loop).
            trial_error_rate = 1.0 - (correct / len(holdout)) if holdout else 1.0
            error_rates.append(trial_error_rate)
            total_tokens += trial_tokens

        # Aggregate error rates into a single p99_ms value (overloaded field per design).
        samples = error_rates
        p99_error = (
            sorted(samples)[max(0, int(0.99 * len(samples)) - 1)]
            if samples
            else 0.5
        )
        median_error = _stats.median(samples) if samples else 0.5

        # Throughput: items evaluated per second.
        total_items = len(holdout) * trials
        total_time_estimate = 0.1  # rough estimate, not precise timing
        throughput = total_items / max(0.01, total_time_estimate)

        # Cost: total tokens * unit price (assume $0.001 per 1k tokens, i.e., $1e-6 per token).
        cost_estimate = total_tokens * 1e-6

        return Result(
            p99_ms=median_error,  # Overloaded: actually error_rate, lower=better
            throughput=throughput,
            cost_estimate=cost_estimate,
            samples=samples,
        )

    def check_correctness(self, env: dict, candidate: Candidate) -> bool:
        """Verify that the candidate does not tamper with the loss.

        Returns False (block) if:
          - The current loss hash differs from env["_loss_hash"] (tamper detection)
          - The candidate tries to mutate _grader, _eval, _loss_hash keys

        Returns True (allow) if the candidate is a valid config delta.

        Args:
            env: Domain environment dict.
            candidate: Proposed candidate.

        Returns:
            True if the candidate is safe; False if it should be blocked.
        """
        # Check for attempted mutations of frozen keys.
        forbidden_keys = {"_agent", "_grader", "_eval", "_loss_hash", "_logclient"}
        config_delta = candidate.params.get("config_delta", {})
        if any(key in config_delta for key in forbidden_keys):
            return False

        # Verify loss hash is unchanged (no tampering with grader/eval).
        # Note: only check if _loss_hash is set (may be empty in tests).
        expected_loss_hash = env.get("_loss_hash", "")
        if expected_loss_hash:
            current_loss_hash = self._compute_loss_hash(env)
            if current_loss_hash != expected_loss_hash:
                return False

        return True

    def is_within_noise(
        self, baseline_samples: list, candidate_samples: list
    ) -> bool:
        """Delegate to the shared statistical gate.

        Returns True if candidate is within noise (discard it).
        """
        return is_within_noise(baseline_samples, candidate_samples)

    @staticmethod
    def _exact_grader(result: str, expected: str) -> bool:
        """Exact string match (case-insensitive, whitespace-normalized)."""
        return result.strip().lower() == expected.strip().lower()

    @staticmethod
    def _regex_grader(pattern: str):
        """Regex match factory."""

        def grader(result: str, expected: str) -> bool:
            # expected is the regex pattern
            return bool(re.search(expected, result))

        return grader

    @staticmethod
    def _compute_loss_hash(env: dict) -> str:
        """Compute SHA256 hash of (grader, eval) to detect tampering."""
        grader_kind, _ = env.get("_grader", ("exact", None))
        eval_dict = env.get("_eval", {})

        # Hash the eval structure (train + holdout) and grader kind.
        hash_input = json.dumps(
            {"grader_kind": grader_kind, "eval": eval_dict}, sort_keys=True
        )
        return hashlib.sha256(hash_input.encode()).hexdigest()
