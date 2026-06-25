# SunsteadHack Control Plane Plugin

Operate the SunsteadHack autoresearch control plane from Claude Code. Dispatch runs, watch optimization curves, and adjudicate escalations—all from slash commands.

## Install

This plugin is bundled with the SunsteadHack project. To enable it in Claude Code:

1. Ensure you have the `cleanroom/control/` module and its dependencies installed.
2. Set `PYTHONPATH` to the repo root (or configure in `.claude-plugin/plugin.json`).
3. Enable the plugin in Claude Code settings.

## Commands

- **`/dispatch <task_id> [model] [iterations]`** — Dispatch a new optimization run on an active task.
- **`/runs [state]`** — List all runs, optionally filtered by state (running, done, failed, etc.).
- **`/escalations`** — List all pending escalations awaiting human judgment (governance checkpoints).
- **`/adjudicate <crossing_id> <decision> [rationale]`** — Make a human decision on an escalation (approve/reject/allow/block).
- **`/curve <task_id>`** — Read the performance curve (all experiments) for a task.

## Persistence

By default, the plugin uses **in-memory storage** (state is lost when the MCP server restarts). To enable **persistent storage** backed by Aiven Postgres:

```bash
export CLEANROOM_PG_DSN="postgresql://user:pass@host:5432/db?sslmode=require"
```

The plugin will automatically:
- Create the required schema tables (experiment, crossing, judgment, run)
- Persist all runs and escalations to Postgres
- Sync state across separate Claude Code sessions

## Legitimacy Boundary

**What the plugin allows (free):**
- Dispatching runs with different models/iterations on an active task (parameterization)
- Polling run status and performance curves
- Listing and adjudicating pending escalations

**What the plugin does NOT expose (governed):**
- Scoring / benchmarking (in-place evaluation without explicit control)
- Silently mutating a task's objective or workload
- Changing pore rules or risk thresholds
- Registering new tasks — these escalate if they are irreversible or high-risk; humans adjudicate

The philosophy: Claude operates *within* the task and run lifecycle, but cannot unilaterally redefine the rules of engagement.

## Architecture

- **MCP Server**: `cleanroom.control.server.mcp` (stdio transport)
- **Backend Factory**: `cleanroom.control.server.wiring` (selects persistent vs. in-memory by `CLEANROOM_PG_DSN`)
- **Operator Core**: `cleanroom.control.ops.Operator` (task registration, dispatch, escalation, adjudication)
- **CLI Adapter**: `cleanroom.control.server.cli` (argparse CLI for local testing)

## Development

### Run the MCP server directly
```bash
PYTHONPATH=. python -m cleanroom.control.server.mcp
```

### Test via CLI
```bash
# List tasks
python -m cleanroom.control.server.cli list-tasks

# Register a task
python -m cleanroom.control.server.cli register-task --spec-json '{"task_id":"t1","objective":"...","workload_id":"w1","action_space":[],"db_ref":"...","constraints":{},"default_model":"gpt-4"}'

# Dispatch a run
python -m cleanroom.control.server.cli dispatch-run t1 --model gpt-4 --iterations 10

# List runs
python -m cleanroom.control.server.cli list-runs

# Pending escalations
python -m cleanroom.control.server.cli pending-escalations

# Adjudicate
python -m cleanroom.control.server.cli adjudicate 1 approve --rationale "approved by human"

# Read curve
python -m cleanroom.control.server.cli read-curve t1
```

With `CLEANROOM_PG_DSN` set, all state persists across CLI invocations.

## Phase 1 vs. Phase 2

**Phase 1 (now):**
- Operator surface with in-memory or Aiven Postgres backend
- FIXTURE proposer (DummyProposer) and benchmark (CannedBenchmark)
- REAL frozen pore for governance
- Manual task registration and escalation adjudication

**Phase 2 (future):**
- ClaudeCodeProposer (Claude-powered candidate generation)
- Real benchmark (live performance measurement)
- Tighter integration with workload streams and optimization loops
