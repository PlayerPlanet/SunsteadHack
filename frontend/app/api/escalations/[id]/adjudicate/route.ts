import { NextResponse } from "next/server";
import { cp, hasControlPlane } from "@/lib/api";

export async function POST(req: Request, { params }: { params: { id: string } }) {
  const { decision, rationale } = await req.json();
  if (!["approve", "reject"].includes(decision)) {
    return NextResponse.json({ error: "decision must be approve or reject" }, { status: 400 });
  }

  if (!hasControlPlane()) return NextResponse.json({ ok: true, mock: true });

  try {
    await cp(`/escalations/${params.id}/adjudicate`, {
      method: "POST",
      body: JSON.stringify({ decision, rationale }),
    });
    return NextResponse.json({ ok: true });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
