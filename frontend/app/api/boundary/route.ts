import { NextResponse } from "next/server";
import { allExperiments, requireBearer, errToResponse } from "@/lib/control";

// Boundary instrument via the AgentCore edge API (NOT direct Postgres). The runtime's
// read_boundary tool only exposes escalation-rate-by-drift (no correctness line), so we
// reconstruct both readings from the experiments read through the edge (read_curve carries
// drift_level + correctness_ok + decision):
//   spatial      — escalation rate + autonomous correctness vs workload drift
//   longitudinal — cumulative escalations vs experiment volume (flat with the frozen pore)
export const runtime = "nodejs";

const PROXY_CAVEAT =
  "Pore gates blast-radius + reversibility — a lower bound on, not identical to, the agent's true epistemic edge.";

export async function GET() {
  try {
    const bearer = await requireBearer();
    const exps = await allExperiments(bearer);
    if (exps.length === 0) {
      return NextResponse.json({ spatial: [], longitudinal: [], proxy_caveat: PROXY_CAVEAT });
    }

    // spatial: group by drift_level. correctness is over NON-escalated experiments only,
    // matching the original SQL (count correctness_ok among decision <> 'escalated').
    const byDrift = new Map<number, { esc: number; corrOk: number; corrDenom: number; n: number }>();
    for (const e of exps) {
      const d = Number(e.drift_level ?? 0);
      const g = byDrift.get(d) ?? { esc: 0, corrOk: 0, corrDenom: 0, n: 0 };
      g.n += 1;
      if (e.decision === "escalated") {
        g.esc += 1;
      } else {
        g.corrDenom += 1;
        if (e.correctness_ok === true) g.corrOk += 1;
      }
      byDrift.set(d, g);
    }
    const spatial = [...byDrift.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([drift, g]) => ({
        drift,
        escalation_rate: g.n ? (g.esc / g.n) * 100 : 0,
        correctness: g.corrDenom ? (g.corrOk / g.corrDenom) * 100 : 0,
        n: g.n,
      }));

    // longitudinal: cumulative escalations over experiment volume, ordered by id.
    // No learned membrane on this data, so escalations_membrane is honestly omitted.
    const ordered = [...exps].sort((a, b) => Number(a.id ?? 0) - Number(b.id ?? 0));
    let cum = 0;
    const longitudinal = ordered.map((e, i) => {
      if (e.decision === "escalated") cum += 1;
      return { volume: i + 1, escalations_frozen: cum };
    });

    return NextResponse.json({ spatial, longitudinal, proxy_caveat: PROXY_CAVEAT });
  } catch (e) {
    return errToResponse(e);
  }
}
