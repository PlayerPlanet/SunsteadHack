import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { mockEscalations } from "@/lib/mock";

export async function GET() {
  const db = getDb();
  if (!db) return NextResponse.json({ escalations: mockEscalations });

  const rows = await db`
    SELECT
      c.id, c.pore, c.risk_level, c.action, c.created_at,
      j.decision AS judgment_decision, j.judge_kind, j.rationale AS judgment_rationale
    FROM crossing c
    LEFT JOIN judgment j ON j.crossing_id = c.id
    WHERE c.requires_human_judgment = true
    ORDER BY c.created_at DESC
    LIMIT 50
  `;

  return NextResponse.json({
    escalations: rows.map((r) => ({
      id: r.id,
      pore: r.pore,
      risk_level: r.risk_level,
      action: r.action,
      created_at: r.created_at,
      judgment: r.judgment_decision
        ? { decision: r.judgment_decision, judge_kind: r.judge_kind, rationale: r.judgment_rationale }
        : null,
    })),
  });
}
