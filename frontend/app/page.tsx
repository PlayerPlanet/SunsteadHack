"use client";
import { useEffect, useState } from "react";
import StatCard from "@/components/StatCard";
import BoundaryChart from "@/components/BoundaryChart";
import Link from "next/link";

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
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-white">Dashboard</h1>
        <p className="text-sm text-neutral-500 mt-1">
          Autonomous actions, measured boundaries, escalations routed to you.
        </p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Experiments run"
          value={stats ? stats.totalExperiments.toLocaleString() : "—"}
          sub="all domains"
        />
        <StatCard
          label="Best p99"
          value={stats?.bestP99 ? `${stats.bestP99.toFixed(1)}ms` : "—"}
          sub={p99Improvement ? `${p99Improvement}% below baseline` : undefined}
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
          accent={stats?.activeRuns > 0 ? "green" : "neutral"}
        />
      </div>

      {/* Boundary chart + runs list */}
      <div className="grid md:grid-cols-3 gap-6">
        <div className="md:col-span-2 bg-card border border-border rounded-lg p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-medium text-white">Autonomy boundary</h2>
              <p className="text-xs text-neutral-500 mt-0.5">
                Escalation rate + autonomous correctness vs. workload drift
              </p>
            </div>
            <Link href="/boundary" className="text-xs text-neutral-500 hover:text-neutral-300">
              Full view →
            </Link>
          </div>
          {boundary ? (
            <BoundaryChart data={boundary.spatial} />
          ) : (
            <div className="h-80 flex items-center justify-center text-neutral-600 text-sm">Loading…</div>
          )}
          <p className="text-xs text-neutral-600 mt-3">
            Proxy: frozen pore gates blast-radius + irreversibility — a lower bound on the true epistemic edge.
          </p>
        </div>

        <div className="bg-card border border-border rounded-lg p-5">
          <h2 className="text-sm font-medium text-white mb-4">Recent runs</h2>
          <div className="space-y-3">
            {runs.slice(0, 6).map((r) => (
              <div key={r.run_id} className="flex items-start gap-3">
                <span
                  className={`mt-1 w-2 h-2 rounded-full flex-shrink-0 ${
                    r.state === "running"
                      ? "bg-emerald-500 animate-pulse"
                      : r.state === "completed"
                      ? "bg-neutral-500"
                      : "bg-red-500"
                  }`}
                />
                <div className="min-w-0">
                  <p className="text-sm text-neutral-200 truncate">{r.task_id}</p>
                  <p className="text-xs text-neutral-500">
                    {r.iterations_done}/{r.iterations_target} iter
                    {r.best_p99 ? ` · ${r.best_p99.toFixed(1)}ms` : ""}
                  </p>
                </div>
                <Link
                  href={`/runs?task=${r.task_id}`}
                  className="ml-auto text-xs text-neutral-600 hover:text-neutral-400 flex-shrink-0"
                >
                  →
                </Link>
              </div>
            ))}
          </div>
          <Link href="/runs" className="block mt-4 text-xs text-neutral-500 hover:text-neutral-300">
            All runs →
          </Link>
        </div>
      </div>

      {/* Thesis callout */}
      <div className="border border-border rounded-lg p-5 bg-card">
        <p className="text-sm text-neutral-400 leading-relaxed max-w-3xl">
          <span className="text-white">The trustworthy region</span> is where the agent acts alone and the judge confirms it was right.
          The <span className="text-amber-400">boundary</span> is where either escalation spikes or autonomous correctness falls off.
          It is drawn from data — not asserted.{" "}
          <Link href="/boundary" className="text-neutral-500 hover:text-neutral-300 underline underline-offset-2">
            See the full instrument →
          </Link>
        </p>
      </div>
    </div>
  );
}
