"use client";

import Link from "next/link";
import { useCallback } from "react";
import { AlertTriangle, CheckCircle2, Gauge, GitBranch, ListChecks, XCircle } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { RiskBadge, StatusBadge } from "@/components/badges";
import { EmptyState, ErrorState, LoadingState } from "@/components/data-state";
import { MetricCard } from "@/components/metric-card";
import { getDashboard } from "@/lib/api";
import { useApiResource } from "@/hooks/use-api-resource";

export default function DashboardPage() {
  const loader = useCallback(() => getDashboard(), []);
  const { data, error, isLoading } = useApiResource(loader);

  return (
    <AppShell title="Dashboard">
      {isLoading ? <LoadingState label="Loading dashboard" /> : null}
      {error ? <ErrorState message={error} /> : null}
      {data ? (
        <div className="space-y-6">
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <MetricCard icon={GitBranch} label="Repositories" value={data.summary.total_repositories} />
            <MetricCard icon={ListChecks} label="Total scans" value={data.summary.total_scans} />
            <MetricCard icon={CheckCircle2} label="Completed" value={data.summary.completed_scans} />
            <MetricCard icon={XCircle} label="Failed" value={data.summary.failed_scans} />
            <MetricCard icon={AlertTriangle} label="High risk" value={data.summary.high_risk_scans} />
            <MetricCard icon={Gauge} label="Average risk" value={data.summary.average_risk_score.toFixed(1)} detail="/100" />
          </section>

          <section className="rounded-lg border border-line bg-panel shadow-surface">
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <h2 className="text-sm font-semibold text-ink">Recent scans</h2>
              <Link className="focus-ring rounded px-2 py-1 text-sm font-medium text-brand hover:bg-mist" href="/scans">
                View all
              </Link>
            </div>
            {data.recent_scans.length === 0 ? (
              <EmptyState title="No scans yet" />
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
                    {data.recent_scans.map((scan) => (
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
                        <td className="whitespace-nowrap px-4 py-3 text-slate-500">{new Date(scan.created_at).toLocaleString()}</td>
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
