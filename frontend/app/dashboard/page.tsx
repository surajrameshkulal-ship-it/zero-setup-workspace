"use client";

import Link from "next/link";
import { useCallback } from "react";
import { Activity, AlertTriangle, CheckCircle2, Gauge, GitBranch, ListChecks, Server, ShieldAlert, XCircle } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { RiskBadge, StatusBadge } from "@/components/badges";
import { CardsSkeleton, EmptyState, ErrorState, TableSkeleton } from "@/components/data-state";
import { MetricCard } from "@/components/metric-card";
import { getDashboard, getHealth, getQueueMetrics } from "@/lib/api";
import { formatDateTime, formatScore } from "@/lib/format";
import { useApiResource } from "@/hooks/use-api-resource";
import type { HealthStatus, QueueMetrics } from "@/types/api";

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

function HealthStatusCard({ health, error }: { health: HealthStatus | null; error: string | null }) {
  return (
    <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.08em] text-slate-500">Health</p>
          <p className="mt-2 text-2xl font-semibold text-ink">{health?.status ?? "unavailable"}</p>
          <p className="mt-1 text-sm text-slate-500">{health ? formatDateTime(health.timestamp) : error ?? "Health check unavailable"}</p>
        </div>
        <div className="flex h-9 w-9 items-center justify-center rounded border border-line bg-mist text-brand">
          <Server className="h-4 w-4" aria-hidden="true" />
        </div>
      </div>
      {health ? (
        <dl className="mt-4 grid grid-cols-3 gap-2 text-sm">
          <div>
            <dt className="text-slate-500">DB</dt>
            <dd className="font-medium text-slate-800">{health.database_status}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Redis</dt>
            <dd className="font-medium text-slate-800">{health.redis_status}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Celery</dt>
            <dd className="font-medium text-slate-800">{health.celery_queue_reachable ? "ok" : "error"}</dd>
          </div>
        </dl>
      ) : null}
    </section>
  );
}

function QueueMetricsCard({ metrics, error }: { metrics: QueueMetrics | null; error: string | null }) {
  return (
    <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.08em] text-slate-500">Queue</p>
          <p className="mt-2 text-2xl font-semibold text-ink">{metrics?.pending_scan_task_count ?? "-"}</p>
          <p className="mt-1 text-sm text-slate-500">{metrics ? `${metrics.queue_name} pending scans` : error ?? "Queue metrics unavailable"}</p>
        </div>
        <div className="flex h-9 w-9 items-center justify-center rounded border border-line bg-mist text-brand">
          <Activity className="h-4 w-4" aria-hidden="true" />
        </div>
      </div>
      {metrics ? (
        <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
          <span className="inline-flex rounded border border-line bg-mist px-2 py-0.5 font-medium text-slate-700">
            {metrics.redis_connected ? "redis ok" : "redis error"}
          </span>
          <Link className="focus-ring rounded px-2 py-1 font-medium text-brand hover:bg-mist" href="/admin/dead-letter-scans">
            {metrics.dead_letter_count} dead letters
          </Link>
        </div>
      ) : null}
    </section>
  );
}

export default function DashboardPage() {
  const loader = useCallback(() => loadDashboardView(), []);
  const { data, error, isLoading, reload } = useApiResource(loader);

  return (
    <AppShell title="Dashboard">
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
            <MetricCard icon={GitBranch} label="Repositories" value={data.dashboard.summary.total_repositories} />
            <MetricCard icon={ListChecks} label="Total scans" value={data.dashboard.summary.total_scans} />
            <MetricCard icon={CheckCircle2} label="Completed" value={data.dashboard.summary.completed_scans} />
            <MetricCard icon={XCircle} label="Failed" value={data.dashboard.summary.failed_scans} />
            <MetricCard icon={AlertTriangle} label="High risk" value={data.dashboard.summary.high_risk_scans} />
            <MetricCard icon={Gauge} label="Average risk" value={formatScore(data.dashboard.summary.average_risk_score)} detail="/100" />
          </section>

          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-medium uppercase tracking-[0.08em] text-slate-500">Risk summary</p>
                  <p className="mt-2 text-2xl font-semibold text-ink">{formatScore(data.dashboard.summary.average_risk_score)}</p>
                  <p className="mt-1 text-sm text-slate-500">average scan risk</p>
                </div>
                <div className="flex h-9 w-9 items-center justify-center rounded border border-line bg-mist text-brand">
                  <ShieldAlert className="h-4 w-4" aria-hidden="true" />
                </div>
              </div>
              <dl className="mt-4 grid grid-cols-3 gap-2 text-sm">
                <div>
                  <dt className="text-slate-500">High</dt>
                  <dd className="font-semibold text-ink">{data.dashboard.summary.high_risk_scans}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Failed</dt>
                  <dd className="font-semibold text-ink">{data.dashboard.summary.failed_scans}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Done</dt>
                  <dd className="font-semibold text-ink">{data.dashboard.summary.completed_scans}</dd>
                </div>
              </dl>
            </section>
            <HealthStatusCard health={data.health} error={data.healthError} />
            <QueueMetricsCard metrics={data.queueMetrics} error={data.queueMetricsError} />
          </section>

          <section className="rounded-lg border border-line bg-panel shadow-surface">
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <h2 className="text-sm font-semibold text-ink">Recent scans</h2>
              <Link className="focus-ring rounded px-2 py-1 text-sm font-medium text-brand hover:bg-mist" href="/scans">
                View all
              </Link>
            </div>
            {data.dashboard.recent_scans.length === 0 ? (
              <EmptyState
                icon={ListChecks}
                title="No scans yet"
                description="Scans appear here automatically once a connected repository receives a pull request. To populate a demo, run the seed data script."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-line text-sm">
                  <thead className="bg-mist text-left text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                    <tr>
                      <th className="px-4 py-3">Repository</th>
                      <th className="px-4 py-3">PR</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Risk</th>
                      <th className="px-4 py-3">Findings</th>
                      <th className="px-4 py-3">Created</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {data.dashboard.recent_scans.map((scan) => (
                      <tr key={scan.scan_id} className="hover:bg-mist/70">
                        <td className="whitespace-nowrap px-4 py-3 font-medium text-ink">{scan.repository}</td>
                        <td className="whitespace-nowrap px-4 py-3">
                          <Link className="focus-ring rounded text-brand hover:underline" href={`/scans/${scan.scan_id}`}>
                            #{scan.pr_number}
                          </Link>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3">
                          <StatusBadge status={scan.status} />
                        </td>
                        <td className="whitespace-nowrap px-4 py-3">
                          <div className="flex items-center gap-2">
                            <RiskBadge level={scan.risk_level} />
                            <span className="text-slate-500">{scan.risk_score ?? "-"}</span>
                          </div>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-slate-700">{scan.findings_count}</td>
                        <td className="whitespace-nowrap px-4 py-3 text-slate-500">{formatDateTime(scan.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      ) : null}
    </AppShell>
  );
}
