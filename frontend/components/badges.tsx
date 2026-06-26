import clsx from "clsx";
import type {
  EngineeringRequestPriority,
  EngineeringRequestStatus,
  RiskLevel,
  RuleSeverity,
  ScanStatus
} from "@/types/api";

type Tone = "neutral" | "info" | "brand" | "success" | "warning" | "danger" | "violet" | "cyan";

const TONE: Record<Tone, { pill: string; dot: string }> = {
  neutral: { pill: "border-slate-200 bg-slate-50 text-slate-600", dot: "bg-slate-400" },
  info: { pill: "border-blue-200 bg-blue-50 text-blue-700", dot: "bg-blue-500" },
  brand: { pill: "border-brand/20 bg-brand-soft text-brand-ink", dot: "bg-brand" },
  success: { pill: "border-emerald-200 bg-emerald-50 text-emerald-700", dot: "bg-emerald-500" },
  warning: { pill: "border-amber-200 bg-amber-50 text-amber-800", dot: "bg-amber-500" },
  danger: { pill: "border-rose-200 bg-rose-50 text-rose-700", dot: "bg-rose-500" },
  violet: { pill: "border-violet-200 bg-violet-50 text-violet-700", dot: "bg-violet-500" },
  cyan: { pill: "border-cyan-200 bg-cyan-50 text-cyan-700", dot: "bg-cyan-500" }
};

export function Badge({
  tone = "neutral",
  dot = true,
  className,
  children
}: {
  tone?: Tone;
  dot?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  const t = TONE[tone];
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize",
        t.pill,
        className
      )}
    >
      {dot ? <span className={clsx("h-1.5 w-1.5 rounded-full", t.dot)} aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

const statusTone: Record<ScanStatus, Tone> = {
  queued: "neutral",
  running: "info",
  completed: "success",
  failed: "danger"
};

const riskTone: Record<RiskLevel, Tone> = {
  low: "success",
  medium: "warning",
  high: "warning",
  critical: "danger"
};

const severityTone: Record<RuleSeverity, Tone> = {
  info: "info",
  low: "success",
  medium: "warning",
  high: "warning",
  critical: "danger"
};

export function StatusBadge({ status }: { status: ScanStatus }) {
  return <Badge tone={statusTone[status]}>{status}</Badge>;
}

export function RiskBadge({ level }: { level: RiskLevel | null }) {
  if (!level) {
    return <Badge tone="neutral">none</Badge>;
  }
  return <Badge tone={riskTone[level]}>{level}</Badge>;
}

export function SeverityBadge({ severity }: { severity?: RuleSeverity | string }) {
  if (!severity || !(severity in severityTone)) {
    return <Badge tone="neutral">none</Badge>;
  }
  return <Badge tone={severityTone[severity as RuleSeverity]}>{severity}</Badge>;
}

const requestStatusTone: Record<EngineeringRequestStatus, Tone> = {
  submitted: "neutral",
  analyzing: "info",
  plan_ready: "violet",
  approved: "success",
  rejected: "danger",
  in_progress: "info",
  pr_opened: "cyan",
  completed: "success",
  failed: "danger"
};

const priorityTone: Record<EngineeringRequestPriority, Tone> = {
  low: "neutral",
  medium: "info",
  high: "warning",
  urgent: "danger"
};

export function RequestStatusBadge({ status }: { status: EngineeringRequestStatus }) {
  return <Badge tone={requestStatusTone[status]}>{status.replace(/_/g, " ")}</Badge>;
}

export function PriorityBadge({ priority }: { priority: EngineeringRequestPriority }) {
  return <Badge tone={priorityTone[priority]}>{priority}</Badge>;
}
