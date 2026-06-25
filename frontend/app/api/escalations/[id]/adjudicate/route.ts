import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { roleFromGroups, canAdjudicate } from "@/lib/roles";
import { callControlTool } from "@/lib/control";

// Adjudication is a privileged mutation, so it does NOT write the DB directly (and does
// not use the unauthenticated control-plane shim). It goes through the deployed AgentCore
// runtime with the user's Cognito bearer, which enforces the control:adjudicate scope and
// SET ROLE sunstead_operator in Postgres. The browser-side gate (canAdjudicate) is UX
// only; this server check + the runtime are the real enforcement.
export const runtime = "nodejs"; // MCP client + Aiven egress aren't Edge-safe

export async function POST(req: Request, { params }: { params: { id: string } }) {
  const session = await auth();
  if (!session?.accessToken) {
    return NextResponse.json({ error: "sign in required" }, { status: 401 });
  }
  const role = roleFromGroups(session.groups);
  if (!canAdjudicate(role)) {
    return NextResponse.json(
      { error: "operator role required to adjudicate (you are a viewer)" },
      { status: 403 },
    );
  }

  const { decision, rationale } = await req.json();
  if (!["approve", "reject"].includes(decision)) {
    return NextResponse.json({ error: "decision must be approve or reject" }, { status: 400 });
  }

  try {
    const res = await callControlTool(session.accessToken, "adjudicate", {
      crossing_id: Number(params.id),
      decision,
      rationale: rationale ?? null,
      judge: session.user?.email ?? "operator",
    });
    if (res.isError) {
      // Distinguish an authorization refusal from a downstream failure for the client.
      const status = /scope|role|denied|permission|forbidden/i.test(res.text) ? 403 : 502;
      return NextResponse.json({ error: res.text || "adjudicate failed" }, { status });
    }
    return NextResponse.json({ ok: true });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ error: `control plane unreachable: ${msg}` }, { status: 502 });
  }
}
