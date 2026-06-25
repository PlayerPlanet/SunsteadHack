import { NextResponse } from "next/server";
import { cp, hasControlPlane } from "@/lib/api";

const MOCK_TASKS = [
  {
    task_id: "pg-latency-v1",
    objective: "Minimize p99 on title × cast_info production-year join",
    workload_id: "job-prodyear",
    action_space: ["index"],
    default_model: "claude-haiku-4-5-20251001",
    state: "active",
  },
];

// Workloads the backend can actually resolve. The domain-judged ones come from
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
  if (!hasControlPlane()) return NextResponse.json({ tasks: MOCK_TASKS, workloads: KNOWN_WORKLOADS });

  try {
    const tasks = await cp<unknown[]>("/tasks");
    return NextResponse.json({ tasks: tasks ?? [], workloads: KNOWN_WORKLOADS });
  } catch {
    return NextResponse.json({ tasks: MOCK_TASKS, workloads: KNOWN_WORKLOADS });
  }
}

export async function POST(req: Request) {
  const body = await req.json();

  if (!hasControlPlane()) {
    return NextResponse.json({
      task_id: body.task_id ?? `task-${Date.now()}`,
      state: "active",
      mock: true,
    });
  }

  try {
    const spec = {
      task_id: body.task_id,
      objective: body.objective,
      workload_id: body.workload_id,
      action_space: body.action_space ?? ["index"],
      db_ref: body.db_ref ?? "production_db",
      constraints: { max_iterations: body.iterations ?? 10 },
      default_model: body.model ?? "claude-haiku-4-5-20251001",
      state: "active",
    };

    const data = await cp<{ task_id: string }>("/tasks", {
      method: "POST",
      body: JSON.stringify({ spec_json: JSON.stringify(spec) }),
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
