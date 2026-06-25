import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { mockStats } from "@/lib/mock";

export async function GET() {
  const db = getDb();
  if (!db) return NextResponse.json(mockStats);

  const [counts] = await db`
    SELECT
      COUNT(*) AS total_experiments,
      COUNT(*) FILTER (WHERE decision = 'escalated') AS total_escalations,
      MIN(candidate_p99) FILTER (WHERE decision = 'keep') AS best_p99,
      AVG(baseline_p99) FILTER (WHERE baseline_p99 IS NOT NULL) AS baseline_p99,
      COUNT(*) FILTER (WHERE decision = 'keep') * 100.0 / NULLIF(COUNT(*) FILTER (WHERE decision != 'escalated'), 0) AS autonomous_correctness
    FROM experiment
  `;
  const [runs] = await db`SELECT COUNT(*) FILTER (WHERE state = 'running') AS active FROM run`;

  return NextResponse.json({
    totalExperiments: Number(counts.total_experiments),
    activeRuns: Number(runs.active),
    bestP99: counts.best_p99 ? Number(counts.best_p99) : null,
    baselineP99: counts.baseline_p99 ? Number(counts.baseline_p99) : null,
    escalationRate: counts.total_experiments > 0
      ? (Number(counts.total_escalations) / Number(counts.total_experiments)) * 100
      : 0,
    autonomousCorrectness: counts.autonomous_correctness ? Number(counts.autonomous_correctness) : null,
  });
}
