"use client";
import { useEffect, useState } from "react";
import BoundaryChart from "@/components/BoundaryChart";
import LongitudinalChart from "@/components/LongitudinalChart";
import TopBar from "@/components/TopBar";

export default function BoundaryPage() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    fetch("/api/boundary").then((r) => r.json()).then(setData);
  }, []);

  const spatial = data?.spatial ?? [];
  const longitudinal = data?.longitudinal ?? [];
  const boundary = spatial.find((d: any) => d.escalation_rate > 0 && d.correctness < 90)?.drift ?? null;
  const last = longitudinal[longitudinal.length - 1];
  const bendPct = last
    ? Math.round(((last.escalations_frozen - last.escalations_membrane) / last.escalations_frozen) * 100)
    : null;

  return (
    <>
      <TopBar title="Autonomy Boundary" />
      <main className="flex-1 p-6 space-y-6 overflow-y-auto">

        {/* Calibration gap strip */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Pore precision", value: "46.7%", sub: "stops confirmed by human", color: "text-gray-900" },
            { label: "False-stop rate", value: "53.3%", sub: "human said agent could have acted", color: "text-amber-600" },
            { label: "Gap learnable", value: "93%", sub: "LOO accuracy · 7% is irreducible", color: "text-emerald-600" },
          ].map((s) => (
            <div key={s.label} className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
              <p className="text-xs text-gray-500 uppercase tracking-wide font-medium mb-1">{s.label}</p>
              <p className={`text-3xl font-semibold tabular-nums ${s.color}`}>{s.value}</p>
              <p className="text-xs text-gray-400 mt-1">{s.sub}</p>
            </div>
          ))}
        </div>

        {/* Spatial */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm">
          <div className="flex items-start justify-between px-6 py-4 border-b border-gray-100">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Spatial — where the edge is now</h2>
              <p className="text-xs text-gray-400 mt-0.5">Escalation rate and autonomous correctness, binned by workload drift.</p>
            </div>
            {boundary && (
              <div className="text-right">
                <p className="text-xs text-gray-400">Boundary at</p>
                <p className="text-xl font-semibold text-red-500">drift {boundary.toFixed(1)}</p>
              </div>
            )}
          </div>
          <div className="p-4">
            {spatial.length > 0
              ? <BoundaryChart data={spatial} />
              : <div className="h-72 flex items-center justify-center text-gray-300 text-sm">Loading…</div>}
          </div>
          <div className="px-6 pb-5">
            <div className="flex gap-6 text-xs text-gray-400">
              <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-emerald-500 inline-block rounded" /> Autonomous correctness</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-amber-400 inline-block rounded" /> Escalation rate</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-red-400 inline-block rounded border-dashed" style={{ borderTop: "1px dashed" }} /> Boundary</span>
            </div>
            <p className="mt-3 text-xs text-gray-400 border-t border-gray-100 pt-3">
              Proxy caveat: the frozen pore gates blast-radius + irreversibility — a lower bound on, not identical to, the true epistemic edge.
            </p>
          </div>
        </div>

        {/* Longitudinal */}
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm">
          <div className="flex items-start justify-between px-6 py-4 border-b border-gray-100">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Longitudinal — whether the frontier recedes</h2>
              <p className="text-xs text-gray-400 mt-0.5">Escalations per unit work. Flat = frozen pore (by design). Dashed = shadow membrane (Stage 2).</p>
            </div>
            {bendPct !== null && (
              <div className="text-right">
                <p className="text-xs text-gray-400">Membrane bends curve</p>
                <p className="text-xl font-semibold text-navy">−{bendPct}%</p>
              </div>
            )}
          </div>
          <div className="p-4">
            {longitudinal.length > 0
              ? <LongitudinalChart data={longitudinal} />
              : <div className="h-56 flex items-center justify-center text-gray-300 text-sm">Loading…</div>}
          </div>
          <div className="px-6 pb-5">
            <p className="text-xs text-gray-400 border-t border-gray-100 pt-3">
              The shadow membrane runs alongside but never acts. The bend it produces is measured against the frozen ruler, not produced by moving it. False-clear rate: 0%.
            </p>
          </div>
        </div>

      </main>
    </>
  );
}
