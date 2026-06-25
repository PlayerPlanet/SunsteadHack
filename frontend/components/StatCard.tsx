export default function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: "navy" | "green" | "amber" | "red" | "neutral";
}) {
  const colors = {
    navy: "text-navy",
    green: "text-emerald-600",
    amber: "text-amber-600",
    red: "text-red-600",
    neutral: "text-gray-900",
  };
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
      <p className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-2">{label}</p>
      <p className={`text-3xl font-semibold tabular-nums ${colors[accent ?? "neutral"]}`}>
        {value}
      </p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}
