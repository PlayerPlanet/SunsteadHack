import { NextResponse } from "next/server";
import { randomUUID } from "crypto";
import { getDb } from "@/lib/db";
import { mockRuns, mockCurve } from "@/lib/mock";

// Reads → pg → Aiven sunstead_control (BFF design):
//   GET /api/runs                — list runs       (run table)
//   GET /api/runs?task_id=X       — descent curve   (experiment table)
// Dispatch → web/worker split: the web tier ENQUEUES a run (state='queued'); a worker
// process (`python -m cleanroom.control.worker`) claims it via run_queued_idx and runs
// the loop. We never run the loop in a request.
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
  const taskId = body.task_id;
  const model = body.model ?? "claude-haiku-4-5-20251001";
  const iterations = Number(body.iterations ?? 4);
  if (!taskId) {
    return NextResponse.json({ error: "task_id is required" }, { status: 400 });
  }

  const sql = getDb();
  if (!sql) return NextResponse.json({ run_id: `mock-${Date.now()}`, state: "queued", mock: true });

  try {
    const run_id = randomUUID().replace(/-/g, "").slice(0, 12);
    await sql`
      INSERT INTO run (run_id, task_id, model, state, iterations_done, iterations_target)
      VALUES (${run_id}, ${taskId}, ${model}, 'queued', 0, ${iterations})`;
    return NextResponse.json({ run_id, state: "queued" });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
