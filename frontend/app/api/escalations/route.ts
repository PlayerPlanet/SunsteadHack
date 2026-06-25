import { NextResponse } from "next/server";
import { callControlJson, requireBearer, errToResponse } from "@/lib/control";

// Pending escalations via the AgentCore edge API (NOT direct Postgres): crossings the
// frozen pore routed to a human (requires_human_judgment). The user's bearer is forwarded;
// the runtime enforces read scope + SET ROLE.
export const runtime = "nodejs";

export async function GET() {
  try {
    const bearer = await requireBearer();
    const crossings = await callControlJson<any[]>(bearer, "pending_escalations", {});
    const escalations = (crossings ?? []).map((c: any) => ({
      id: c.id,
      pore: c.pore,
      risk_level: String(c.risk_level ?? "").toUpperCase(),
      // run_loop logs crossings as action = { candidate: {type, params, reversible} };
      // the UI expects {type, params}, so unwrap the candidate when present.
      action: c.action?.candidate ?? c.action,
      created_at: c.created_at,
      // pending_escalations returns only un-adjudicated crossings, so no judgment yet.
      judgment: null,
    }));
    return NextResponse.json({ escalations });
  } catch (e) {
    return errToResponse(e);
  }
}
