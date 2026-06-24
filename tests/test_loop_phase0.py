"""Phase-0 tests for cleanroom loop and actions.

Tests the control flow of run_loop with various outcome scenarios:
1. End-to-end happy path with improving results (keep decisions).
2. Regression handling (rollback decisions).
3. Within-noise handling (discard decisions).
4. Escalation handling (pore requires_human_judgment).
5. Actions apply/rollback with real conn and no-op conn.
"""

import pytest

from cleanroom.fixtures import (
    CannedBenchmark,
    DummyProposer,
    InMemoryLogClient,
    NoOpPore,
)
from cleanroom.loop import run_loop
from cleanroom import actions
from cleanroom.types import Candidate, Result, PoreResult


class TestRunLoopHappyPath:
    """Test the happy path: successive keep decisions with improving p99."""

    def test_canned_benchmark_improves_monotonically(self):
        """Verify the fixture itself decreases p99 over time."""
        bench = CannedBenchmark(baseline_p99=100.0)
        r1 = bench.run_benchmark(None, "", warmup=5, trials=10)
        r2 = bench.run_benchmark(None, "", warmup=5, trials=10)
        r3 = bench.run_benchmark(None, "", warmup=5, trials=10)

        # Should be monotonically decreasing
        assert r1.p99_ms > r2.p99_ms > r3.p99_ms

    def test_end_to_end_with_fixtures(self):
        """Run the loop with all fixtures; expect descending candidate_p99 and keep decisions."""
        task_spec = {
            "task_id": "test_task_1",
            "model": "stub",
            "workload_id": "workload_1",
            "drift_level": 0,
            "conn": None,  # Phase-0: no real conn
        }

        proposer = DummyProposer(base_candidate_type="index")
        benchmark = CannedBenchmark(baseline_p99=100.0)
        pore = NoOpPore()
        logclient = InMemoryLogClient()

        # Run 5 iterations (iteration 0 establishes baseline, iterations 1-4 propose/benchmark)
        run_loop(
            task_spec,
            proposer=proposer,
            benchmark=benchmark,
            pore=pore,
            logclient=logclient,
            iterations=5,
        )

        # Expect 4 experiment records (iterations 1-4; iteration 0 is baseline-only)
        experiments = logclient.read_experiments()
        assert len(experiments) == 4, f"Expected 4 experiments, got {len(experiments)}"

        # All should be keep decisions (CannedBenchmark always improves)
        decisions = [e["decision"] for e in experiments]
        assert all(d == "keep" for d in decisions), f"Expected all keep, got {decisions}"

        # Check that candidate_p99 is descending
        p99s = [e["candidate_p99"] for e in experiments]
        for i in range(len(p99s) - 1):
            assert p99s[i] > p99s[i + 1], (
                f"Expected descending p99, got {p99s}"
            )


class RegressionBenchmark:
    """Test double: returns a regression on a specific proposal iteration."""

    def __init__(self, regression_on_proposal: int = 1):
        """
        Initialize with proposal number that triggers regression.

        Args:
            regression_on_proposal: Which proposal (1-indexed) should regress.
                Baseline established on call 0, proposal 1 is call 1, etc.
        """
        self.call_count = 0
        self.regression_on_proposal = regression_on_proposal
        self.baseline_p99 = 100.0

    def run_benchmark(self, conn, workload_id: str, *, warmup: int = 5, trials: int = 10) -> Result:
        """Return a regressed p99 on the specified proposal."""
        self.call_count += 1
        # call_count 1 is baseline, call_count 2 is proposal 1, etc.
        proposal_num = self.call_count - 1

        if proposal_num == self.regression_on_proposal:
            # Return worse than baseline
            p99 = self.baseline_p99 * 1.2
        else:
            # Return improving result
            p99 = self.baseline_p99 * (0.95 ** self.call_count)

        samples = [p99 * (0.95 + (i % 3) * 0.02) for i in range(trials)]
        return Result(
            p99_ms=p99,
            throughput=1000.0 / p99,
            cost_estimate=10.0 + (0.1 * self.call_count),
            samples=samples,
        )

    def check_correctness(self, conn, candidate: Candidate) -> bool:
        """Always passes."""
        return True

    def is_within_noise(self, baseline_samples: list[float], candidate_samples: list[float]) -> bool:
        """Standard noise check."""
        if not baseline_samples or not candidate_samples:
            return True
        import statistics
        baseline_mean = statistics.mean(baseline_samples)
        candidate_mean = statistics.mean(candidate_samples)
        baseline_stdev = (
            statistics.stdev(baseline_samples)
            if len(baseline_samples) > 1
            else 0.0
        )
        candidate_stdev = (
            statistics.stdev(candidate_samples)
            if len(candidate_samples) > 1
            else 0.0
        )
        combined_stdev = (baseline_stdev + candidate_stdev) / 2.0 or 1.0
        return abs(candidate_mean - baseline_mean) < combined_stdev


class TestRegressionHandling:
    """Test that regressions trigger rollback."""

    def test_regression_on_iteration_2(self):
        """Trigger a regression on first proposal."""
        task_spec = {
            "task_id": "test_regression_1",
            "model": "stub",
            "workload_id": "workload_1",
            "drift_level": 0,
            "conn": None,
        }

        proposer = DummyProposer(base_candidate_type="index")
        benchmark = RegressionBenchmark(regression_on_proposal=1)  # Regress on proposal 1
        pore = NoOpPore()
        logclient = InMemoryLogClient()

        run_loop(
            task_spec,
            proposer=proposer,
            benchmark=benchmark,
            pore=pore,
            logclient=logclient,
            iterations=4,
        )

        experiments = logclient.read_experiments()
        # First experiment should be rollback (regression)
        assert experiments[0]["decision"] == "rollback"
        # Subsequent experiments should be keep (improving)
        assert experiments[1]["decision"] == "keep"


class WithinNoiseBenchmark:
    """Test double: returns a result within noise on a specific proposal."""

    def __init__(self, within_noise_on_proposal: int = 1):
        """
        Initialize with proposal number that triggers within_noise.

        Args:
            within_noise_on_proposal: Which proposal (1-indexed) should be within noise.
        """
        self.call_count = 0
        self.within_noise_on_proposal = within_noise_on_proposal
        self.baseline_p99 = 100.0
        self.last_baseline = None

    def run_benchmark(self, conn, workload_id: str, *, warmup: int = 5, trials: int = 10) -> Result:
        """Return a slightly improved p99 (within noise range) on the specified proposal."""
        self.call_count += 1
        # call_count 1 is baseline, call_count 2 is proposal 1, etc.
        proposal_num = self.call_count - 1

        if self.call_count == 1:
            # Establish baseline
            p99 = self.baseline_p99 * 0.95
            self.last_baseline = p99
        elif proposal_num == self.within_noise_on_proposal:
            # Return improvement within noise (e.g., 0.5% difference from baseline)
            p99 = self.last_baseline * 0.995
        else:
            # Return normal improving result
            p99 = self.baseline_p99 * (0.95 ** self.call_count)
            self.last_baseline = p99

        # Generate samples very close to the mean (tight stdev ~0.1%)
        samples = [p99 * (0.999 + (i % 3) * 0.0003) for i in range(trials)]
        return Result(
            p99_ms=p99,
            throughput=1000.0 / p99,
            cost_estimate=10.0 + (0.1 * self.call_count),
            samples=samples,
        )

    def check_correctness(self, conn, candidate: Candidate) -> bool:
        """Always passes."""
        return True

    def is_within_noise(self, baseline_samples: list[float], candidate_samples: list[float]) -> bool:
        """Force within_noise on the specified proposal."""
        proposal_num = self.call_count - 1
        if proposal_num == self.within_noise_on_proposal:
            return True
        # Otherwise, standard check
        if not baseline_samples or not candidate_samples:
            return True
        import statistics
        baseline_mean = statistics.mean(baseline_samples)
        candidate_mean = statistics.mean(candidate_samples)
        baseline_stdev = (
            statistics.stdev(baseline_samples)
            if len(baseline_samples) > 1
            else 0.0
        )
        candidate_stdev = (
            statistics.stdev(candidate_samples)
            if len(candidate_samples) > 1
            else 0.0
        )
        combined_stdev = (baseline_stdev + candidate_stdev) / 2.0 or 1.0
        return abs(candidate_mean - baseline_mean) < combined_stdev


class TestWithinNoiseHandling:
    """Test that within-noise improvements trigger discard."""

    def test_within_noise_on_iteration_2(self):
        """Trigger within_noise on first proposal."""
        task_spec = {
            "task_id": "test_within_noise_1",
            "model": "stub",
            "workload_id": "workload_1",
            "drift_level": 0,
            "conn": None,
        }

        proposer = DummyProposer(base_candidate_type="index")
        benchmark = WithinNoiseBenchmark(within_noise_on_proposal=1)
        pore = NoOpPore()
        logclient = InMemoryLogClient()

        run_loop(
            task_spec,
            proposer=proposer,
            benchmark=benchmark,
            pore=pore,
            logclient=logclient,
            iterations=4,
        )

        experiments = logclient.read_experiments()
        # First experiment should be discard (within_noise)
        assert experiments[0]["decision"] == "discard"
        assert experiments[0]["within_noise"] is True


class EscalatingPore:
    """Test double: escalates on a specific iteration."""

    def __init__(self, escalate_iteration: int = 1):
        """Initialize with iteration number that escalates."""
        self.call_count = 0
        self.escalate_iteration = escalate_iteration

    def evaluate(self, candidate: Candidate) -> PoreResult:
        """Return escalate on the specified iteration."""
        self.call_count += 1
        if self.call_count == self.escalate_iteration:
            return PoreResult(
                pore="escalating_pore",
                risk_level="high",
                requires_human_judgment=True,
                decision="escalate",
            )
        else:
            return PoreResult(
                pore="escalating_pore",
                risk_level="low",
                requires_human_judgment=False,
                decision="allow",
            )


class TestEscalationHandling:
    """Test that pore escalations skip apply/benchmark and write crossing."""

    def test_escalation_on_iteration_2(self):
        """Trigger escalation on iteration 2."""
        task_spec = {
            "task_id": "test_escalation_1",
            "model": "stub",
            "workload_id": "workload_1",
            "drift_level": 0,
            "conn": None,
        }

        proposer = DummyProposer(base_candidate_type="index")
        benchmark = CannedBenchmark(baseline_p99=100.0)
        pore = EscalatingPore(escalate_iteration=1)
        logclient = InMemoryLogClient()

        run_loop(
            task_spec,
            proposer=proposer,
            benchmark=benchmark,
            pore=pore,
            logclient=logclient,
            iterations=4,
        )

        experiments = logclient.read_experiments()
        # First experiment should be escalated
        assert experiments[0]["decision"] == "escalated"
        # A crossing should have been written
        assert len(logclient.crossings) == 1
        assert logclient.crossings[0]["requires_human_judgment"] is True
        # Benchmark should not have been called for iteration 1 (only iterations 2, 3)
        # Since CannedBenchmark increments call_count, it should have been called only 3 times:
        # iter 0 (baseline), iter 2, iter 3
        assert benchmark.call_count == 3


class FakeCursor:
    """Mock cursor for testing SQL generation."""

    def __init__(self):
        """Initialize."""
        self.statements = []

    def execute(self, sql: str):
        """Record the SQL statement."""
        self.statements.append(sql)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass


class FakeCursorFactory:
    """Factory for creating cursor context managers."""

    def __init__(self):
        """Initialize."""
        self.cursor_obj = FakeCursor()

    def __call__(self):
        """Return the cursor."""
        return self.cursor_obj


class FakeConn:
    """Mock connection for testing SQL generation."""

    def __init__(self):
        """Initialize."""
        self.cursor_factory = FakeCursorFactory()
        self.committed = False

    def cursor(self):
        """Return cursor factory (which acts as a context manager)."""
        return self.cursor_factory.cursor_obj

    def commit(self):
        """Mark as committed."""
        self.committed = True


class TestActionsWithRealConn:
    """Test apply/rollback with a fake conn."""

    def test_apply_with_multiple_columns(self):
        """Verify apply handles composite indexes correctly."""
        conn = FakeConn()
        candidate = Candidate(
            type="index",
            params={"table": "transactions", "columns": ["user_id", "status", "timestamp"]},
            reversible=True,
        )

        actions.apply(conn, candidate)

        sql = conn.cursor_factory.cursor_obj.statements[0]
        # All columns should appear in the SQL
        assert "user_id" in sql
        assert "status" in sql
        assert "timestamp" in sql

    def test_apply_index_generates_create_index_sql(self):
        """Verify apply generates correct CREATE INDEX statement."""
        conn = FakeConn()
        candidate = Candidate(
            type="index",
            params={"table": "users", "columns": ["email"]},
            reversible=True,
        )

        actions.apply(conn, candidate)

        # Verify cursor received a CREATE INDEX statement
        assert len(conn.cursor_factory.cursor_obj.statements) == 1
        sql = conn.cursor_factory.cursor_obj.statements[0]
        assert "CREATE INDEX" in sql
        assert "IF NOT EXISTS" in sql
        assert "users" in sql
        assert "email" in sql
        assert conn.committed

    def test_rollback_index_generates_drop_index_sql(self):
        """Verify rollback generates correct DROP INDEX statement."""
        conn = FakeConn()
        candidate = Candidate(
            type="index",
            params={"table": "users", "columns": ["email"]},
            reversible=True,
        )

        actions.rollback(conn, candidate)

        # Verify cursor received a DROP INDEX statement
        assert len(conn.cursor_factory.cursor_obj.statements) == 1
        sql = conn.cursor_factory.cursor_obj.statements[0]
        assert "DROP INDEX" in sql
        assert "IF EXISTS" in sql
        assert conn.committed

    def test_apply_and_rollback_use_same_index_name(self):
        """Verify apply and rollback derive the same index name."""
        conn1 = FakeConn()
        conn2 = FakeConn()
        candidate = Candidate(
            type="index",
            params={"table": "orders", "columns": ["user_id", "created_at"]},
            reversible=True,
        )

        actions.apply(conn1, candidate)
        actions.rollback(conn2, candidate)

        apply_sql = conn1.cursor_factory.cursor_obj.statements[0]
        rollback_sql = conn2.cursor_factory.cursor_obj.statements[0]

        # Extract index names
        # CREATE INDEX "idx_..." -> extract from quotes
        # DROP INDEX "idx_..." -> extract from quotes
        apply_idx = apply_sql.split('"')[1]
        rollback_idx = rollback_sql.split('"')[1]

        assert apply_idx == rollback_idx

    def test_apply_with_none_conn_is_noop(self):
        """Verify apply with conn=None is a safe no-op."""
        candidate = Candidate(
            type="index",
            params={"table": "users", "columns": ["email"]},
            reversible=True,
        )

        # Should not raise
        actions.apply(None, candidate)

    def test_rollback_with_none_conn_is_noop(self):
        """Verify rollback with conn=None is a safe no-op."""
        candidate = Candidate(
            type="index",
            params={"table": "users", "columns": ["email"]},
            reversible=True,
        )

        # Should not raise
        actions.rollback(None, candidate)

    def test_apply_rejects_unknown_candidate_type(self):
        """Verify apply raises for unsupported candidate types."""
        conn = FakeConn()
        candidate = Candidate(
            type="parameter",
            params={"param": "shared_buffers", "value": "4GB"},
            reversible=False,
        )

        with pytest.raises(ValueError, match="unsupported candidate type"):
            actions.apply(conn, candidate)

    def test_rollback_rejects_unknown_candidate_type(self):
        """Verify rollback raises for unsupported candidate types."""
        conn = FakeConn()
        candidate = Candidate(
            type="parameter",
            params={"param": "shared_buffers", "value": "4GB"},
            reversible=False,
        )

        with pytest.raises(ValueError, match="unsupported candidate type"):
            actions.rollback(conn, candidate)

