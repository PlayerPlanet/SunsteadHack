"""Thin FastAPI shim over the MCP tool_* functions — browser-callable REST.

Run:
    uvicorn cleanroom.control.server.http:app --reload --port 8000

All endpoints are unauthenticated for demo use. In production gate with the same
OAuth resource server as the MCP transport.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from cleanroom.control.ingest import ingest_bond_csv
from cleanroom.control.server import mcp

app = FastAPI(title="Sunstead Control Plane", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Tasks ────────────────────────────────────────────────────────────────────

class TaskBody(BaseModel):
    spec_json: str


@app.get("/tasks")
def list_tasks():
    return mcp.tool_list_tasks()


@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    t = mcp.tool_get_task(task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="task not found")
    return t


@app.post("/tasks")
def register_task(body: TaskBody):
    task_id = mcp.tool_register_task(body.spec_json)
    return {"task_id": task_id}


# ── Runs ─────────────────────────────────────────────────────────────────────

class DispatchBody(BaseModel):
    task_id: str
    model: str = "claude-haiku-4-5-20251001"
    iterations: int = 10


@app.get("/runs")
def list_runs(state: str | None = None):
    filter_json = f'{{"state":"{state}"}}' if state else None
    return mcp.tool_list_runs(filter_json)


@app.post("/runs")
def dispatch_run(body: DispatchBody):
    run_id = mcp.tool_dispatch_run(body.task_id, body.model, body.iterations)
    return {"run_id": run_id}


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    r = mcp.tool_get_run(run_id)
    if r is None:
        raise HTTPException(status_code=404, detail="run not found")
    return r


@app.delete("/runs/{run_id}")
def cancel_run(run_id: str):
    mcp.tool_cancel_run(run_id)
    return {"ok": True}


# ── Curve ────────────────────────────────────────────────────────────────────

@app.get("/tasks/{task_id}/curve")
def read_curve(task_id: str):
    return mcp.tool_read_curve(task_id)


# ── Boundary ─────────────────────────────────────────────────────────────────

@app.get("/boundary")
def read_boundary():
    return mcp.tool_read_boundary()


# ── Escalations ──────────────────────────────────────────────────────────────

class AdjudicateBody(BaseModel):
    decision: str
    rationale: str | None = None
    judge: str = "human"


@app.get("/escalations")
def pending_escalations():
    return mcp.tool_pending_escalations()


@app.post("/escalations/{crossing_id}/adjudicate")
def adjudicate(crossing_id: int, body: AdjudicateBody):
    mcp.tool_adjudicate(crossing_id, body.decision, body.rationale, body.judge)
    return {"ok": True}


# ── Ingestion ────────────────────────────────────────────────────────────────────

class IngestBondBody(BaseModel):
    name: str
    objective: str
    gold_csv: str
    splits_csv: str | None = None
    interpretation_csv: str | None = None
    documents_csv: str | None = None


@app.post("/ingest/bond")
def ingest_bond(body: IngestBondBody):
    try:
        result = ingest_bond_csv(
            name=body.name,
            objective=body.objective,
            gold_csv=body.gold_csv,
            splits_csv=body.splits_csv,
            interpretation_csv=body.interpretation_csv,
            documents_csv=body.documents_csv,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Stats (derived) ───────────────────────────────────────────────────────────

@app.get("/stats")
def stats():
    runs = mcp.tool_list_runs()
    escalations = mcp.tool_pending_escalations()
    total = len(runs)
    active = sum(1 for r in runs if r.get("state") == "running")
    best_p99 = min((r["best_p99"] for r in runs if r.get("best_p99")), default=None)
    return {
        "totalExperiments": total,
        "activeRuns": active,
        "bestP99": best_p99,
        "pendingEscalations": len(escalations),
    }
