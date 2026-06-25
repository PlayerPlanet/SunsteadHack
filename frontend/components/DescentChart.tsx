"use client";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, Cell, ScatterChart, Scatter } from "recharts";

type Exp = { n: number; p99: number | null; decision: string; action?: string };

const DOT_COLORS: Record<string, string> = {
  keep: "#22c55e",
  discard: "#6b7280",
  rollback: "#ef4444",
  escalated: "#f59e0b",
};

export default function DescentChart({ data, baseline }: { data: Exp[]; baseline?: number }) {
  const kept = data.filter((d) => d.decision === "keep" && d.p99 != null);

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
        <XAxis
          dataKey="n"
          label={{ value: "Experiment →", position: "insideBottomRight", offset: -8, fill: "#737373", fontSize: 11 }}
          tick={{ fill: "#737373", fontSize: 11 }}
        />
        <YAxis
          tickFormatter={(v) => `${v}ms`}
          tick={{ fill: "#737373", fontSize: 11 }}
        />
        <Tooltip
          contentStyle={{ background: "#1c1c1c", border: "1px solid #333", borderRadius: 6 }}
          formatter={(val: number, _: string, item: any) => [
            `${val}ms`,
            item?.payload?.decision ?? "",
          ]}
          labelFormatter={(v) => `Experiment ${v}`}
        />
        {baseline && (
          <ReferenceLine
            y={baseline}
            stroke="#4b5563"
            strokeDasharray="4 4"
            label={{ value: `baseline ${baseline}ms`, position: "right", fill: "#6b7280", fontSize: 10 }}
          />
        )}
        <Line
          type="stepAfter"
          dataKey="p99"
          stroke="#22c55e"
          strokeWidth={2}
          dot={(props) => {
            const { cx, cy, payload } = props;
            const color = DOT_COLORS[payload.decision] ?? "#6b7280";
            return <circle key={payload.n} cx={cx} cy={cy} r={4} fill={color} stroke="none" />;
          }}
          connectNulls={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
