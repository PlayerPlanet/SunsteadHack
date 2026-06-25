"use client";
import { useEffect, useState } from "react";
import StatCard from "@/components/StatCard";
import BoundaryChart from "@/components/BoundaryChart";
import TopBar from "@/components/TopBar";
import Link from "next/link";
import { ArrowRight, Circle } from "lucide-react";

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  const [boundary, setBoundary] = useState<any>(null);
  const [runs, setRuns] = useState<any[]>([]);

  useEffect(() => {
    fetch("/api/stats").then((r) => r.json()).then(setStats);
    fetch("/api/boundary").then((r) => r.json()).then(setBoundary);
    fetch("/api/runs").then((r) => r.json()).then((d) => setRuns(d.runs ?? []));
  }, []);

  const p99Improvement = stats?.bestP99 && stats?.baselineP99
    ? Math.round(((stats.baselineP99 - stats.bestP99) / stats.baselineP99) * 100)
    : null;

  return (
    <>
      <TopBar title="Dashboard" />
      <main className="flex-1 p-6 space-y-6 overflow-y-auto">

        {/* Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Experiments run"
            value={stats ? stats.totalExperiments.toLocaleString() : "—"}
            sub="all domains"
          />
          <StatCard
            label="Best p99"
            value={stats?.bestP99 ? `${stats.bestP99.toFixed(1)}ms` : "—"}
            sub={p99Improvement ? `−${p99Improvement}% vs baseline` : undefined}
            accent="green"
          />
          <StatCard
            label="Escalation rate"
            value={stats ? `${stats.escalationRate.toFixed(1)}%` : "—"}
            sub="of all experiments"
            accent={stats?.escalationRate > 20 ? "amber" : "neutral"}
          />
          <StatCard
            label="Active runs"
            value={stats ? String(stats.activeRuns) : "—"}
            sub={stats?.activeRuns > 0 ? "running now" : "idle"}
            accent={stats?.activeRuns > 0 ? "navy" : "neutral"}
          />
        </div>

        {/* Boundary + Runs */}
        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 bg-white border border-gray-200 rounded-xl shadow-sm">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div>
                <h2 className="text-sm font-semibold text-gray-900">Autonomy boundary</h2>
                <p className="text-xs text-gray-400 mt-0.5">Escalation rate + correctness vs. workload drift</p>
              </div>
              <Link href="/boundary" className="flex items-center gap-1 text-xs text-navy font-medium hover:underline">
                Full view <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="p-4">
              {boundary ? (
                <BoundaryChart data={boundary.spatial} />
              ) : (
                <div className="h-72 flex items-center justify-center text-gray-300 text-sm">Loading…</div>
              )}
            </div>
            <div className="px-6 pb-4">
              <p className="text-xs text-gray-400">
                Proxy: frozen pore gates blast-radius + irreversibility — a lower bound on the true epistemic edge.
              </p>
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl shadow-sm">
            <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-900">Active runs</h2>
              <Link href="/runs" className="text-xs text-navy font-medium hover:underline">All →</Link>
            </div>
            <div className="divide-y divide-gray-100">
              {runs.slice(0, 6).map((r) => (
                <div key={r.run_id} className="flex items-center gap-3 px-5 py-3 hover:bg-gray-50 transition-colors">
                  <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                    r.state === "running" ? "bg-emerald-500" : r.state === "completed" ? "bg-gray-300" : "bg-red-400"
                  }`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-800 font-medium truncate">{r.task_id}</p>
                    <p className="text-xs text-gray-400">
                      {r.iterations_done}/{r.iterations_target} iter
                      {r.best_p99 ? ` · ${r.best_p99.toFixed(1)}ms` : ""}
                    </p>
                  </div>
                  <Link href={`/runs?task=${r.task_id}`} className="text-gray-300 hover:text-navy transition-colors">
                    <ArrowRight className="w-3.5 h-3.5" />
                  </Link>
                </div>
              ))}
              {runs.length === 0 && (
                <div className="px-5 py-8 text-center text-gray-400 text-sm">No runs yet</div>
              )}
            </div>
          </div>
        </div>

        {/* Thesis callout */}
        <div className="bg-navy rounded-xl p-6">
          <p className="text-sm text-blue-100 leading-relaxed max-w-3xl">
            <span className="text-white font-semibold">The trustworthy region</span> is where the agent acts alone and the judge confirms it was right.
            The <span className="text-amber-300">boundary</span> is where either escalation spikes or autonomous correctness falls off.
            It is drawn from data — not asserted.{" "}
            <Link href="/boundary" className="text-blue-200 hover:text-white underline underline-offset-2 transition-colors">
              See the full instrument →
            </Link>
          </p>
        </div>

      </main>
    </>
  );
}
