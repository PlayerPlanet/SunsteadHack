"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import DescentChart from "@/components/DescentChart";
import { Suspense } from "react";

function RunsContent() {
  const params = useSearchParams();
  const taskId = params.get("task");
  const [runs, setRuns] = useState<any[]>([]);
  const [experiments, setExperiments] = useState<any[]>([]);
  const [selected, setSelected] = useState<string | null>(taskId);

  useEffect(() => {
    fetch("/api/runs").then((r) => r.json()).then((d) => setRuns(d.runs ?? []));
  }, []);

  useEffect(() => {
    if (!selected) return;
    fetch(`/api/runs?task_id=${selected}`).then((r) => r.json()).then((d) => setExperiments(d.experiments ?? []));
  }, [selected]);

  const uniqueTasks = [...new Set(runs.map((r) => r.task_id))];
  const baseline = experiments.find((e) => e.n === 1)?.p99;
  const best = experiments.filter((e) => e.decision === "keep" && e.p99).reduce((acc, e) => Math.min(acc, e.p99), Infinity);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-white">Runs</h1>
        <p className="text-sm text-neutral-500 mt-1">Active and completed optimization runs. Select a task to see its descent curve.</p>
      </div>

      {/* Run list */}
      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left px-4 py-3 text-xs text-neutral-500 font-medium">Task</th>
              <th className="text-left px-4 py-3 text-xs text-neutral-500 font-medium">State</th>
              <th className="text-left px-4 py-3 text-xs text-neutral-500 font-medium">Progress</th>
              <th className="text-left px-4 py-3 text-xs text-neutral-500 font-medium">Best p99</th>
              <th className="text-left px-4 py-3 text-xs text-neutral-500 font-medium">Model</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr
                key={r.run_id}
                onClick={() => setSelected(r.task_id)}
                className={`border-b border-border cursor-pointer transition-colors ${
                  selected === r.task_id ? "bg-white/5" : "hover:bg-white/[0.02]"
                }`}
              >
                <td className="px-4 py-3 text-neutral-200 font-mono text-xs">{r.task_id}</td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex items-center gap-1.5 text-xs ${
                      r.state === "running" ? "text-emerald-400" : r.state === "completed" ? "text-neutral-400" : "text-red-400"
                    }`}
                  >
                    {r.state === "running" && <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />}
                    {r.state}
                  </span>
                </td>
                <td className="px-4 py-3 text-neutral-400 text-xs">
                  {r.iterations_done}/{r.iterations_target}
                </td>
                <td className="px-4 py-3 text-emerald-400 text-xs font-mono">
                  {r.best_p99 ? `${r.best_p99.toFixed(1)}ms` : "—"}
                </td>
                <td className="px-4 py-3 text-neutral-500 text-xs">{r.model}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Descent chart */}
      {selected && (
        <div className="bg-card border border-border rounded-lg p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h2 className="text-sm font-medium text-white">p99 descent — {selected}</h2>
              <p className="text-xs text-neutral-500 mt-0.5">
                Each dot is one experiment.{" "}
                <span className="text-emerald-400">Green</span> = kept,{" "}
                <span className="text-neutral-400">gray</span> = discarded,{" "}
                <span className="text-amber-400">amber</span> = escalated,{" "}
                <span className="text-red-400">red</span> = rolled back.
              </p>
            </div>
            {best < Infinity && baseline && (
              <div className="text-right">
                <p className="text-xs text-neutral-500">Improvement</p>
                <p className="text-lg font-semibold text-emerald-400">
                  −{Math.round(((baseline - best) / baseline) * 100)}%
                </p>
                <p className="text-xs text-neutral-600">{baseline.toFixed(1)} → {best.toFixed(1)}ms</p>
              </div>
            )}
          </div>
          {experiments.length > 0 ? (
            <DescentChart data={experiments} baseline={baseline} />
          ) : (
            <div className="h-64 flex items-center justify-center text-neutral-600 text-sm">Loading…</div>
          )}
        </div>
      )}
    </div>
  );
}

export default function RunsPage() {
  return (
    <Suspense fallback={<div className="text-neutral-500 text-sm">Loading…</div>}>
      <RunsContent />
    </Suspense>
  );
}
