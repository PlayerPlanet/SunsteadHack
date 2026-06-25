"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle, XCircle, Clock } from "lucide-react";

type Escalation = {
  id: number;
  pore: string;
  risk_level: string;
  action: { type: string; params: Record<string, string> };
  rationale?: string;
  created_at: string;
  judgment: { decision: string; judge_kind: string; rationale?: string } | null;
};

function riskColor(level: string) {
  if (level === "HIGH") return "text-red-400 bg-red-400/10 border-red-400/20";
  if (level === "MEDIUM") return "text-amber-400 bg-amber-400/10 border-amber-400/20";
  return "text-neutral-400 bg-neutral-400/10 border-neutral-400/20";
}

function actionLabel(action: Escalation["action"]) {
  if (!action) return "—";
  const p = action.params ?? {};
  if (action.type === "guc") return `SET ${p.name} = '${p.value}'`;
  if (action.type === "index_drop") return `DROP INDEX ${p.name}`;
  if (action.type === "index_create") return `CREATE INDEX ${p.name ?? ""}`;
  return action.type;
}

function timeAgo(iso: string) {
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  return `${Math.floor(mins / 60)}h ago`;
}

export default function EscalationsPage() {
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [adjudicating, setAdjudicating] = useState<number | null>(null);
  const [rationale, setRationale] = useState("");

  const load = () =>
    fetch("/api/escalations").then((r) => r.json()).then((d) => setEscalations(d.escalations ?? []));

  useEffect(() => { load(); }, []);

  async function adjudicate(id: number, decision: "approve" | "reject") {
    await fetch(`/api/escalations/${id}/adjudicate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, rationale }),
    });
    setAdjudicating(null);
    setRationale("");
    load();
  }

  const pending = escalations.filter((e) => !e.judgment);
  const decided = escalations.filter((e) => e.judgment);

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Escalations</h1>
          <p className="text-sm text-neutral-500 mt-1">
            Actions the frozen pore flagged. These are routed to you because the agent shouldn't decide alone.
          </p>
        </div>
        {pending.length > 0 && (
          <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-amber-400/10 text-amber-400 border border-amber-400/20">
            {pending.length} pending
          </span>
        )}
      </div>

      {/* Pending */}
      {pending.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-xs text-neutral-500 uppercase tracking-wider">Awaiting judgment</h2>
          {pending.map((e) => (
            <div key={e.id} className="bg-card border border-amber-400/20 rounded-lg p-5">
              <div className="flex items-start gap-4">
                <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-xs px-2 py-0.5 rounded border font-mono ${riskColor(e.risk_level)}`}>
                      {e.risk_level}
                    </span>
                    <span className="text-xs text-neutral-500">pore: {e.pore}</span>
                    <span className="text-xs text-neutral-600 ml-auto">{timeAgo(e.created_at)}</span>
                  </div>
                  <p className="font-mono text-sm text-white mt-2">{actionLabel(e.action)}</p>
                  {e.rationale && (
                    <p className="text-xs text-neutral-400 mt-2 leading-relaxed">{e.rationale}</p>
                  )}

                  {adjudicating === e.id ? (
                    <div className="mt-4 space-y-3">
                      <textarea
                        className="w-full bg-surface border border-border rounded p-3 text-sm text-neutral-200 placeholder-neutral-600 resize-none focus:outline-none focus:border-neutral-500"
                        rows={3}
                        placeholder="Rationale (optional)…"
                        value={rationale}
                        onChange={(ev) => setRationale(ev.target.value)}
                      />
                      <div className="flex gap-2">
                        <button
                          onClick={() => adjudicate(e.id, "approve")}
                          className="px-4 py-2 text-sm rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20 transition-colors"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => adjudicate(e.id, "reject")}
                          className="px-4 py-2 text-sm rounded bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20 transition-colors"
                        >
                          Reject
                        </button>
                        <button
                          onClick={() => setAdjudicating(null)}
                          className="px-4 py-2 text-sm rounded text-neutral-500 hover:text-neutral-300 transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      onClick={() => setAdjudicating(e.id)}
                      className="mt-3 px-3 py-1.5 text-xs rounded border border-border text-neutral-400 hover:text-neutral-200 hover:border-neutral-500 transition-colors"
                    >
                      Adjudicate →
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Decided */}
      {decided.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-xs text-neutral-500 uppercase tracking-wider">Decided</h2>
          {decided.map((e) => (
            <div key={e.id} className="bg-card border border-border rounded-lg p-4">
              <div className="flex items-start gap-4">
                {e.judgment?.decision === "approve" ? (
                  <CheckCircle className="w-4 h-4 text-emerald-400 mt-0.5 flex-shrink-0" />
                ) : (
                  <XCircle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-xs px-2 py-0.5 rounded border font-mono ${riskColor(e.risk_level)}`}>
                      {e.risk_level}
                    </span>
                    <span className="text-xs text-neutral-500">pore: {e.pore}</span>
                    <span className={`text-xs ml-auto ${e.judgment?.decision === "approve" ? "text-emerald-400" : "text-red-400"}`}>
                      {e.judgment?.decision} · {e.judgment?.judge_kind}
                    </span>
                  </div>
                  <p className="font-mono text-sm text-neutral-300 mt-1">{actionLabel(e.action)}</p>
                  {e.judgment?.rationale && (
                    <p className="text-xs text-neutral-500 mt-1 leading-relaxed line-clamp-2">
                      {e.judgment.rationale}
                    </p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {escalations.length === 0 && (
        <div className="bg-card border border-border rounded-lg p-12 text-center">
          <Clock className="w-8 h-8 text-neutral-600 mx-auto mb-3" />
          <p className="text-neutral-500 text-sm">No escalations yet.</p>
          <p className="text-neutral-600 text-xs mt-1">The pore will route decisions here when the agent reaches its edge.</p>
        </div>
      )}
    </div>
  );
}
