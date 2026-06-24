"use client";

import Link from "next/link";
import { use, useCallback } from "react";
import { ArrowLeft } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { RiskBadge, StatusBadge } from "@/components/badges";
import { EmptyState, ErrorState, LoadingState } from "@/components/data-state";
import { getRepository, listRepositoryScans } from "@/lib/api";
import { useApiResource } from "@/hooks/use-api-resource";

export default function RepositoryScanHistoryPage({
  params,
}: {
  params: Promise<{ repositoryId: string }>;
}) {
  const { repositoryId } = use(params);

  const loader = useCallback(
    async () => {
      const [repository, scans] = await Promise.all([
        getRepository(repositoryId),
        listRepositoryScans(repositoryId),
      ]);

      return { repository, scans };
    },
    [repositoryId]
  );
  const { data, error, isLoading } = useApiResource(loader);

  return (
    <AppShell
      title={data?.repository.full_name ?? "Repository scans"}
      actions={
        <Link
          className="focus-ring inline-flex h-9 w-9 items-center justify-center rounded border border-line bg-panel text-slate-700 hover:bg-mist"
          href="/repositories"
          title="Repositories"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </Link>
      }
    >
      {isLoading ? <LoadingState label="Loading scan history" /> : null}
      {error ? <ErrorState message={error} /> : null}
      {data ? (
        <section className="rounded-lg border border-line bg-panel shadow-surface">
          <div className="border-b border-line px-4 py-3">
            <h2 className="text-sm font-semibold text-ink">Scan history</h2>
            <p className="mt-1 text-sm text-slate-500">{data.repository.default_branch}</p>
          </div>
          {data.scans.length === 0 ? (
            <EmptyState title="No scans for this repository" />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-line text-sm">
                <thead className="bg-mist text-left text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                  <tr>
                    <th className="px-4 py-3">PR</th>
                    <th className="px-4 py-3">Title</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Risk</th>
                    <th className="px-4 py-3">Findings</th>
                    <th className="px-4 py-3">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {data.scans.map((scan) => (
                    <tr key={scan.id} className="hover:bg-mist/70">
                      <td className="whitespace-nowrap px-4 py-3">
                        <Link className="focus-ring rounded text-brand hover:underline" href={`/scans/${scan.id}`}>
                          #{scan.github_pr_number}
                        </Link>
                      </td>
                      <td className="min-w-64 px-4 py-3 text-slate-700">{scan.title ?? "-"}</td>
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
