import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { mockEscalations } from "@/lib/mock";

// Reads → pg → Aiven sunstead_control (BFF design): crossings the frozen pore routed
// to a human (requires_human_judgment), with any judgment joined in. Mirrors
// Operator.pending_escalations but also surfaces decided ones for the "Decided" panel.
export const runtime = "nodejs";

export async function GET() {
  const sql = getDb();
  if (!sql) return NextResponse.json({ escalations: mockEscalations });

  try {
    const rows = await sql`
      SELECT c.id, c.pore, upper(c.risk_level) AS risk_level, c.action, c.created_at,
             j.decision AS j_decision, j.judge_kind AS j_judge_kind, j.rationale AS j_rationale
      FROM crossing c
      LEFT JOIN judgment j ON j.crossing_id = c.id
      WHERE c.requires_human_judgment = true
      ORDER BY c.created_at DESC`;

    const escalations = rows.map((r: any) => ({
      id: r.id,
      pore: r.pore,
      risk_level: r.risk_level,
      // run_loop logs crossings as action = { candidate: {type, params, reversible} };
      // the UI expects {type, params}, so unwrap the candidate when present.
      action: r.action?.candidate ?? r.action,
      created_at: r.created_at,
      judgment: r.j_decision
        ? { decision: r.j_decision, judge_kind: r.j_judge_kind, rationale: r.j_rationale }
        : null,
    }));

    return NextResponse.json({ escalations });
  } catch {
    return NextResponse.json({ escalations: mockEscalations });
  }
}
