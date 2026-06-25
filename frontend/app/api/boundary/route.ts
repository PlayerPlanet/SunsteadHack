import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { mockBoundaryCurve, mockLongitudinal } from "@/lib/mock";

export async function GET() {
  const db = getDb();
  if (!db) return NextResponse.json({ spatial: mockBoundaryCurve, longitudinal: mockLongitudinal });

  const spatial = await db`
    SELECT
      ROUND(drift_level::numeric, 1) AS drift,
      COUNT(*) FILTER (WHERE decision = 'escalated') * 100.0 / COUNT(*) AS escalation_rate,
      COUNT(*) FILTER (WHERE decision = 'keep') * 100.0 / NULLIF(COUNT(*) FILTER (WHERE decision != 'escalated'), 0) AS correctness,
      COUNT(*) AS n
    FROM experiment
    GROUP BY ROUND(drift_level::numeric, 1)
    ORDER BY drift
  `;

  const longitudinal = await db`
    SELECT
      ROW_NUMBER() OVER (ORDER BY created_at) * 10 AS volume,
      COUNT(*) FILTER (WHERE decision = 'escalated') OVER (ORDER BY created_at ROWS UNBOUNDED PRECEDING) AS escalations_frozen
    FROM experiment
    WHERE ROW_NUMBER() OVER (ORDER BY created_at) % 10 = 0
  `;

  return NextResponse.json({
    spatial: spatial.map((r) => ({
      drift: Number(r.drift),
      escalation_rate: Number(r.escalation_rate ?? 0),
      correctness: Number(r.correctness ?? 0),
      n: Number(r.n),
    })),
    longitudinal: mockLongitudinal,
  });
}
