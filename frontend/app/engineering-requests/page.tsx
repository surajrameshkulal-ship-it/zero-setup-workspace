"use client";

import Link from "next/link";
import { FormEvent, useCallback, useState } from "react";
import { Bot, RefreshCw, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { PriorityBadge, RequestStatusBadge, RiskBadge } from "@/components/badges";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/data-state";
import { createEngineeringRequest, listEngineeringRequests, listRepositories } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApiResource } from "@/hooks/use-api-resource";
import type { EngineeringRequestPriority, EngineeringRequestType } from "@/types/api";

const REQUEST_TYPES: EngineeringRequestType[] = [
  "bug",
  "feature",
  "refactor",
  "docs",
  "security",
  "performance",
  "other"
];
const PRIORITIES: EngineeringRequestPriority[] = ["low", "medium", "high", "urgent"];

export default function EngineeringRequestsPage() {
  const loader = useCallback(async () => {
    const [requests, repositories] = await Promise.all([listEngineeringRequests(), listRepositories()]);
    return { requests, repositories };
  }, []);
  const { data, error, isLoading, reload } = useApiResource(loader);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [requestType, setRequestType] = useState<EngineeringRequestType>("feature");
  const [priority, setPriority] = useState<EngineeringRequestPriority>("medium");
  const [repositoryId, setRepositoryId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setSubmitting(true);
    try {
      await createEngineeringRequest({
        title,
        description,
        request_type: requestType,
        priority,
        repository_id: repositoryId || null
      });
      setTitle("");
      setDescription("");
      setRequestType("feature");
      setPriority("medium");
      setRepositoryId("");
      await reload();
    } catch (caught) {
      setFormError(caught instanceof Error ? caught.message : "Could not create request");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell
      title="Engineering requests"
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
      <div className="mb-4 flex items-start gap-2 rounded-lg border border-violet-200 bg-violet-50 p-3 text-sm text-violet-900">
        <ShieldCheck className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
        <p>
          The AI Engineering Agent only produces a <strong>plan</strong>. It never deploys, merges, or pushes to main.
          Every change requires human approval and a GitHub pull request.
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-[380px_1fr]">
        <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
          <div className="mb-3 flex items-center gap-2">
            <Bot className="h-4 w-4 text-brand" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-ink">New request</h2>
          </div>
          <form className="space-y-3" onSubmit={onSubmit}>
            <label className="block space-y-1 text-sm">
              <span className="font-medium text-slate-700">Title</span>
              <input
                className="focus-ring w-full rounded border border-line bg-white px-3 py-2"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                required
                minLength={3}
              />
            </label>
            <label className="block space-y-1 text-sm">
              <span className="font-medium text-slate-700">Description</span>
              <textarea
                className="focus-ring min-h-28 w-full rounded border border-line bg-white px-3 py-2"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                required
              />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block space-y-1 text-sm">
                <span className="font-medium text-slate-700">Type</span>
                <select
                  className="focus-ring w-full rounded border border-line bg-white px-3 py-2"
                  value={requestType}
                  onChange={(event) => setRequestType(event.target.value as EngineeringRequestType)}
                >
                  {REQUEST_TYPES.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block space-y-1 text-sm">
                <span className="font-medium text-slate-700">Priority</span>
                <select
                  className="focus-ring w-full rounded border border-line bg-white px-3 py-2"
                  value={priority}
                  onChange={(event) => setPriority(event.target.value as EngineeringRequestPriority)}
                >
                  {PRIORITIES.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="block space-y-1 text-sm">
              <span className="font-medium text-slate-700">Repository (optional)</span>
              <select
                className="focus-ring w-full rounded border border-line bg-white px-3 py-2"
                value={repositoryId}
                onChange={(event) => setRepositoryId(event.target.value)}
              >
                <option value="">No specific repository</option>
                {data?.repositories.map((repository) => (
                  <option key={repository.id} value={repository.id}>
                    {repository.full_name}
                  </option>
                ))}
              </select>
            </label>
            {formError ? (
              <div className="rounded border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{formError}</div>
            ) : null}
            <button
              type="submit"
              className="focus-ring inline-flex w-full items-center justify-center gap-2 rounded bg-brand px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#125870] disabled:cursor-not-allowed disabled:opacity-70"
              disabled={submitting}
            >
              {submitting ? "Submitting" : "Submit request"}
            </button>
          </form>
        </section>

        <section>
          {isLoading ? <TableSkeleton rows={5} columns={5} /> : null}
          {error ? <ErrorState message={error} onRetry={() => reload().catch(() => undefined)} /> : null}
          {data ? (
            <div className="rounded-lg border border-line bg-panel shadow-surface">
              <div className="border-b border-line px-4 py-3">
                <h2 className="text-sm font-semibold text-ink">Requests</h2>
              </div>
              {data.requests.length === 0 ? (
                <EmptyState
                  icon={Bot}
                  title="No engineering requests yet"
                  description="Submit a request on the left. The AI agent will analyze it and propose a plan for your approval."
                />
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-line text-sm">
                    <thead className="bg-mist text-left text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                      <tr>
                        <th className="px-4 py-3">Title</th>
                        <th className="px-4 py-3">Type</th>
                        <th className="px-4 py-3">Priority</th>
                        <th className="px-4 py-3">Status</th>
                        <th className="px-4 py-3">Risk</th>
                        <th className="px-4 py-3">Created</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {data.requests.map((request) => (
                        <tr key={request.id} className="hover:bg-mist/70">
                          <td className="min-w-64 px-4 py-3">
                            <Link className="focus-ring rounded font-medium text-brand hover:underline" href={`/engineering-requests/${request.id}`}>
                              {request.title}
                            </Link>
                            {request.repository_full_name ? (
                              <div className="mt-1 text-xs text-slate-500">{request.repository_full_name}</div>
                            ) : null}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3 text-slate-700">{request.request_type}</td>
                          <td className="whitespace-nowrap px-4 py-3">
                            <PriorityBadge priority={request.priority} />
                          </td>
                          <td className="whitespace-nowrap px-4 py-3">
                            <RequestStatusBadge status={request.status} />
                          </td>
                          <td className="whitespace-nowrap px-4 py-3">
                            <RiskBadge level={request.risk_level} />
                          </td>
                          <td className="whitespace-nowrap px-4 py-3 text-slate-500">{formatDateTime(request.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : null}
        </section>
      </div>
    </AppShell>
  );
}
