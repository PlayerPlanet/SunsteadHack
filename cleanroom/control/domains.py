"""Control-plane domain binding — maps a domain TaskSpec to its loop components.

Epic #8 proves the substrate generalizes beyond Postgres: the SAME `run_loop`
drives a quant / bio / kernel judge by swapping only the (benchmark, pore, actions,
proposer) tuple and seeding a domain-specific env. This module is the dispatch-time
binding that lets those domains run *through Story D's control plane unchanged*:
the dispatcher asks `resolve_domain(task_spec)`; a non-domain (Postgres) task
resolves to `None` and dispatch falls back to the injected ctx + builtin
`cleanroom.actions`.

The domain packages (`cleanroom.domains.*`) stay pure implementations; the binding
lives here so the control plane owns it (Story D's file boundary) and the heavy
domain imports stay lazy (only the dispatched domain is imported).

Selection key is `TaskSpec.workload_id` — the frozen workload identifier — so a
committed domain TaskSpec JSON wires itself to its judge with no code change.
"""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class DomainBundle:
    """Per-dispatch loop components for one domain run.

    Fields mirror `run_loop`'s injected seam:
      proposer / benchmark / pore / actions — the swapped components.
      make_env  — factory for a FRESH mutable env dict, seeded into
                  task_spec["conn"] (the loop's per-run state the actions/benchmark
                  read & mutate). A factory (not a value) so every dispatch starts
                  from a clean baseline state.

    The make_env callable now accepts an optional task_spec dict parameter to allow
    domains to load real task data at dispatch time.
    """

    proposer: Any
    benchmark: Any
    pore: Any
    actions: Any
    make_env: Callable[[dict | None], dict]


def _kernel_bundle() -> DomainBundle:
    from cleanroom.domains.kernel import (
        KERNELS,
        KernelActions,
        KernelBenchmark,
        KernelPore,
        KernelProposer,
    )

    return DomainBundle(
        proposer=KernelProposer(),
        benchmark=KernelBenchmark(),
        pore=KernelPore(),
        actions=KernelActions(),
        make_env=lambda task_spec=None: {"kernel_fn": KERNELS["naive"], "_cur_strategy": "naive"},
    )


def _quant_bundle() -> DomainBundle:
    from cleanroom.domains.quant import (
        OHLCV_DATA,
        QuantActions,
        QuantBenchmark,
        QuantPore,
        QuantProposer,
        _N_TRAIN,
    )

    return DomainBundle(
        proposer=QuantProposer(),
        benchmark=QuantBenchmark(),
        pore=QuantPore(),
        actions=QuantActions(),
        make_env=lambda task_spec=None: {
            "lookback": 30,
            "threshold": 0.02,
            "data": OHLCV_DATA,
            "n_train": _N_TRAIN,
        },
    )


def _bio_bundle() -> DomainBundle:
    from cleanroom.domains.bio import (
        BIO_SPLITS,
        BioActions,
        BioBenchmark,
        BioPore,
        BioProposer,
    )

    return DomainBundle(
        proposer=BioProposer(),
        benchmark=BioBenchmark(),
        pore=BioPore(),
        actions=BioActions(),
        # Trivial baseline (threshold≈1.0 predicts almost nothing positive → F1≈0)
        # so any trained pipeline produces a clear first descent in the curve.
        make_env=lambda task_spec=None: {
            "lr": 0.0001,
            "max_iter": 1,
            "threshold": 0.99,
            "l2": 0.0,
            "splits": BIO_SPLITS,
        },
    )


def _byo_agent_bundle() -> DomainBundle:
    from cleanroom.domains.byo_agent import (
        BYOAgentActions,
        BYOAgentBenchmark,
        BYOAgentPore,
        ScriptedProposer,
        build_env_from_task,
    )

    # For the domain bundle factory, we create a minimal env that can be augmented
    # by the caller. The caller (script/control plane) must pass full task_dict
    # to build_env_from_task() to get the real env with agent + eval loaded.
    def make_byo_env(task_spec=None):
        if task_spec:
            # Load real env from task spec.
            return build_env_from_task(task_spec)
        # Minimal stub env — used for offline tests without real task data.
        return {
            "_cur_config": {
                "system_prompt": "You are a helpful assistant.",
                "few_shot": [],
                "temperature": 1.0,
                "top_p": 1.0,
                "max_tokens": 1024,
            },
            "_agent": None,
            "_eval": {"train": [], "holdout": []},
            "_grader": ("exact", BYOAgentBenchmark._exact_grader),
            "_loss_hash": "",
            "_logclient": None,
            "_config_stack": [],
        }

    return DomainBundle(
        proposer=ScriptedProposer(),  # Use scripted for deterministic bundle
        benchmark=BYOAgentBenchmark(),
        pore=BYOAgentPore(),
        actions=BYOAgentActions(),
        make_env=make_byo_env,
    )


# Domain TaskSpecs select their bundle by workload_id. Keep these keys in sync with
# the committed task JSON files under cleanroom/control/tasks/.
def _bond_extraction_bundle() -> DomainBundle:
    from cleanroom.domains.bond_extraction import (
        BondActions,
        BondBenchmark,
        BondPore,
        ScriptedExtractor,
        build_env_from_task,
    )

    return DomainBundle(
        proposer=ScriptedExtractor(),  # Use scripted for deterministic offline runs.
        benchmark=BondBenchmark(),
        pore=BondPore(),
        actions=BondActions(),
        make_env=lambda task_spec=None: (
            build_env_from_task(task_spec)
            if task_spec
            else {
                "_cur_config": {
                    "field_patterns": {},
                    "validation_enabled": False,
                    "field_schema": [],
                },
                "_extractor": None,
                "_eval": {"train": [], "holdout": []},
                "_grader": ("field_match", None),
                "_loss_hash": "",
                "_interpretation": [],
                "_logclient": None,
                "_config_stack": [],
            }
        ),
    )


def _agent_bundle() -> DomainBundle:
    """Agent self-improvement flywheel (Issue #43 — Tier B).

    CAVEAT: This domain's CodeActions mutates candidate_agent.py source on disk
    in-process. Safe for local stdio MCP (single trusted process) but NOT for
    load-balanced/queue-mode remote control plane (concurrent runs race on the file).
    Remote deployment requires git-worktree isolation per-iteration (deferred,
    Issue #43 hardening phase).

    The domain ensures the modifiable surface (candidate_agent.py THRESHOLD)
    starts at the documented baseline (0.95) by resetting it in make_env, so
    a fresh dispatch begins at the bad baseline, not wherever prior runs left it.
    """
    from cleanroom.domains.agent import (
        AgentBenchmark,
        CodeActions,
        AgentPore,
        CuratedSourceProposer,
    )
    import pathlib

    def make_agent_env(task_spec=None):
        """Reset candidate_agent.py to baseline (THRESHOLD=0.95) before each run.

        This ensures every dispatched run starts fresh at the bad baseline,
        independent of prior runs' final states.
        """
        # Reset the modifiable surface's THRESHOLD to the baseline (0.95) IN PLACE.
        # Edit only the module-level constant (anchored, single occurrence) rather than
        # rewriting the whole file from a hardcoded string — the latter drifts from the
        # real source and silently clobbers it on every dispatch.
        import re

        candidate_agent_path = (
            pathlib.Path(__file__).parent.parent
            / "domains" / "agent" / "candidate_agent.py"
        )
        src = candidate_agent_path.read_text()
        new_src, n = re.subn(
            r"^THRESHOLD\s*=\s*[\d.]+",
            "THRESHOLD = 0.95",
            src,
            count=1,
            flags=re.MULTILINE,
        )
        if n == 0:
            raise RuntimeError(
                "_agent_bundle.make_env: no module-level 'THRESHOLD = ...' assignment "
                "found in candidate_agent.py"
            )
        candidate_agent_path.write_text(new_src)

        # Reload the module so subsequent imports get the fresh version.
        import sys
        import importlib
        module_name = "cleanroom.domains.agent.candidate_agent"
        if module_name in sys.modules:
            del sys.modules[module_name]

        # Create the benchmark and freeze the loss hash before any iterations.
        benchmark = AgentBenchmark(train_seed=7, eval_seed=11)
        benchmark.freeze_loss_hash()

        return {
            "_loss_hash": benchmark._loss_hash,
            "_eval_seed": 11,
        }

    benchmark = AgentBenchmark(train_seed=7, eval_seed=11)
    benchmark.freeze_loss_hash()

    return DomainBundle(
        proposer=CuratedSourceProposer(),
        benchmark=benchmark,
        pore=AgentPore(),
        actions=CodeActions(),
        make_env=make_agent_env,
    )


_BUILDERS: dict[str, Callable[[], DomainBundle]] = {
    "kernel_matmul_32": _kernel_bundle,
    "quant_walkforward_momentum": _quant_bundle,
    "bio_molclass_f1": _bio_bundle,
    "byo_agent_demo": _byo_agent_bundle,
    "bond_extraction": _bond_extraction_bundle,
    "agent_selfimprove": _agent_bundle,
}


def _workload_id(task_spec: Any) -> str:
    """Read workload_id from a TaskSpec dataclass or a plain dict."""
    if hasattr(task_spec, "workload_id"):
        return task_spec.workload_id
    if isinstance(task_spec, dict):
        return task_spec.get("workload_id", "")
    return ""


def is_domain_workload(workload_id: str) -> bool:
    """True if workload_id maps to a registered domain judge."""
    return workload_id in _BUILDERS


def resolve_domain(task_spec: Any) -> DomainBundle | None:
    """Return the DomainBundle for a domain TaskSpec, or None for a Postgres task.

    Accepts either a TaskSpec dataclass or a dict carrying a 'workload_id'.
    """
    builder = _BUILDERS.get(_workload_id(task_spec))
    return builder() if builder else None
