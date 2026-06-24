"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { RefreshCw } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { RiskBadge, StatusBadge } from "@/components/badges";
import { EmptyState, ErrorState, LoadingState } from "@/components/data-state";
import { listRepositories, listScans } from "@/lib/api";
import { useApiResource } from "@/hooks/use-api-resource";
import type { RiskLevel, ScanStatus } from "@/types/api";

export default function ScansPage() {
  const [repositoryId, setRepositoryId] = useState("");
  const [status, setStatus] = useState<ScanStatus | "">("");
  const [riskLevel, setRiskLevel] = useState<RiskLevel | "">("");
  const loader = useCallback(
    async () => {
      const [repositories, scans] = await Promise.all([
        listRepositories(),
        listScans({ repository_id: repositoryId, status, risk_level: riskLevel })
      ]);
      return { repositories, scans };
    },
    [repositoryId, riskLevel, status]
  );
  const { data, error, isLoading, reload } = useApiResource(loader);

  return (
    <AppShell
      title="Scans"
      actions={
        <button
          type="button"
          className="focus-ring inline-flex h-9 w-9 items-center justify-center rounded border border-line bg-panel text-slate-700 hover:bg-mist"
          onClick={() => reload().catch(() => undefined)}
          title="Refresh"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
        </button>
      }
    >
      <section className="mb-4 grid gap-3 rounded-lg border border-line bg-panel p-4 shadow-surface md:grid-cols-3">
        <label className="space-y-1 text-sm">
          <span className="font-medium text-slate-700">Repository</span>
          <select
            className="focus-ring w-full rounded border border-line bg-white px-3 py-2"
            value={repositoryId}
            onChange={(event) => setRepositoryId(event.target.value)}
          >
            <option value="">All repositories</option>
            {data?.repositories.map((repository) => (
              <option key={repository.id} value={repository.id}>
                {repository.full_name}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="font-medium text-slate-700">Status</span>
          <select
            className="focus-ring w-full rounded border border-line bg-white px-3 py-2"
            value={status}
            onChange={(event) => setStatus(event.target.value as ScanStatus | "")}
          >
            <option value="">Any status</option>
            <option value="queued">Queued</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="font-medium text-slate-700">Risk</span>
          <select
            className="focus-ring w-full rounded border border-line bg-white px-3 py-2"
            value={riskLevel}
            onChange={(event) => setRiskLevel(event.target.value as RiskLevel | "")}
          >
            <option value="">Any risk</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
        </label>
      </section>

      {isLoading ? <LoadingState label="Loading scans" /> : null}
      {error ? <ErrorState message={error} /> : null}
      {data ? (
        <section className="rounded-lg border border-line bg-panel shadow-surface">
          {data.scans.length === 0 ? (
            <EmptyState title="No scans match the selected filters" />
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
                  {data.scans.map((scan) => (
                    <tr key={scan.id} className="hover:bg-mist/70">
                      <td className="whitespace-nowrap px-4 py-3 font-medium text-ink">{scan.repository_full_name ?? scan.repository_id}</td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <Link className="focus-ring rounded text-brand hover:underline" href={`/scans/${scan.id}`}>
                          #{scan.github_pr_number}
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
      ) : null}
    </AppShell>
  );
}
