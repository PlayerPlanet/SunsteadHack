import { NextResponse } from "next/server";
import { callControlJson, allExperiments, requireBearer, errToResponse } from "@/lib/control";

// Dashboard stat cards via the AgentCore edge API (NOT direct Postgres). The runtime has
// no single aggregate tool, so we derive the figures from edge primitives: list_runs for
// active-run count and the experiments (read through the edge) for the rest.
export const runtime = "nodejs";

export async function GET() {
  try {
    const bearer = await requireBearer();
    const [runs, exps] = await Promise.all([
      callControlJson<any[]>(bearer, "list_runs", {}),
      allExperiments(bearer),
    ]);

    const total = exps.length;
    const keeps = exps
      .filter((e) => e.decision === "keep" && e.candidate_p99 != null)
      .map((e) => Number(e.candidate_p99));
    const baselines = exps
      .filter((e) => e.baseline_p99 != null)
      .map((e) => Number(e.baseline_p99));
    const escalated = exps.filter((e) => e.decision === "escalated").length;
    const activeRuns = (runs ?? []).filter((r: any) => r.state === "running").length;

    return NextResponse.json({
      totalExperiments: total,
      bestP99: keeps.length ? Math.min(...keeps) : null,
      baselineP99: baselines.length ? Math.max(...baselines) : null,
      activeRuns,
      escalationRate: total ? (escalated / total) * 100 : 0,
    });
  } catch (e) {
    return errToResponse(e);
  }
}
