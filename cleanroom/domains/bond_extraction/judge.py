"""Bond extraction judge — benchmark and correctness evaluation.

DESIGN PRINCIPLE (Issue #28 — the benchmark paradox):
This module imports NO LLM client of any kind (anthropic, openai, boto3 LLM, etc.).
The judge is the REFEREE, not the contestant. It grounds truth ONLY in:
  1. User-planted held-out labels (the answer key in env["_eval"])
  2. Deterministic graders (exact match or field-level F1)

The extractor being measured (env["_extractor"]) is the CONTESTANT. It can never
see the held-out data. Both must be frozen by a content hash before iteration 0
(env["_loss_hash"]).
"""

import hashlib
import json
import statistics as _stats

from cleanroom.benchmark import is_within_noise
from cleanroom.types import Candidate, Result

from .validators import validate_field


class BondBenchmark:
    """Benchmark a bond field extractor on held-out objective rows.

    The grader grounds truth via field-level F1. The extractor is measured only
    on the held-out split, never on the train split. The loss is frozen at the
    start (env["_loss_hash"]) so the proposer cannot tamper with the eval.
    """

    def run_benchmark(
        self, env: dict, workload_id: str, *, warmup: int = 0, trials: int = 5
    ) -> Result:
        """Benchmark the extractor on held-out objective rows.

        Returns p99_ms = 1 - field_F1 (lower=better, per loop convention).

        Args:
            env: Domain environment dict with:
                - _extractor: StubExtractor instance
                - _cur_config: dict, current extractor config
                - _eval: dict with "train" and "holdout" lists of rows
                - _grader: (kind, grader_fn) tuple (field_match in our case)
            workload_id: Identifier (unused, for loop compatibility).
            warmup: Untimed warmup (ignored).
            trials: Number of benchmark passes (default: 5).

        Returns:
            Result with p99_ms = 1 - F1 (lower=better), samples = per-pass F1s.

        Raises:
            ValueError: If env is malformed.
        """
        extractor = env.get("_extractor")
        if not extractor:
            raise ValueError("env['_extractor'] is required")

        eval_dict = env.get("_eval")
        if not eval_dict:
            raise ValueError("env['_eval'] is required (dict with 'train' and 'holdout')")

        cur_config = env.get("_cur_config", {})
        grader_kind, grader_fn = env.get("_grader", ("field_match", None))

        # Only held-out OBJECTIVE rows are used for measurement (never train, never interpretation).
        holdout = [
            row
            for row in eval_dict.get("holdout", [])
            if row.get("kind") == "objective"
        ]
        if not holdout:
            return Result(p99_ms=0.5, throughput=0.0, cost_estimate=0.0, samples=[0.5])

        # Run benchmark trials times.
        f1_scores = []
        for trial in range(trials):
            # For each trial, measure field-level F1 over holdout objective rows.
            trial_f1 = self._measure_f1(extractor, cur_config, holdout, grader_fn)
            f1_scores.append(trial_f1)

        # Aggregate F1 scores: p99_ms = 1 - F1 (lower=better).
        samples = [1.0 - f1 for f1 in f1_scores]
        p99_error = (
            sorted(samples)[max(0, int(0.99 * len(samples)) - 1)]
            if samples
            else 0.5
        )

        # Throughput and cost (stub estimates).
        total_items = len(holdout) * trials
        throughput = total_items / max(0.01, 0.1)
        cost_estimate = 0.0

        return Result(
            p99_ms=p99_error,
            throughput=throughput,
            cost_estimate=cost_estimate,
            samples=samples,
        )

    def _measure_f1(
        self, extractor, config: dict, rows: list, grader_fn
    ) -> float:
        """Measure field-level F1 over a set of rows.

        F1 is averaged across all fields in the row set.

        Args:
            extractor: StubExtractor instance.
            config: Current extractor config.
            rows: List of {document_id, field_name, gold_value, source_text, ...} rows.
            grader_fn: Field-level grader function (unused for exact match).

        Returns:
            F1 score (0.0 to 1.0).
        """
        if not rows:
            return 0.0

        field_metrics = {}  # field_name -> {tp, fp, fn}

        for row in rows:
            field_name = row.get("field_name", "")
            gold_value = row.get("gold_value", "")
            source_text = row.get("source_text", "")

            if not field_name:
                continue

            # Extract the value.
            extracted = extractor.extract(field_name, source_text, config)

            # Initialize metrics for this field if needed.
            if field_name not in field_metrics:
                field_metrics[field_name] = {"tp": 0, "fp": 0, "fn": 0}

            # Exact match (case-insensitive, whitespace-normalized).
            is_match = (
                extracted.strip().lower() == gold_value.strip().lower()
            )

            if is_match:
                field_metrics[field_name]["tp"] += 1
            else:
                if extracted:
                    field_metrics[field_name]["fp"] += 1
                field_metrics[field_name]["fn"] += 1

        # Aggregate F1 across all fields.
        if not field_metrics:
            return 0.0

        total_f1 = 0.0
        for field_name, metrics in field_metrics.items():
            tp = metrics["tp"]
            fp = metrics["fp"]
            fn = metrics["fn"]

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            total_f1 += f1

        return total_f1 / len(field_metrics)

    def check_correctness(self, env: dict, candidate: Candidate) -> bool:
        """Verify that the candidate does not tamper with the loss.

        Returns False (block) if:
          - The current loss hash differs from env["_loss_hash"] (tamper detection)
          - The candidate tries to mutate frozen keys
          - Any extracted value is NOT a span of its source_text (fabrication)
          - Any extracted value fails validate_field format

        Returns True (allow) if the candidate is a valid config delta.

        Args:
            env: Domain environment dict.
            candidate: Proposed candidate.

        Returns:
            True if the candidate is safe; False if it should be blocked.
        """
        # Check for attempted mutations of frozen keys.
        forbidden_keys = {
            "_extractor",
            "_grader",
            "_eval",
            "_loss_hash",
            "_logclient",
            "_interpretation",
        }
        config_delta = candidate.params.get("config_delta", {})
        if any(key in config_delta for key in forbidden_keys):
            return False

        # Verify loss hash is unchanged.
        expected_loss_hash = env.get("_loss_hash", "")
        if expected_loss_hash:
            current_loss_hash = self._compute_loss_hash(env)
            if current_loss_hash != expected_loss_hash:
                return False

        # Fabrication + format gate (the issue-#18 legitimacy guarantee). Simulate the
        # candidate's effective config and run the extractor over the held-out objective
        # rows: every value it EMITS must be (a) grounded in the document — a verbatim
        # span of source_text (no invented values) — and (b) valid for the field's format
        # (coupon numeric, date parseable, ISIN checksum, currency ISO-4217). An empty
        # extraction is an honest miss, not a violation, so it is allowed. The judge may
        # read holdout here; only the PROPOSER is barred from it.
        extractor = env.get("_extractor")
        if extractor is not None:
            effective_config = {**env.get("_cur_config", {}), **config_delta}
            holdout = [
                row
                for row in env.get("_eval", {}).get("holdout", [])
                if row.get("kind") == "objective"
            ]
            for row in holdout:
                field_name = row.get("field_name", "")
                source_text = row.get("source_text", "")
                if not field_name:
                    continue
                value = extractor.extract(field_name, source_text, effective_config)
                if not value:
                    continue  # a miss is honest
                if value.strip().lower() not in source_text.lower():
                    return False  # fabrication: emitted a value not in the document
                if not validate_field(field_name, value):
                    return False  # malformed value for this field type

        return True

    def is_within_noise(
        self, baseline_samples: list, candidate_samples: list
    ) -> bool:
        """Delegate to the shared statistical gate."""
        return is_within_noise(baseline_samples, candidate_samples)

    @staticmethod
    def _compute_loss_hash(env: dict) -> str:
        """Compute SHA256 hash of (grader, eval) to detect tampering."""
        grader_kind, _ = env.get("_grader", ("field_match", None))
        eval_dict = env.get("_eval", {})

        # Hash the eval structure (train + holdout) and grader kind.
        hash_input = json.dumps(
            {"grader_kind": grader_kind, "eval": eval_dict}, sort_keys=True
        )
        return hashlib.sha256(hash_input.encode()).hexdigest()
