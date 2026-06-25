"use client";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";

type Point = { volume: number; escalations_frozen: number; escalations_membrane?: number };

export default function LongitudinalChart({ data }: { data: Point[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
        <XAxis
          dataKey="volume"
          label={{ value: "Cumulative experiments →", position: "insideBottomRight", offset: -8, fill: "#737373", fontSize: 11 }}
          tick={{ fill: "#737373", fontSize: 11 }}
        />
        <YAxis
          label={{ value: "Escalations", angle: -90, position: "insideLeft", fill: "#737373", fontSize: 11 }}
          tick={{ fill: "#737373", fontSize: 11 }}
        />
        <Tooltip
          contentStyle={{ background: "#1c1c1c", border: "1px solid #333", borderRadius: 6 }}
        />
        <Legend
          formatter={(v) => (
            <span className="text-xs text-neutral-400">
              {v === "escalations_frozen" ? "Frozen pore (today)" : "Shadow membrane (Stage 2)"}
            </span>
          )}
        />
        <Line type="monotone" dataKey="escalations_frozen" stroke="#f59e0b" strokeWidth={2} dot={false} name="escalations_frozen" />
        <Line type="monotone" dataKey="escalations_membrane" stroke="#22c55e" strokeWidth={2} strokeDasharray="5 3" dot={false} name="escalations_membrane" />
      </LineChart>
    </ResponsiveContainer>
  );
}
