import { NextResponse } from "next/server";
import { cp, hasControlPlane } from "@/lib/api";
import { mockRuns, mockCurve } from "@/lib/mock";

// GET /api/runs                   — list runs
// GET /api/runs?task_id=X         — curve for task
// POST /api/runs                  — dispatch a new run
export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const taskId = searchParams.get("task_id");

  if (!hasControlPlane()) {
    if (taskId) return NextResponse.json({ curve: mockCurve });
    return NextResponse.json({ runs: mockRuns });
  }

  try {
    if (taskId) {
      const curve = await cp<unknown[]>(`/tasks/${taskId}/curve`);
      // Normalize: add sequential index, keep all handoff fields
      const normalized = (curve ?? []).map((row: any, i: number) => ({ n: i + 1, ...row }));
      return NextResponse.json({ curve: normalized });
    }

    const runs = await cp<unknown[]>("/runs");
    return NextResponse.json({ runs: runs ?? [] });
  } catch {
    if (taskId) return NextResponse.json({ curve: mockCurve });
    return NextResponse.json({ runs: mockRuns });
  }
}

export async function POST(req: Request) {
  const body = await req.json();

  if (!hasControlPlane()) {
    return NextResponse.json({ run_id: `mock-run-${Date.now()}` });
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
