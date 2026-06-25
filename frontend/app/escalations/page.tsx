"use client";
import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { AlertTriangle, CheckCircle, XCircle, Clock, Lock } from "lucide-react";
import TopBar from "@/components/TopBar";
import { roleFromGroups, canAdjudicate } from "@/lib/roles";

type Escalation = {
  id: number;
  pore: string;
  risk_level: string;
  action: { type: string; params: Record<string, string> };
  rationale?: string;
  created_at: string;
  judgment: { decision: string; judge_kind: string; rationale?: string } | null;
};

function riskBadge(level: string) {
  if (level === "HIGH") return "bg-red-100 text-red-700 border-red-200";
  if (level === "MEDIUM") return "bg-amber-100 text-amber-700 border-amber-200";
  return "bg-gray-100 text-gray-600 border-gray-200";
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
  // Role is derived from the signed-in user's Cognito groups. This only gates the UI;
  // the real enforcement is the adjudicate route -> runtime -> SET ROLE in Postgres.
  const { data: session } = useSession();
  const role = roleFromGroups(session?.groups);
  const mayAdjudicate = canAdjudicate(role);

  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [adjudicating, setAdjudicating] = useState<number | null>(null);
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    fetch("/api/escalations").then((r) => r.json()).then((d) => setEscalations(Array.isArray(d.escalations) ? d.escalations : []));

  useEffect(() => { load(); }, []);

  async function adjudicate(id: number, decision: "approve" | "reject") {
    setError(null);
    const res = await fetch(`/api/escalations/${id}/adjudicate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, rationale }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      // The control plane refused (scope / SET ROLE) — surface it verbatim; this is the
      // truth boundary talking, not a UI bug.
      setError(body.error ?? `adjudicate failed (${res.status})`);
      return;
    }
    setAdjudicating(null);
    setRationale("");
    load();
  }

  const pending = escalations.filter((e) => !e.judgment);
  const decided = escalations.filter((e) => e.judgment);

  return (
    <>
      <TopBar title="Escalations" />
      <main className="flex-1 p-6 space-y-6 overflow-y-auto">

        {/* Header strip */}
        <div className="flex items-center justify-between">
          <p className="text-sm text-gray-500">
            Actions the frozen pore flagged. These are routed to you because the agent shouldn't decide alone.
          </p>
          {pending.length > 0 && (
            <span className="px-3 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-700 border border-amber-200">
              {pending.length} pending
            </span>
          )}
        </div>

        {!mayAdjudicate && (
          <div className="flex items-center gap-2 text-sm text-gray-500 bg-white border border-gray-200 rounded-xl shadow-sm px-4 py-3">
            <Lock className="w-4 h-4 text-gray-400 flex-shrink-0" />
            View only — adjudicating requires the operator role. Ask an operator to add you to the
            <span className="font-mono text-gray-700">sunstead-operators</span> group.
          </div>
        )}

        {error && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
            {error}
          </div>
        )}

        {/* Pending */}
        {pending.length > 0 && (
          <div className="space-y-3">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Awaiting judgment</h2>
            {pending.map((e) => (
              <div key={e.id} className="bg-white border border-amber-200 rounded-xl shadow-sm p-5">
                <div className="flex items-start gap-4">
                  <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-2">
                      <span className={`text-xs px-2 py-0.5 rounded border font-semibold ${riskBadge(e.risk_level)}`}>
                        {e.risk_level}
                      </span>
                      <span className="text-xs text-gray-400">pore: {e.pore}</span>
                      <span className="text-xs text-gray-300 ml-auto">{timeAgo(e.created_at)}</span>
                    </div>
                    <p className="font-mono text-sm text-gray-900 bg-gray-50 rounded-lg px-3 py-2 border border-gray-100">
                      {actionLabel(e.action)}
                    </p>
                    {e.rationale && (
                      <p className="text-xs text-gray-500 mt-2 leading-relaxed">{e.rationale}</p>
                    )}
                    {mayAdjudicate && (adjudicating === e.id ? (
                      <div className="mt-4 space-y-3">
                        <textarea
                          className="w-full bg-white border border-gray-200 rounded-lg p-3 text-sm text-gray-800 placeholder-gray-400 resize-none focus:outline-none focus:ring-2 focus:ring-navy focus:border-transparent"
                          rows={3}
                          placeholder="Rationale (optional)…"
                          value={rationale}
                          onChange={(ev) => setRationale(ev.target.value)}
                        />
                        <div className="flex gap-2">
                          <button
                            onClick={() => adjudicate(e.id, "approve")}
                            className="px-4 py-2 text-sm rounded-lg bg-navy text-white font-medium hover:bg-navy-dark transition-colors"
                          >
                            Approve
                          </button>
                          <button
                            onClick={() => adjudicate(e.id, "reject")}
                            className="px-4 py-2 text-sm rounded-lg bg-red-50 border border-red-200 text-red-600 font-medium hover:bg-red-100 transition-colors"
                          >
                            Reject
                          </button>
                          <button
                            onClick={() => setAdjudicating(null)}
                            className="px-4 py-2 text-sm text-gray-400 hover:text-gray-600 transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        onClick={() => setAdjudicating(e.id)}
                        className="mt-3 px-4 py-1.5 text-xs rounded-lg border border-navy text-navy font-medium hover:bg-navy hover:text-white transition-colors"
                      >
                        Adjudicate →
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Decided */}
        {decided.length > 0 && (
          <div className="space-y-2">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Decided</h2>
            <div className="bg-white border border-gray-200 rounded-xl shadow-sm divide-y divide-gray-100 overflow-hidden">
              {decided.map((e) => (
                <div key={e.id} className="flex items-start gap-4 px-5 py-4 hover:bg-gray-50 transition-colors">
                  {e.judgment?.decision === "approve"
                    ? <CheckCircle className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" />
                    : <XCircle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-xs px-2 py-0.5 rounded border font-semibold ${riskBadge(e.risk_level)}`}>
                        {e.risk_level}
                      </span>
                      <span className="text-xs text-gray-400">pore: {e.pore}</span>
                      <span className={`text-xs ml-auto font-semibold ${e.judgment?.decision === "approve" ? "text-emerald-600" : "text-red-500"}`}>
                        {e.judgment?.decision} · {e.judgment?.judge_kind}
                      </span>
                    </div>
                    <p className="font-mono text-xs text-gray-600 mt-1">{actionLabel(e.action)}</p>
                    {e.judgment?.rationale && (
                      <p className="text-xs text-gray-400 mt-1 line-clamp-1">{e.judgment.rationale}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {escalations.length === 0 && (
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-12 text-center">
            <Clock className="w-8 h-8 text-gray-200 mx-auto mb-3" />
            <p className="text-gray-400 text-sm font-medium">No escalations yet</p>
            <p className="text-gray-300 text-xs mt-1">The pore will route decisions here when the agent reaches its edge.</p>
          </div>
        )}
      </main>
    </>
  );
}
