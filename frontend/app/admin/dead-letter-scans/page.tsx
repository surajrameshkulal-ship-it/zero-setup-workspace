"use client";

import Link from "next/link";
import { useCallback } from "react";
import { RefreshCw, ShieldAlert } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/data-state";
import { listDeadLetterScans } from "@/lib/api";
import { formatDateTime, shortSha } from "@/lib/format";
import { useApiResource } from "@/hooks/use-api-resource";

export default function DeadLetterScansPage() {
  const loader = useCallback(() => listDeadLetterScans(), []);
  const { data, error, isLoading, reload } = useApiResource(loader);

  return (
    <AppShell
      title="Dead-letter scans"
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
      {isLoading ? <TableSkeleton rows={4} columns={7} /> : null}
      {error ? <ErrorState message={error} onRetry={() => reload().catch(() => undefined)} /> : null}
      {data ? (
        <section className="rounded-lg border border-line bg-panel shadow-surface">
          <div className="flex items-center gap-2 border-b border-line px-4 py-3">
            <ShieldAlert className="h-4 w-4 text-slate-500" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-ink">Permanent scan failures</h2>
          </div>
          {data.length === 0 ? (
            <EmptyState
              icon={ShieldAlert}
              title="No dead-letter scans"
              description="Nothing here is good news — no scans have exhausted their retries and landed in the dead-letter queue."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-line text-sm">
                <thead className="bg-mist text-left text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                  <tr>
                    <th className="px-4 py-3">Scan</th>
                    <th className="px-4 py-3">Repository</th>
                    <th className="px-4 py-3">PR</th>
                    <th className="px-4 py-3">Head SHA</th>
                    <th className="px-4 py-3">Retries</th>
                    <th className="px-4 py-3">Failed</th>
                    <th className="px-4 py-3">Error</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {data.map((item) => (
                    <tr key={item.scan_id} className="hover:bg-mist/70">
                      <td className="whitespace-nowrap px-4 py-3">
                        <Link className="focus-ring rounded text-brand hover:underline" href={`/scans/${item.scan_id}`}>
                          {shortSha(item.scan_id, 8)}
                        </Link>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-slate-600">{shortSha(item.repository_id, 8)}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-slate-700">#{item.pull_request_number}</td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-slate-600">{shortSha(item.head_sha)}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-slate-700">{item.retry_count}</td>
                      <td className="whitespace-nowrap px-4 py-3 text-slate-500">{formatDateTime(item.failed_at)}</td>
                      <td className="min-w-80 px-4 py-3 text-slate-700">{item.error_message}</td>
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
