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

const KNOWN_WORKLOADS = ["job-prodyear", "__default__"];

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
