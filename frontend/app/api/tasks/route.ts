import { NextResponse } from "next/server";
import { callControlJson, requireBearer, errToResponse } from "@/lib/control";

// Tasks via the AgentCore edge API (NOT direct Postgres):
//   GET  /api/tasks  — list_tasks (active tasks) + the static workload catalog
//   POST /api/tasks  — register_task (governance-gated; the frozen pore may hold it)
// The user's bearer is forwarded; register requires the control:register scope.
export const runtime = "nodejs";

// Workloads the backend can resolve. The domain-judged ones come from
// cleanroom.control.domains._BUILDERS; job-prodyear is the Postgres/JOB index task;
// __default__ is the canned benchmark. Keep ids in sync with that registry.
const KNOWN_WORKLOADS = [
  { id: "job-prodyear", label: "Postgres · JOB production-year join" },
  { id: "kernel_matmul_32", label: "Kernel · 32×32 matmul latency" },
  { id: "quant_walkforward_momentum", label: "Quant · walk-forward momentum Sharpe" },
  { id: "bio_molclass_f1", label: "Bio · molecular-property F1" },
  { id: "byo_agent_demo", label: "BYO-agent · demo loop" },
  { id: "bond_extraction", label: "Bond extraction · field F1" },
  { id: "__default__", label: "Default · canned benchmark" },
];

export async function GET() {
  try {
    const bearer = await requireBearer();
    const tasks = await callControlJson<any[]>(bearer, "list_tasks", {});
    return NextResponse.json({ tasks: tasks ?? [], workloads: KNOWN_WORKLOADS });
  } catch (e) {
    return errToResponse(e);
  }
}

export async function POST(req: Request) {
  const body = await req.json();
  try {
    const bearer = await requireBearer();
    const spec = {
      task_id: body.task_id,
      objective: body.objective,
      workload_id: body.workload_id,
      action_space: body.action_space ?? ["index"],
      db_ref: body.db_ref ?? "production_db",
      constraints: { max_iterations: body.iterations ?? 10 },
      default_model: body.model ?? "claude-haiku-4-5-20251001",
    };
    const task_id = await callControlJson<string>(bearer, "register_task", {
      spec_json: JSON.stringify(spec),
    });
    // register_task returns only the id; the spec has no state field. Detect a governance
    // hold by checking whether the frozen pore routed this registration to human review.
    let state = "active";
    try {
      const pending = await callControlJson<any[]>(bearer, "pending_escalations", {});
      if ((pending ?? []).some((c: any) => c.action?.register_task?.task_id === task_id)) {
        state = "pending_judgment";
      }
    } catch {
      /* non-fatal: fall back to optimistic 'active' */
    }
    return NextResponse.json({ task_id, state });
  } catch (e) {
    return errToResponse(e);
  }
}
