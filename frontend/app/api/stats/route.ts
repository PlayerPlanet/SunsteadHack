import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { mockStats } from "@/lib/mock";

// Reads → pg → Aiven sunstead_control (BFF design). Falls back to mock when no DB.
export const runtime = "nodejs";

export async function GET() {
  const sql = getDb();
  if (!sql) return NextResponse.json(mockStats);

  try {
    const [agg] = await sql`
      SELECT
        (SELECT count(*) FROM experiment)::int                                AS total_experiments,
        (SELECT min(candidate_p99) FROM experiment WHERE decision = 'keep')   AS best_p99,
        (SELECT max(baseline_p99) FROM experiment)                            AS baseline_p99,
        (SELECT count(*) FROM run WHERE state = 'running')::int               AS active_runs,
        (SELECT count(*) FROM experiment WHERE decision = 'escalated')::int   AS escalated
    `;
    const total = Number(agg.total_experiments) || 0;
    return NextResponse.json({
      totalExperiments: total,
      bestP99: agg.best_p99 != null ? Number(agg.best_p99) : null,
      baselineP99: agg.baseline_p99 != null ? Number(agg.baseline_p99) : null,
      activeRuns: Number(agg.active_runs) || 0,
      escalationRate: total ? (Number(agg.escalated) / total) * 100 : 0,
    });
  } catch {
    return NextResponse.json(mockStats);
  }
}
