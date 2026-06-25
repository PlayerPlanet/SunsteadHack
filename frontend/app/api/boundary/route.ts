import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { mockBoundaryCurve, mockLongitudinal } from "@/lib/mock";

// Reads → pg → Aiven sunstead_control (BFF design). Replicates the frozen Story-C
// boundary analysis (cleanroom.boundary) as SQL:
//   spatial      — escalation rate + autonomous correctness vs workload drift
//   longitudinal — cumulative escalations vs experiment volume (flat with the frozen pore)
export const runtime = "nodejs";

const PROXY_CAVEAT =
  "Pore gates blast-radius + reversibility — a lower bound on, not identical to, the agent's true epistemic edge.";

export async function GET() {
  const sql = getDb();
  if (!sql) return NextResponse.json({ spatial: mockBoundaryCurve, longitudinal: mockLongitudinal });

  try {
    const spatialRows = await sql`
      SELECT drift_level                                                          AS drift,
             100.0 * count(*) FILTER (WHERE decision = 'escalated') / count(*)    AS escalation_rate,
             COALESCE(
               100.0 * count(*) FILTER (WHERE correctness_ok IS TRUE)
               / NULLIF(count(*) FILTER (WHERE decision <> 'escalated'), 0), 0)   AS correctness,
             count(*)::int                                                        AS n
      FROM experiment
      GROUP BY drift_level
      ORDER BY drift_level`;

    if (spatialRows.length === 0) {
      return NextResponse.json({ spatial: mockBoundaryCurve, longitudinal: mockLongitudinal });
    }

    const longitudinalRows = await sql`
      SELECT row_number() OVER (ORDER BY id)::int                       AS volume,
             sum((decision = 'escalated')::int) OVER (ORDER BY id)::int AS escalations_frozen
      FROM experiment
      ORDER BY id`;

    const spatial = spatialRows.map((r: any) => ({
      drift: Number(r.drift),
      escalation_rate: Number(r.escalation_rate),
      correctness: Number(r.correctness),
      n: Number(r.n),
    }));
    // No learned membrane deployed on this data, so escalations_membrane is omitted —
    // the "Shadow membrane (Stage 2)" line is honestly absent rather than faked.
    const longitudinal = longitudinalRows.map((r: any) => ({
      volume: Number(r.volume),
      escalations_frozen: Number(r.escalations_frozen),
    }));

    return NextResponse.json({ spatial, longitudinal, proxy_caveat: PROXY_CAVEAT });
  } catch {
    return NextResponse.json({ spatial: mockBoundaryCurve, longitudinal: mockLongitudinal });
  }
}
