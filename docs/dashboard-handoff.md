# Dashboard handoff — BYO-task control-plane contract

> Spec for wiring the dashboard to the control plane. The backend (registration → dispatch → run-status → curve) is **already built and live-proven**; the dashboard's job is to drive four tools and render two things: a run's status and its p99 curve.

## How to connect (read this first)

The control plane is a **FastMCP** server (`cleanroom/control/server/mcp.py::build_server`, name `sunstead-control`). A browser **cannot** speak stdio-MCP directly. The tool functions, however, are deliberately written as **plain Python functions** (`tool_*`) that work with no MCP runtime — the module docstring says so explicitly.

**Recommended (fastest for the demo): a thin HTTP shim over `tool_*`.** ~30 lines of FastAPI that import the functions and expose them as REST. The browser does normal `fetch`:

```python
# cleanroom/control/server/http.py  (sketch — confirm before building)
from fastapi import FastAPI
from pydantic import BaseModel
from cleanroom.control.server import mcp

app = FastAPI()

class TaskBody(BaseModel): spec_json: str
class DispatchBody(BaseModel): task_id: str; model: str; iterations: int = 10

@app.post("/tasks")        # -> task_id
def register(b: TaskBody):       return {"task_id": mcp.tool_register_task(b.spec_json)}
@app.get("/tasks")         # -> [TaskSpec]
def tasks():                     return mcp.tool_list_tasks()
@app.post("/runs")         # -> run_id
def dispatch(b: DispatchBody):   return {"run_id": mcp.tool_dispatch_run(b.task_id, b.model, b.iterations)}
@app.get("/runs/{rid}")    # -> RunStatus
def run(rid: str):               return mcp.tool_get_run(rid)
@app.get("/tasks/{tid}/curve")   # -> [experiment]
def curve(tid: str):             return mcp.tool_read_curve(tid)
```

Alternatives: (B) FastMCP streamable-HTTP transport + an MCP client in the browser — more moving parts, only if we want "real MCP"; (C) if the dashboard is server-rendered Python, import `tool_*` directly.

**Open question to confirm with the orchestrator:** shim vs. MCP transport, and whether Story G's OAuth2.1 resource server gates this surface (if so the shim sits behind the same auth).

## The four-call flow

| Step | Call | Signature | Returns |
|------|------|-----------|---------|
| Submit | `tool_register_task` | `(spec_json: str)` | `task_id: str` |
| Run | `tool_dispatch_run` | `(task_id, model, iterations=10)` | `run_id: str` (returns instantly — fire-and-return) |
| Poll | `tool_get_run` | `(run_id)` | `RunStatus` dict or `None` |
| Chart | `tool_read_curve` | `(task_id)` | `list[experiment]` |

Extras: `tool_list_tasks()`, `tool_get_task(task_id)`, `tool_list_runs(filter_json)`, `tool_cancel_run(run_id)`, `tool_pending_escalations()`, `tool_adjudicate(crossing_id, decision, rationale, judge)`.

## Task spec (the submit form)

`spec_json` is a JSON string of:

```json
{
  "task_id": "my-task",
  "objective": "minimize p99 on the title x cast_info production-year join",
  "workload_id": "job-prodyear",
  "action_space": ["index"],
  "db_ref": "production_db",
  "constraints": { "max_iterations": 10 },
  "default_model": "claude-haiku-4-5-20251001",
  "state": "active"
}
```

- `workload_id` must be one the backend knows. `job-prodyear` is registered after the in-flight control-plane fix; `__default__` always exists (but no index helps it). Treat the field as a **dropdown of known workloads**, not free text, for now.
- `action_space` for the proven path is `["index"]`.

## States the UI must handle

**Registration outcome** — `tool_register_task` runs through the frozen governance pore:
- spec lands `active` → appears in `tool_list_tasks`, dispatchable.
- spec lands `pending_judgment` → held, NOT in `list_tasks`, needs `tool_adjudicate`. **Show this as a governance hold, not an error** — it's the membrane doing its job.

**Run state** (`RunStatus.state`): `queued` → `running` → `done` | `cancelled` | `failed`. Poll `tool_get_run` (~1–2s). Live fields: `iterations_done`, `best_p99`. On `failed`, show `error_msg`.

`RunStatus` dict shape:
```
{ run_id, task_id, model, state, iterations_done, best_p99, started_at, ended_at, error_msg }
```

## The curve (the chart)

`tool_read_curve(task_id)` returns one dict per experiment (iteration). Plot `candidate_p99` over iterations; color each point by `decision`:

| Field | Use |
|-------|-----|
| `candidate_p99` | y-value of the point |
| `baseline_p99` | reference / first point |
| `decision` | `keep` (teal) vs `reject` (amber) |
| `within_noise` | `true` ⇒ rejected (didn't beat the noise floor) |
| `candidate` | the proposed action, e.g. `{type:"index", params:{table, columns}}` — tooltip label |
| `correctness_ok` | sanity flag |

This is exactly the shape behind `docs/live-curve.html` — reuse it as the visual reference (kept = solid descending line, rejected = hollow amber marker that rolls back). Don't drop rejected points: the "refused to keep noise" moment is the story.

## Environment / live-demo prerequisites

- `CLEANROOM_PG_DSN` set ⇒ persistent Postgres + **live** proposer/benchmark; unset ⇒ in-memory + fixtures (fine for UI dev without a DB). Set it so runs and curves persist across requests.
- Live curve also needs: Docker running, `sunstead-proposer:latest` built, `ANTHROPIC_API_KEY`. A seeded PG is up on `localhost:55432` right now for the demo.
- The dispatch background thread runs in the **process that handled the call** — keep the shim a single long-lived server so in-memory runs complete (with a DSN, state persists regardless).

## Reference artifacts

- Strategy / positioning: `docs/strategy.html`
- Live proven curve (visual + recipe): `docs/live-curve.html`
