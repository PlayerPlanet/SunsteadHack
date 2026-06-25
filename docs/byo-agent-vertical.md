# BYO-Agent + BYO-Task Vertical

## Overview

The BYO-Agent vertical enables users to bring their own agent (hosted on AWS Bedrock AgentCore Runtime) and their own task (eval dataset + grader), and runs the EXISTING auto-research optimization loop to improve the agent's config — without modifying any frozen contract.

The vertical is fully integrated into the `sunsteadhack` loop, reusing the same loop infrastructure that drives kernel, quant, and bio domains (Epic #8).

## Design Principles (Issue #28 — The Benchmark Paradox)

The vertical implements the non-circular judge design required by Issue #28:

1. **Non-Agent Judge**: The judge (`judge.py`) imports NO LLM client of any kind (anthropic, openai, boto3, bedrock, etc.). Truth is grounded ONLY in user-planted labels and deterministic graders.

2. **Held-Out Split**: The proposer (agentic optimizer) receives ONLY the TRAIN split. The HELD-OUT split is reserved for measurement. The agent being optimized can NEVER see the test set.

3. **Frozen Loss**: The loss (grader + eval dataset) is frozen via content hash before iteration 0. Any tampering is detected via `check_correctness()`.

4. **Refused LLM-Judge**: If a task requests LLM-as-judge or soft rubric grading, the vertical REFUSES with a clear error. The paradox remains human territory.

5. **Ruler, Not Runner**: The platform measures the agent only up to the manufacturable edge — where the user holds an objective answer key. The platform is never a better agent than the BYO agent.

## Package Structure

```
cleanroom/domains/byo_agent/
├── __init__.py                    # Package root, env builder, helpers
├── agentcore_client.py            # AgentCoreInvoker (real AWS) + StubAgent (offline)
├── judge.py                       # BYOAgentBenchmark (NO LLM client per Issue #28)
├── actions.py                     # BYOAgentActions (apply/rollback config deltas)
├── pore.py                        # BYOAgentPore (risk evaluation)
├── proposer.py                    # BYOAgentProposer (Claude-based) + ScriptedProposer (offline)
├── loss_spec.py                   # Loss specification, freezing, hashing
└── fixtures/
    └── demo_eval.jsonl            # 12-row demo eval set (arithmetic)
```

## Key Classes

### AgentCoreInvoker
- Real AWS Bedrock AgentCore runtime integration.
- `invoke(prompt, config) -> {"result": str, "tokens": int}`.
- Boto3 and requests lazy-imported (no import needed for offline tests).

### StubAgent
- Deterministic test double (no AWS credentials needed).
- Error rate improves based on config quality markers:
  - system_prompt contains "expert"/"careful"/"precise" → lower error
  - few_shot examples present → lower error
  - temperature < 0.5 → lower error
  - top_p < 0.5 → lower error
- Answers arithmetic prompts correctly with probability = quality.
- Makes the offline curve actually descend.

### BYOAgentBenchmark
- Runs the agent on HELD-OUT data only (train split never used for measurement).
- Returns error_rate as p99_ms (lower=better, per loop convention).
- `check_correctness()` detects tampering with frozen keys via content hash.
- `is_within_noise()` delegates to shared statistical gate.

### BYOAgentActions
- Applies config deltas via shallow merge: `_cur_config = {**_cur_config, **delta}`.
- Rolls back via stack: prior config is pushed on apply, popped on rollback.
- Exact round-trip guaranteed.

### BYOAgentPore
- Low-risk: system_prompt, few_shot, temperature, top_p, max_tokens changes.
- Medium-risk: model changes (cost + behavior).
- High-risk (blocked): attempts to mutate _agent, _grader, _eval, _loss_hash.

### BYOAgentProposer
- Claude-based with forced tool_use for structured deltas.
- Receives TRAIN split only (never holdout).
- Forbidden keys never appear in proposals.

### ScriptedProposer
- Deterministic sequence of config deltas.
- Used for offline curve scripts and reproducible testing.

### build_loss_spec()
- Constructs a loss spec dict matching the domain-onboarding straw-man.
- Validates grader kind (only "exact", "regex", "programmatic" allowed).
- Refuses "llm_rubric", "llm_judge", or any soft rubric.
- Generates content_hash for tamper detection.

## Domain Registration

The vertical is registered in `cleanroom/control/domains.py` under workload_id `"byo_agent_demo"`:

```python
_BUILDERS: dict[str, Callable[[], DomainBundle]] = {
    ...
    "byo_agent_demo": _byo_agent_bundle,
}
```

A task JSON file (e.g., `cleanroom/control/tasks/byo-agent-demo.json`) specifies:
- `workload_id: "byo_agent_demo"` — routes to the vertical
- `action_space: ["agent_config"]` — config delta actions only
- `agent_ref: "stub"` (demo) or AWS ARN (production)
- `eval_ref: "path/to/eval.jsonl"` — hold-out test data
- `grader: {"kind": "exact"}` — exact match, regex, or programmatic

## Environment Dictionary

The loop receives an env dict (passed as task_spec["conn"]) with:

```python
{
    "_cur_config": {...},           # Current agent config
    "_agent": StubAgent | AgentCoreInvoker,  # Agent to measure
    "_eval": {"train": [...], "holdout": [...]},  # Split data
    "_grader": ("exact", grader_fn),  # Frozen grader
    "_loss_hash": "sha256...",       # Content hash of (grader, eval)
    "_logclient": InMemoryLogClient,  # Audit trail
    "_config_stack": [],             # Rollback stack
}
```

All fields EXCEPT `_cur_config` and `_config_stack` are FROZEN. Candidates attempting to mutate them are blocked by pore/check_correctness.

## Running the Demo

### Offline Curve (No AWS Required)

```bash
uv run python scripts/run_byo_agent_curve.py --iterations 8
```

Output shows descending error-rate curve:
```
-- [byo-agent-demo] BYO-Agent demo ------------------------------------------
   experiments logged : 7
   baseline error     : 0.7500
   best error         : 0.0000
   improvement        : +100.0%
   decisions          : keep=3 discard=3 rollback=1 escalated=0

-- Error-rate curve (per iteration) ---------------------------------
   0. baseline=0.7500 > candidate=1.0000 [rollback]
   1. baseline=0.7500 > candidate=0.7500 [discard]
   2. baseline=0.7500 > candidate=0.5000 [keep]
   3. baseline=0.5000 > candidate=0.2500 [keep]
   4. baseline=0.2500 > candidate=0.0000 [keep]
```

### Running Tests

```bash
python -m pytest tests/test_byo_agent*.py -v
```

All 18 tests pass:
- 4 judge tests (including Issue #28 compliance)
- 4 actions tests (round-trip correctness)
- 4 proposer tests (holdout data leakage prevention)
- 3 end-to-end loop tests (curve descent, loss freeze, tampering)
- 3 Issue #28 specific tests (no LLM imports, deterministic graders, refusal of LLM judges)

## Demonstrating the Non-Circular Design

The Issue #28 docstring is explicit in three places:

1. **judge.py module docstring**: "This module imports NO LLM client of any kind."
2. **StubAgent docstring**: "This stub is the CONTESTANT being measured. The REFEREE is judge.py + held-out labels."
3. **agentcore_client.py docstring**: "The agent (contestant) is measured only by the referee (held-out labels + grader)."

The held-out / train split enforcement happens in:
- `build_env_from_task()`: splits 70% train, 30% holdout
- `BYOAgentBenchmark.run_benchmark()`: uses ONLY holdout for measurement
- `BYOAgentProposer` prompt: "TRAIN SET (do NOT use holdout)" — no holdout examples included

The loss freeze happens via:
- `build_loss_spec()`: generates content_hash
- `BYOAgentBenchmark.check_correctness()`: verifies hash unchanged (detects tampering)
- Test `test_byo_agent_no_llm_in_judge.py`: scans source for forbidden imports

## Extending to Real AWS

To use a real Bedrock AgentCore runtime:

1. Set AWS credentials in environment.
2. Create a task JSON with `agent_ref: "arn:aws:bedrock-agentcore:..."`.
3. Replace `"stub"` with `"bedrock"` in `agent_ref`.
4. The `AgentCoreInvoker` will lazily import boto3 and invoke the runtime.

The grader and loss freeze remain the same — the only change is the agent invoker.

## The Verdict

The BYO-Agent vertical proves the autoresearch loop substrate generalizes beyond Postgres + kernel/quant/bio domains. It demonstrates:

1. **Modularity**: Same loop, different judge (proposer/benchmark/pore/actions).
2. **Non-Circularity**: Judge imports no LLM. Truth from held-out labels or deterministic graders.
3. **Honesty Invariant**: Never keeps an incorrect candidate (checked every iteration).
4. **Freezing**: Loss is hashed and verified to prevent post-hoc tampering.
5. **Safety**: Pore gates risk, check_correctness blocks forbidden mutations, proposer never sees holdout.

The curve descends from 75% error to 0% error, with one rollback and several within-noise rejections, showing the loop works end-to-end.
