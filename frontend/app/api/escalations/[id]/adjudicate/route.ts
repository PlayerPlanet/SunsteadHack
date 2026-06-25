import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export async function POST(req: Request, { params }: { params: { id: string } }) {
  const { decision, rationale } = await req.json();
  if (!["approve", "reject"].includes(decision)) {
    return NextResponse.json({ error: "decision must be approve or reject" }, { status: 400 });
  }

  const db = getDb();
  if (!db) {
    return NextResponse.json({ ok: true, mock: true });
  }

  await db`
    INSERT INTO judgment (crossing_id, judge, judge_kind, decision, rationale)
    VALUES (${params.id}, 'operator', 'human', ${decision}, ${rationale ?? null})
  `;

  return NextResponse.json({ ok: true });
}
