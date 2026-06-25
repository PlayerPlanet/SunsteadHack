import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { mockRuns, mockExperiments } from "@/lib/mock";

export async function GET(req: Request) {
  const db = getDb();
  const { searchParams } = new URL(req.url);
  const taskId = searchParams.get("task_id");

  if (!db) {
    if (taskId) return NextResponse.json({ experiments: mockExperiments });
    return NextResponse.json({ runs: mockRuns });
  }

  if (taskId) {
    const experiments = await db`
      SELECT
        ROW_NUMBER() OVER (ORDER BY created_at) AS n,
        candidate_p99 AS p99,
        decision,
        candidate->>'type' AS action
      FROM experiment
      WHERE task_id = ${taskId}
      ORDER BY created_at
    `;
    return NextResponse.json({
      experiments: experiments.map((r) => ({
        n: Number(r.n),
        p99: r.p99 ? Number(r.p99) : null,
        decision: r.decision,
        action: r.action,
      })),
    });
  }

  const runs = await db`SELECT * FROM run ORDER BY started_at DESC LIMIT 20`;
  return NextResponse.json({ runs });
}
