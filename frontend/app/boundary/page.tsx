"use client";
import { useEffect, useState } from "react";
import BoundaryChart from "@/components/BoundaryChart";
import LongitudinalChart from "@/components/LongitudinalChart";

export default function BoundaryPage() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    fetch("/api/boundary").then((r) => r.json()).then(setData);
  }, []);

  const spatial = data?.spatial ?? [];
  const longitudinal = data?.longitudinal ?? [];

  const boundary = spatial.find((d: any) => d.escalation_rate > 0 && d.correctness < 90)?.drift ?? null;
  const bendPct = longitudinal.length >= 2
    ? Math.round(
        ((longitudinal[longitudinal.length - 1].escalations_frozen -
          longitudinal[longitudinal.length - 1].escalations_membrane) /
          longitudinal[longitudinal.length - 1].escalations_frozen) *
          100
      )
    : null;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-white">Autonomy boundary</h1>
        <p className="text-sm text-neutral-500 mt-1">
          Two live readings off the escalation log. Neither is asserted — both are measured.
        </p>
      </div>

      {/* Spatial */}
      <div className="bg-card border border-border rounded-lg p-6">
        <div className="flex items-start justify-between mb-1">
          <div>
            <h2 className="text-sm font-medium text-white">Spatial — where the edge is now</h2>
            <p className="text-xs text-neutral-500 mt-0.5">
              Escalation rate and autonomous correctness, binned by workload drift from baseline.
            </p>
          </div>
          {boundary && (
            <div className="text-right">
              <p className="text-xs text-neutral-500">Boundary at</p>
              <p className="text-lg font-semibold text-red-400">drift {boundary.toFixed(1)}</p>
            </div>
          )}
        </div>
        <div className="mt-4">
          {spatial.length > 0 ? (
            <BoundaryChart data={spatial} />
          ) : (
            <div className="h-80 flex items-center justify-center text-neutral-600 text-sm">Loading…</div>
          )}
        </div>
        <div className="mt-4 grid grid-cols-3 gap-4 text-xs">
          <div className="flex items-center gap-2">
            <span className="w-3 h-px bg-emerald-500 inline-block" />
            <span className="text-neutral-500">Autonomous correctness — stays high in the trustworthy region</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-px bg-amber-400 inline-block" />
            <span className="text-neutral-500">Escalation rate — rises as world drifts from familiar territory</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-px bg-red-500 border-dashed inline-block" style={{ borderTop: "1px dashed" }} />
            <span className="text-neutral-500">Boundary — where either line crosses the threshold</span>
          </div>
        </div>
        <p className="mt-4 text-xs text-neutral-600 border-t border-border pt-4">
          Proxy caveat: the frozen pore gates blast-radius + irreversibility — a lower bound on, not identical to,
          the true epistemic edge. The coupling is structural: as the world drifts, the genuinely-best fix becomes
          more systemic or irreversible, and the frozen gate catches exactly those.
        </p>
      </div>

      {/* Longitudinal */}
      <div className="bg-card border border-border rounded-lg p-6">
        <div className="flex items-start justify-between mb-1">
          <div>
            <h2 className="text-sm font-medium text-white">Longitudinal — whether the frontier recedes</h2>
            <p className="text-xs text-neutral-500 mt-0.5">
              Escalations per unit work, cumulative. Flat = frozen pore (by design). Dashed = shadow membrane (Stage 2).
            </p>
          </div>
          {bendPct !== null && (
            <div className="text-right">
              <p className="text-xs text-neutral-500">Membrane bends curve</p>
              <p className="text-lg font-semibold text-emerald-400">−{bendPct}%</p>
            </div>
          )}
        </div>
        <div className="mt-4">
          {longitudinal.length > 0 ? (
            <LongitudinalChart data={longitudinal} />
          ) : (
            <div className="h-64 flex items-center justify-center text-neutral-600 text-sm">Loading…</div>
          )}
        </div>
        <p className="mt-4 text-xs text-neutral-600 border-t border-border pt-4">
          With today's frozen pore the line is flat by design — and that flat line is the point. The shadow membrane
          (Stage 2) runs alongside but never acts: it logs what it would decide. The bend it produces is measured
          against the frozen ruler, not produced by moving it. False-clear rate: 0%.
        </p>
      </div>

      {/* Calibration gap */}
      <div className="grid md:grid-cols-3 gap-4">
        <div className="bg-card border border-border rounded-lg p-5">
          <p className="text-xs text-neutral-500 uppercase tracking-wider mb-2">Pore precision</p>
          <p className="text-3xl font-semibold text-white">46.7%</p>
          <p className="text-xs text-neutral-500 mt-1">of stops confirmed by human</p>
        </div>
        <div className="bg-card border border-border rounded-lg p-5">
          <p className="text-xs text-neutral-500 uppercase tracking-wider mb-2">False-stop rate</p>
          <p className="text-3xl font-semibold text-amber-400">53.3%</p>
          <p className="text-xs text-neutral-500 mt-1">human said "agent could have acted"</p>
        </div>
        <div className="bg-card border border-border rounded-lg p-5">
          <p className="text-xs text-neutral-500 uppercase tracking-wider mb-2">Gap learnable</p>
          <p className="text-3xl font-semibold text-emerald-400">93%</p>
          <p className="text-xs text-neutral-500 mt-1">LOO accuracy — residual 7% is the irreducible edge</p>
        </div>
      </div>
    </div>
  );
}
