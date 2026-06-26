"use client";

import Link from "next/link";
import { useCallback } from "react";
import { Activity, AlertTriangle, CheckCircle2, Gauge, GitBranch, ListChecks, Server, ShieldAlert, XCircle } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { RiskBadge, StatusBadge } from "@/components/badges";
import { CardsSkeleton, EmptyState, ErrorState, TableSkeleton } from "@/components/data-state";
import { StatCard } from "@/components/metric-card";
import { Column, DataTable, SectionCard } from "@/components/ui";
import { getDashboard, getHealth, getQueueMetrics } from "@/lib/api";
import { formatDateTime, formatScore } from "@/lib/format";
import { useApiResource } from "@/hooks/use-api-resource";
import type { DashboardRecentScan, HealthStatus, QueueMetrics } from "@/types/api";

type DashboardView = {
  dashboard: Awaited<ReturnType<typeof getDashboard>>;
  health: HealthStatus | null;
  healthError: string | null;
  queueMetrics: QueueMetrics | null;
  queueMetricsError: string | null;
};

function getSettledError(result: PromiseSettledResult<unknown>): string | null {
  if (result.status === "fulfilled") {
    return null;
  }
  return result.reason instanceof Error ? result.reason.message : "Request failed";
}

async function loadDashboardView(): Promise<DashboardView> {
  const [dashboardResult, healthResult, queueResult] = await Promise.allSettled([
    getDashboard(),
    getHealth(),
    getQueueMetrics()
  ]);

  if (dashboardResult.status === "rejected") {
    throw dashboardResult.reason;
  }

  return {
    dashboard: dashboardResult.value,
    health: healthResult.status === "fulfilled" ? healthResult.value : null,
    healthError: getSettledError(healthResult),
    queueMetrics: queueResult.status === "fulfilled" ? queueResult.value : null,
    queueMetricsError: getSettledError(queueResult)
  };
}

function MiniStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-mist px-3 py-2">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-sm font-semibold text-ink">{value}</dd>
    </div>
  );
}

function HealthStatusCard({ health, error }: { health: HealthStatus | null; error: string | null }) {
  const ok = health?.status === "ok" || health?.status === "healthy";
  return (
    <SectionCard title="Service health" icon={Server} description={health ? formatDateTime(health.timestamp) : undefined}>
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${ok ? "bg-emerald-500" : health ? "bg-amber-500" : "bg-slate-300"}`} />
        <span className="text-lg font-semibold capitalize text-ink">{health?.status ?? "unavailable"}</span>
      </div>
      {health ? (
        <dl className="mt-4 grid grid-cols-3 gap-2">
          <MiniStat label="Database" value={health.database_status} />
          <MiniStat label="Redis" value={health.redis_status} />
          <MiniStat label="Celery" value={health.celery_queue_reachable ? "ok" : "error"} />
        </dl>
      ) : (
        <p className="mt-2 text-sm text-slate-500">{error ?? "Health check unavailable"}</p>
      )}
    </SectionCard>
  );
}

function QueueMetricsCard({ metrics, error }: { metrics: QueueMetrics | null; error: string | null }) {
  return (
    <SectionCard title="Scan queue" icon={Activity}>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-semibold tracking-tight text-ink">{metrics?.pending_scan_task_count ?? "—"}</span>
        <span className="text-sm text-slate-500">{metrics ? `${metrics.queue_name} pending` : error ?? "unavailable"}</span>
      </div>
      {metrics ? (
        <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
          <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${metrics.redis_connected ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-rose-200 bg-rose-50 text-rose-700"}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${metrics.redis_connected ? "bg-emerald-500" : "bg-rose-500"}`} />
            {metrics.redis_connected ? "redis ok" : "redis error"}
          </span>
          <Link className="focus-ring rounded-lg px-2 py-1 font-medium text-brand hover:bg-brand-soft" href="/admin/dead-letter-scans">
            {metrics.dead_letter_count} dead letters →
          </Link>
        </div>
      ) : null}
    </SectionCard>
  );
}

export default function DashboardPage() {
  const loader = useCallback(() => loadDashboardView(), []);
  const { data, error, isLoading, reload } = useApiResource(loader);

  const columns: Column<DashboardRecentScan>[] = [
    { key: "repo", header: "Repository", render: (s) => <span className="font-medium text-ink">{s.repository}</span> },
    {
      key: "pr",
      header: "PR",
      render: (s) => (
        <Link className="focus-ring rounded font-medium text-brand hover:underline" href={`/scans/${s.scan_id}`}>
          #{s.pr_number}
        </Link>
      )
    },
    { key: "status", header: "Status", render: (s) => <StatusBadge status={s.status} /> },
    {
      key: "risk",
      header: "Risk",
      render: (s) => (
        <div className="flex items-center gap-2">
          <RiskBadge level={s.risk_level} />
          <span className="text-slate-500">{s.risk_score ?? "—"}</span>
        </div>
      )
    },
    { key: "findings", header: "Findings", align: "right", render: (s) => s.findings_count },
    { key: "created", header: "Created", render: (s) => <span className="text-slate-500">{formatDateTime(s.created_at)}</span> }
  ];

  return (
    <AppShell title="Dashboard" description="Engineering governance at a glance">
      {isLoading ? (
        <div className="space-y-6">
          <CardsSkeleton count={6} />
          <TableSkeleton rows={5} columns={6} />
        </div>
      ) : null}
      {error ? <ErrorState message={error} onRetry={() => reload().catch(() => undefined)} /> : null}
      {data ? (
        <div className="space-y-6">
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <StatCard icon={GitBranch} label="Repositories" value={data.dashboard.summary.total_repositories} />
            <StatCard icon={ListChecks} label="Total scans" value={data.dashboard.summary.total_scans} />
            <StatCard icon={CheckCircle2} label="Completed" value={data.dashboard.summary.completed_scans} />
            <StatCard icon={XCircle} label="Failed" value={data.dashboard.summary.failed_scans} />
            <StatCard icon={AlertTriangle} label="High risk" value={data.dashboard.summary.high_risk_scans} />
            <StatCard icon={Gauge} label="Average risk" value={formatScore(data.dashboard.summary.average_risk_score)} detail="out of 100" />
          </section>

          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <SectionCard title="Risk summary" icon={ShieldAlert}>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-semibold tracking-tight text-ink">{formatScore(data.dashboard.summary.average_risk_score)}</span>
                <span className="text-sm text-slate-500">average scan risk</span>
              </div>
              <dl className="mt-4 grid grid-cols-3 gap-2">
                <MiniStat label="High" value={data.dashboard.summary.high_risk_scans} />
                <MiniStat label="Failed" value={data.dashboard.summary.failed_scans} />
                <MiniStat label="Done" value={data.dashboard.summary.completed_scans} />
              </dl>
            </SectionCard>
            <HealthStatusCard health={data.health} error={data.healthError} />
            <QueueMetricsCard metrics={data.queueMetrics} error={data.queueMetricsError} />
          </section>

          <SectionCard
            title="Recent scans"
            actions={
              <Link className="focus-ring rounded-lg px-2.5 py-1 text-sm font-medium text-brand hover:bg-brand-soft" href="/scans">
                View all →
              </Link>
            }
            bodyClassName="p-0"
          >
            <DataTable
              columns={columns}
              rows={data.dashboard.recent_scans}
              getRowKey={(s) => s.scan_id}
              empty={
                <div className="p-5">
                  <EmptyState
                    icon={ListChecks}
                    title="No scans yet"
                    description="Scans appear here automatically once a connected repository receives a pull request. To populate a demo, run the seed data script."
                  />
                </div>
              }
            />
          </SectionCard>
        </div>
      ) : null}
    </AppShell>
  );
}
