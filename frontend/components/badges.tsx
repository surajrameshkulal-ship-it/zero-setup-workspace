import clsx from "clsx";
import type { RiskLevel, RuleSeverity, ScanStatus } from "@/types/api";

const statusClass: Record<ScanStatus, string> = {
  queued: "border-slate-300 bg-slate-100 text-slate-700",
  running: "border-blue-300 bg-blue-50 text-blue-700",
  completed: "border-emerald-300 bg-emerald-50 text-emerald-700",
  failed: "border-rose-300 bg-rose-50 text-rose-700"
};

const riskClass: Record<RiskLevel, string> = {
  low: "border-emerald-300 bg-emerald-50 text-emerald-700",
  medium: "border-amber-300 bg-amber-50 text-amber-800",
  high: "border-orange-300 bg-orange-50 text-orange-800",
  critical: "border-rose-300 bg-rose-50 text-rose-800"
};

const severityClass: Record<RuleSeverity, string> = {
  info: "border-sky-300 bg-sky-50 text-sky-700",
  low: riskClass.low,
  medium: riskClass.medium,
  high: riskClass.high,
  critical: riskClass.critical
};

export function StatusBadge({ status }: { status: ScanStatus }) {
  return <span className={clsx("inline-flex rounded border px-2 py-0.5 text-xs font-medium", statusClass[status])}>{status}</span>;
}

export function RiskBadge({ level }: { level: RiskLevel | null }) {
  if (!level) {
    return <span className="inline-flex rounded border border-slate-300 bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">none</span>;
  }
  return <span className={clsx("inline-flex rounded border px-2 py-0.5 text-xs font-medium", riskClass[level])}>{level}</span>;
}

export function SeverityBadge({ severity }: { severity?: RuleSeverity | string }) {
  if (!severity || !(severity in severityClass)) {
    return <span className="inline-flex rounded border border-slate-300 bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">none</span>;
  }
  return <span className={clsx("inline-flex rounded border px-2 py-0.5 text-xs font-medium", severityClass[severity as RuleSeverity])}>{severity}</span>;
}
