import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { cp, hasControlPlane } from "@/lib/api";
import { mockRuns, mockCurve } from "@/lib/mock";

// Reads → pg → Aiven sunstead_control (BFF design):
//   GET /api/runs                — list runs       (run table)
//   GET /api/runs?task_id=X       — descent curve   (experiment table)
// Action → MCP → AgentCore (not yet deployed):
//   POST /api/runs                — dispatch a run
export const runtime = "nodejs";

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const taskId = searchParams.get("task_id");
  const sql = getDb();

  if (!sql) return NextResponse.json(taskId ? { curve: mockCurve } : { runs: mockRuns });

  try {
    if (taskId) {
      const rows = await sql`
        SELECT id, task_id, candidate, baseline_p99, candidate_p99, cost_estimate,
               correctness_ok, within_noise, decision, created_at
        FROM experiment
        WHERE task_id = ${taskId}
        ORDER BY id`;
      const curve = rows.map((r: any, i: number) => ({ n: i + 1, ...r }));
      return NextResponse.json({ curve });
    }

    const runs = await sql`
      SELECT run_id, task_id, model, state, iterations_done, iterations_target,
             best_p99, started_at, ended_at
      FROM run
      ORDER BY started_at DESC NULLS LAST`;
    return NextResponse.json({ runs });
  } catch {
    return NextResponse.json(taskId ? { curve: mockCurve } : { runs: mockRuns });
  }
}

export async function POST(req: Request) {
  const body = await req.json();

  // Dispatch is an action → MCP → AgentCore Gateway. Until the runtime is deployed
  // there is no edge to call, so we surface that explicitly rather than faking a run.
  if (!hasControlPlane()) {
    return NextResponse.json(
      { error: "Dispatch is unavailable until the AgentCore control-plane runtime is deployed." },
      { status: 503 }
    );
  }

  try {
    const data = await cp<{ run_id: string }>("/runs", {
      method: "POST",
      body: JSON.stringify(body),
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
