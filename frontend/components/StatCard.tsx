export default function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: "green" | "amber" | "red" | "neutral";
}) {
  const colors = {
    green: "text-emerald-400",
    amber: "text-amber-400",
    red: "text-red-400",
    neutral: "text-white",
  };
  return (
    <div className="bg-card border border-border rounded-lg p-5">
      <p className="text-xs text-neutral-500 uppercase tracking-wider mb-2">{label}</p>
      <p className={`text-3xl font-semibold tabular-nums ${colors[accent ?? "neutral"]}`}>
        {value}
      </p>
      {sub && <p className="text-xs text-neutral-500 mt-1">{sub}</p>}
    </div>
  );
}
