interface Props {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "alert" | "good";
}

export default function StatCard({ label, value, hint, tone = "default" }: Props) {
  const toneClass =
    tone === "alert" ? "text-alert" : tone === "good" ? "text-good" : "text-slate-100";
  return (
    <div className="card flex flex-col gap-1 min-w-[150px]">
      <span className="text-xs uppercase tracking-wide text-slate-400">{label}</span>
      <span className={`text-3xl font-bold ${toneClass}`}>{value}</span>
      {hint && <span className="text-xs text-slate-500">{hint}</span>}
    </div>
  );
}
