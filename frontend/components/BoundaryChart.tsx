"use client";
import {
  ResponsiveContainer, ComposedChart, Area, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine,
} from "recharts";

type Point = { drift: number; escalation_rate: number; correctness: number; n: number };

export default function BoundaryChart({ data }: { data: Point[] }) {
  const boundary = data.find((d) => d.escalation_rate > 0 && d.correctness < 90)?.drift ?? 0.6;

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis
          dataKey="drift"
          tickFormatter={(v) => v.toFixed(1)}
          label={{ value: "Workload drift →", position: "insideBottomRight", offset: -8, fill: "#9ca3af", fontSize: 11 }}
          tick={{ fill: "#9ca3af", fontSize: 11 }}
        />
        <YAxis
          tickFormatter={(v) => `${v}%`}
          tick={{ fill: "#9ca3af", fontSize: 11 }}
          domain={[0, 100]}
        />
        <Tooltip
          contentStyle={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, boxShadow: "0 2px 8px rgba(0,0,0,0.08)" }}
          formatter={(val: number, name: string) => [
            `${val.toFixed(1)}%`,
            name === "escalation_rate" ? "Escalation rate" : "Autonomous correctness",
          ]}
          labelFormatter={(v) => `Drift: ${Number(v).toFixed(1)}`}
        />
        <Legend
          formatter={(v) => (
            <span style={{ fontSize: 12, color: "#6b7280" }}>
              {v === "escalation_rate" ? "Escalation rate" : "Autonomous correctness"}
            </span>
          )}
        />
        <Area type="monotone" dataKey="correctness" fill="#d1fae5" stroke="#10b981" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="escalation_rate" stroke="#f59e0b" strokeWidth={2} dot={{ r: 3, fill: "#f59e0b" }} />
        <ReferenceLine
          x={boundary}
          stroke="#ef4444"
          strokeDasharray="4 4"
          label={{ value: "boundary", position: "top", fill: "#ef4444", fontSize: 10 }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
