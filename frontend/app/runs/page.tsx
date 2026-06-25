"use client";
import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Plus, X, AlertCircle } from "lucide-react";
import DescentChart from "@/components/DescentChart";
import TopBar from "@/components/TopBar";

const MODELS = [
  "claude-haiku-4-5-20251001",
  "claude-sonnet-4-6",
  "claude-opus-4-8",
];

const STATE_STYLE: Record<string, string> = {
  running: "bg-emerald-100 text-emerald-700",
  queued: "bg-blue-50 text-blue-600",
  done: "bg-gray-100 text-gray-600",
  completed: "bg-gray-100 text-gray-600",
  failed: "bg-red-100 text-red-600",
  cancelled: "bg-gray-100 text-gray-400",
};

function RegisterForm({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [workloads, setWorkloads] = useState<string[]>([]);
  const [form, setForm] = useState({
    task_id: "",
    objective: "",
    workload_id: "job-prodyear",
    model: MODELS[0],
    iterations: 10,
  });
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ task_id?: string; state?: string; error?: string } | null>(null);

  useEffect(() => {
    fetch("/api/tasks").then((r) => r.json()).then((d) => setWorkloads(d.workloads ?? []));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setResult(null);
    try {
      const res = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      setResult(data);
      if (data.task_id && !data.error) onCreated();
    } catch (err: any) {
      setResult({ error: err.message });
    } finally {
      setBusy(false);
    }
  }

  const field = (key: keyof typeof form, label: string, extra?: React.InputHTMLAttributes<HTMLInputElement>) => (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
      <input
        {...extra}
        value={String(form[key])}
        onChange={(ev) => setForm((f) => ({ ...f, [key]: key === "iterations" ? Number(ev.target.value) : ev.target.value }))}
        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-navy focus:border-transparent"
      />
    </div>
  );

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6 space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-900">Register new task</h2>
        <button onClick={onClose} className="text-gray-300 hover:text-gray-500 transition-colors"><X className="w-4 h-4" /></button>
      </div>

      {result?.state === "pending_judgment" && (
        <div className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-lg p-4">
          <AlertCircle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-amber-800">Governance hold</p>
            <p className="text-xs text-amber-600 mt-0.5">The frozen pore held this spec for human review. Check Escalations to adjudicate before dispatching.</p>
          </div>
        </div>
      )}

      {result?.task_id && result?.state !== "pending_judgment" && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 text-sm text-emerald-800">
          Task <span className="font-mono font-semibold">{result.task_id}</span> registered as active.{" "}
          <button onClick={onClose} className="underline text-emerald-700 ml-1">Close</button>
        </div>
      )}

      {result?.error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">{result.error}</div>
      )}

      <form onSubmit={submit} className="space-y-4">
        {field("task_id", "Task ID", { placeholder: "my-pg-task", required: true })}
        {field("objective", "Objective", { placeholder: "Minimize p99 on title × cast_info join", required: true })}

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Workload</label>
          <select
            value={form.workload_id}
            onChange={(ev) => setForm((f) => ({ ...f, workload_id: ev.target.value }))}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-navy focus:border-transparent"
          >
            {workloads.map((w) => <option key={w} value={w}>{w}</option>)}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Proposer model</label>
          <select
            value={form.model}
            onChange={(ev) => setForm((f) => ({ ...f, model: ev.target.value }))}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-navy focus:border-transparent"
          >
            {MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        {field("iterations", "Iterations", { type: "number", min: 1, max: 100 })}

        <div className="flex gap-3 pt-1">
          <button
            type="submit"
            disabled={busy}
            className="px-4 py-2 text-sm rounded-lg bg-navy text-white font-medium hover:bg-navy-dark transition-colors disabled:opacity-60"
          >
            {busy ? "Registering…" : "Register task"}
          </button>
          {result?.task_id && result?.state !== "pending_judgment" && (
            <button
              type="button"
              onClick={async () => {
                setBusy(true);
                const res = await fetch("/api/runs", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ task_id: result.task_id, model: form.model, iterations: form.iterations }),
                });
                const d = await res.json();
                setBusy(false);
                if (d.run_id) { onCreated(); onClose(); }
              }}
              className="px-4 py-2 text-sm rounded-lg border border-navy text-navy font-medium hover:bg-navy hover:text-white transition-colors disabled:opacity-60"
            >
              Dispatch run →
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

function RunsContent() {
  const params = useSearchParams();
  const [runs, setRuns] = useState<any[]>([]);
  const [curve, setCurve] = useState<any[]>([]);
  const [selected, setSelected] = useState<string | null>(params.get("task"));
  const [showForm, setShowForm] = useState(false);

  const loadRuns = () =>
    fetch("/api/runs").then((r) => r.json()).then((d) => setRuns(d.runs ?? []));

  useEffect(() => { loadRuns(); }, []);

  useEffect(() => {
    if (!selected) return;
    setCurve([]);
    fetch(`/api/runs?task_id=${selected}`)
      .then((r) => r.json())
      .then((d) => setCurve(d.curve ?? []));
  }, [selected]);

  const baseline = curve[0]?.baseline_p99 ?? undefined;
  const best = curve.filter((e) => e.decision === "keep" && e.candidate_p99).reduce((a: number, e: any) => Math.min(a, e.candidate_p99), Infinity);

  return (
    <>
      <TopBar title="Runs" />
      <main className="flex-1 p-6 space-y-6 overflow-y-auto">

        <div className="flex justify-end">
          <button
            onClick={() => setShowForm((v) => !v)}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-navy text-white font-medium hover:bg-navy-dark transition-colors"
          >
            <Plus className="w-4 h-4" />
            New task
          </button>
        </div>

        {showForm && (
          <RegisterForm
            onClose={() => setShowForm(false)}
            onCreated={loadRuns}
          />
        )}

        <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="text-left px-5 py-3 text-xs text-gray-500 font-semibold uppercase tracking-wide">Task</th>
                <th className="text-left px-5 py-3 text-xs text-gray-500 font-semibold uppercase tracking-wide">State</th>
                <th className="text-left px-5 py-3 text-xs text-gray-500 font-semibold uppercase tracking-wide">Progress</th>
                <th className="text-left px-5 py-3 text-xs text-gray-500 font-semibold uppercase tracking-wide">Best p99</th>
                <th className="text-left px-5 py-3 text-xs text-gray-500 font-semibold uppercase tracking-wide">Model</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {runs.map((r) => (
                <tr
                  key={r.run_id}
                  onClick={() => setSelected(r.task_id)}
                  className={`cursor-pointer transition-colors hover:bg-gray-50 ${selected === r.task_id ? "bg-blue-50" : ""}`}
                >
                  <td className="px-5 py-3 font-mono text-xs text-gray-800">{r.task_id}</td>
                  <td className="px-5 py-3">
                    <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full ${STATE_STYLE[r.state] ?? "bg-gray-100 text-gray-600"}`}>
                      {r.state === "running" && <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />}
                      {r.state}
                    </span>
                    {r.state === "failed" && r.error_msg && (
                      <p className="text-xs text-red-500 mt-0.5 truncate max-w-[200px]">{r.error_msg}</p>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-24 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-navy rounded-full"
                          style={{
                            width: `${r.iterations_target ? (r.iterations_done / r.iterations_target) * 100 : r.iterations_done ? 100 : 0}%`
                          }}
                        />
                      </div>
                      <span className="text-xs text-gray-400">
                        {r.iterations_done}{r.iterations_target ? `/${r.iterations_target}` : ""}
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-3 font-mono text-xs font-semibold text-emerald-600">
                    {r.best_p99 ? `${Number(r.best_p99).toFixed(1)}ms` : "—"}
                  </td>
                  <td className="px-5 py-3 text-xs text-gray-400">{r.model}</td>
                </tr>
              ))}
              {runs.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-5 py-10 text-center text-sm text-gray-300">No runs yet — register a task and dispatch.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {selected && (
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm">
            <div className="flex items-start justify-between px-6 py-4 border-b border-gray-100">
              <div>
                <h2 className="text-sm font-semibold text-gray-900">p99 descent — <span className="font-mono">{selected}</span></h2>
                <p className="text-xs text-gray-400 mt-0.5">
                  <span className="text-emerald-600 font-medium">●</span> kept &nbsp;
                  <span className="text-amber-400 font-medium">○</span> rejected / rolled back
                </p>
              </div>
              {best < Infinity && baseline && (
                <div className="text-right">
                  <p className="text-xs text-gray-400">Improvement</p>
                  <p className="text-xl font-semibold text-emerald-600">
                    −{Math.round(((baseline - best) / baseline) * 100)}%
                  </p>
                  <p className="text-xs text-gray-400">{baseline.toFixed(1)} → {best.toFixed(1)}ms</p>
                </div>
              )}
            </div>
            <div className="p-4">
              {curve.length > 0
                ? <DescentChart data={curve} baseline={baseline} />
                : <div className="h-56 flex items-center justify-center text-gray-300 text-sm">Loading…</div>}
            </div>
          </div>
        )}
      </main>
    </>
  );
}

export default function RunsPage() {
  return (
    <Suspense fallback={<div className="p-6 text-gray-400 text-sm">Loading…</div>}>
      <RunsContent />
    </Suspense>
  );
}
