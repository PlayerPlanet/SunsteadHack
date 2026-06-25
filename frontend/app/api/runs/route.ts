import { NextResponse } from "next/server";
import { callControlJson, requireBearer, errToResponse } from "@/lib/control";

// Runs + descent curve via the AgentCore edge API (NOT direct Postgres):
//   GET /api/runs            — list_runs   (RunStatus[])
//   GET /api/runs?task_id=X   — read_curve  (experiment[] for the descent chart)
//   POST /api/runs            — dispatch_run (enqueues; the runtime's worker runs the loop)
// Every call forwards the user's Cognito bearer; the runtime enforces scope + SET ROLE.
export const runtime = "nodejs"; // MCP client egress isn't Edge-safe

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const taskId = searchParams.get("task_id");
  try {
    const bearer = await requireBearer();
    if (taskId) {
      const exps = await callControlJson<any[]>(bearer, "read_curve", { task_id: taskId });
      const curve = (exps ?? []).map((r, i) => ({ n: i + 1, ...r }));
      return NextResponse.json({ curve });
    }
    const runs = await callControlJson<any[]>(bearer, "list_runs", {});
    return NextResponse.json({ runs: runs ?? [] });
  } catch (e) {
    return errToResponse(e);
  }
}

export async function POST(req: Request) {
  const body = await req.json();
  if (!body.task_id) {
    return NextResponse.json({ error: "task_id is required" }, { status: 400 });
  }
  try {
    const bearer = await requireBearer();
    const run_id = await callControlJson<string>(bearer, "dispatch_run", {
      task_id: body.task_id,
      model: body.model ?? "claude-haiku-4-5-20251001",
      iterations: Number(body.iterations ?? 4),
    });
    return NextResponse.json({ run_id, state: "queued" });
  } catch (e) {
    return errToResponse(e);
  }
}
