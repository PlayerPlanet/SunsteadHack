"use client";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine } from "recharts";

// Matches tool_read_curve output shape (with n added as index)
type CurvePoint = {
  n: number;
  candidate_p99: number | null;
  baseline_p99?: number;
  decision: string;  // "keep" | "reject"
  within_noise?: boolean;
  candidate?: { type: string; params: Record<string, any> };
  correctness_ok?: boolean;
};

const DOT_COLORS: Record<string, string> = {
  keep: "#10b981",   // emerald — improvement kept
  reject: "#f59e0b", // amber — rolled back (noise or pore stop)
};

function candidateLabel(c?: CurvePoint["candidate"]) {
  if (!c) return "";
  const p = c.params ?? {};
  if (c.type === "index") return `INDEX (${p.table ?? ""}.${Array.isArray(p.columns) ? p.columns.join(", ") : p.columns ?? ""})`;
  if (c.type === "guc") return `SET ${p.name} = ${p.value}`;
  if (c.type === "index_drop") return `DROP INDEX ${p.name ?? ""}`;
  return c.type;
}

export default function DescentChart({ data, baseline }: { data: CurvePoint[]; baseline?: number }) {
  const baselineY = baseline ?? data[0]?.baseline_p99 ?? undefined;

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis
          dataKey="n"
          label={{ value: "Experiment →", position: "insideBottomRight", offset: -8, fill: "#9ca3af", fontSize: 11 }}
          tick={{ fill: "#9ca3af", fontSize: 11 }}
        />
        <YAxis tickFormatter={(v) => `${v}ms`} tick={{ fill: "#9ca3af", fontSize: 11 }} />
        <Tooltip
          contentStyle={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, boxShadow: "0 2px 8px rgba(0,0,0,0.08)" }}
          formatter={(val: number, _: string, item: any) => {
            const p = item?.payload as CurvePoint;
            const label = [
              `${val}ms`,
              p?.within_noise ? "within noise — rejected" : p?.decision,
              candidateLabel(p?.candidate),
            ].filter(Boolean).join(" · ");
            return [label, "p99"];
          }}
          labelFormatter={(v) => `Experiment ${v}`}
        />
        {baselineY && (
          <ReferenceLine
            y={baselineY}
            stroke="#d1d5db"
            strokeDasharray="4 4"
            label={{ value: `baseline ${baselineY}ms`, position: "right", fill: "#9ca3af", fontSize: 10 }}
          />
        )}
        <Line
          type="stepAfter"
          dataKey="candidate_p99"
          stroke="#10b981"
          strokeWidth={2}
          dot={(props: any) => {
            const { cx, cy, payload } = props as { cx: number; cy: number; payload: CurvePoint };
            const color = DOT_COLORS[payload.decision] ?? "#9ca3af";
            const filled = payload.decision === "keep";
            return (
              <circle
                key={payload.n}
                cx={cx}
                cy={cy}
                r={4}
                fill={filled ? color : "#fff"}
                stroke={color}
                strokeWidth={1.5}
              />
            );
          }}
          connectNulls={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
