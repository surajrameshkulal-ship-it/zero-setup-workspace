"use client";

import Link from "next/link";
import { useCallback } from "react";
import { GitBranch, RefreshCw, Search } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/data-state";
import { listRepositories } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApiResource } from "@/hooks/use-api-resource";

export default function RepositoriesPage() {
  const loader = useCallback(() => listRepositories(), []);
  const { data, error, isLoading, reload } = useApiResource(loader);

  return (
    <AppShell
      title="Repositories"
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
      {isLoading ? <TableSkeleton rows={5} columns={6} /> : null}
      {error ? <ErrorState message={error} onRetry={() => reload().catch(() => undefined)} /> : null}
      {data ? (
        <section className="rounded-lg border border-line bg-panel shadow-surface">
          <div className="flex items-center gap-2 border-b border-line px-4 py-3">
            <Search className="h-4 w-4 text-slate-500" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-ink">Connected repositories</h2>
          </div>
          {data.length === 0 ? (
            <EmptyState
              icon={GitBranch}
              title="No repositories connected"
              description="Install the CodeDNA GitHub App and register a repository to start scanning pull requests. For a demo, run the seed data script."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-line text-sm">
                <thead className="bg-mist text-left text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                  <tr>
                    <th className="px-4 py-3">Repository</th>
                    <th className="px-4 py-3">Default branch</th>
                    <th className="px-4 py-3">GitHub ID</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Created</th>
                    <th className="px-4 py-3"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {data.map((repository) => (
                    <tr key={repository.id} className="hover:bg-mist/70">
                      <td className="whitespace-nowrap px-4 py-3 font-medium text-ink">{repository.full_name}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-slate-700">{repository.default_branch}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-slate-500">{repository.github_repository_id}</td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span className="inline-flex rounded border border-line bg-mist px-2 py-0.5 text-xs font-medium text-slate-700">
                          {repository.is_active ? "active" : "inactive"}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-slate-500">{formatDate(repository.created_at)}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        <Link
                          className="focus-ring rounded px-2 py-1 text-sm font-medium text-brand hover:bg-mist"
                          href={`/repositories/${repository.id}/dna`}
                        >
                          DNA
                        </Link>
                        <Link
                          className="focus-ring rounded px-2 py-1 text-sm font-medium text-brand hover:bg-mist"
                          href={`/repositories/${repository.id}/setup-intent`}
                        >
                          Setup
                        </Link>
                        <Link
                          className="focus-ring rounded px-2 py-1 text-sm font-medium text-brand hover:bg-mist"
                          href={`/repositories/${repository.id}/environment`}
                        >
                          Env
                        </Link>
                        <Link
                          className="focus-ring rounded px-2 py-1 text-sm font-medium text-brand hover:bg-mist"
                          href={`/repositories/${repository.id}/workspace`}
                        >
                          Workspace
                        </Link>
                        <Link
                          className="focus-ring rounded px-2 py-1 text-sm font-medium text-brand hover:bg-mist"
                          href={`/repositories/${repository.id}/provision`}
                        >
                          Provision
                        </Link>
                        <Link
                          className="focus-ring rounded px-2 py-1 text-sm font-medium text-brand hover:bg-mist"
                          href={`/repositories/${repository.id}/scans`}
                        >
                          Scans
                        </Link>
                      </td>
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
