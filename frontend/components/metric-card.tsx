import type { LucideIcon } from "lucide-react";
import clsx from "clsx";

export function StatCard({
  icon: Icon,
  label,
  value,
  detail,
  trend
}: {
  icon: LucideIcon;
  label: string;
  value: string | number;
  detail?: string;
  trend?: { value: string; tone?: "up" | "down" | "neutral" };
}) {
  return (
    <div className="group rounded-xl border border-line bg-panel p-5 shadow-surface transition-shadow hover:shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-[0.08em] text-slate-500">{label}</p>
          <p className="mt-2 text-3xl font-semibold tracking-tight text-ink">{value}</p>
          {detail ? <p className="mt-1 text-sm text-slate-500">{detail}</p> : null}
        </div>
        <div className="flex h-10 w-10 flex-none items-center justify-center rounded-xl bg-brand-soft text-brand ring-1 ring-brand/10">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </div>
      </div>
      {trend ? (
        <p
          className={clsx(
            "mt-3 inline-flex items-center gap-1 text-xs font-medium",
            trend.tone === "up" && "text-emerald-600",
            trend.tone === "down" && "text-rose-600",
            (!trend.tone || trend.tone === "neutral") && "text-slate-500"
          )}
        >
          {trend.value}
        </p>
      ) : null}
    </div>
  );
}

/** Backwards-compatible alias. */
export const MetricCard = StatCard;
