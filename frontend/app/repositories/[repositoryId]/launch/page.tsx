"use client";

import Link from "next/link";
import { use, useCallback, useState } from "react";
import { ArrowLeft, Play, Square, Rocket } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/data-state";
import { getRepository, getWorkspaceLaunch, launchWorkspace, stopWorkspaceLaunch } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApiResource } from "@/hooks/use-api-resource";

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">{label}</dt>
      <dd className="mt-1 font-mono text-sm text-slate-800">{value || "—"}</dd>
    </div>
  );
}

function statusColor(status: string): string {
  if (status === "healthy" || status === "running") return "border-emerald-300 bg-emerald-50 text-emerald-800";
  if (status === "unhealthy" || status === "expired") return "border-amber-300 bg-amber-50 text-amber-800";
  if (status === "failed") return "border-rose-300 bg-rose-50 text-rose-800";
  if (status === "stopped") return "border-line bg-mist text-slate-600";
  return "border-sky-300 bg-sky-50 text-sky-800";
}

export default function LaunchPage({ params }: { params: Promise<{ repositoryId: string }> }) {
  const { repositoryId } = use(params);
  const loader = useCallback(async () => {
    const [repository, launch] = await Promise.all([
      getRepository(repositoryId),
      getWorkspaceLaunch(repositoryId)
    ]);
    return { repository, launch };
  }, [repositoryId]);
  const { data, error, isLoading, reload } = useApiResource(loader);

  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const run = useCallback(
    async (label: string, fn: () => Promise<unknown>) => {
      setActionError(null);
      setBusy(label);
      try {
        await fn();
        await reload();
      } catch (caught) {
        setActionError(caught instanceof Error ? caught.message : "Action failed");
      } finally {
        setBusy(null);
      }
    },
    [reload]
  );

  const launch = data?.launch ?? null;
  const active = launch && ["running", "healthy", "unhealthy"].includes(launch.status);
  const limits = launch?.resource_limits ?? {};

  return (
    <AppShell
      title={data ? `${data.repository.full_name} · Launch` : "Launch"}
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
      {isLoading ? <LoadingState label="Loading workspace launch" /> : null}
      {error ? <ErrorState message={error} onRetry={() => reload().catch(() => undefined)} /> : null}
      {data ? (
        <div className="space-y-6">
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-panel p-4 shadow-surface">
            <div className="flex items-center gap-2">
              <Rocket className="h-4 w-4 text-brand" aria-hidden="true" />
              <div>
                <div className="text-sm font-semibold text-ink">Local sandbox</div>
                <div className="text-xs text-slate-500">
                  Runs the project in an isolated container: read-only source, no secrets, resource quotas, and a TTL.
                  Never merges, deploys, or modifies the repository.
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => run("launch", () => launchWorkspace(repositoryId))}
                className="focus-ring inline-flex items-center gap-2 rounded bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-[#125870] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                {busy === "launch" ? "Launching" : active ? "Relaunch" : "Launch sandbox"}
              </button>
              {active ? (
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => run("stop", () => stopWorkspaceLaunch(repositoryId))}
                  className="focus-ring inline-flex items-center gap-2 rounded border border-line bg-panel px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-mist disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Square className="h-4 w-4" aria-hidden="true" />
                  {busy === "stop" ? "Stopping" : "Stop"}
                </button>
              ) : null}
            </div>
          </section>

          {actionError ? <ErrorState message={actionError} /> : null}

          {!launch ? (
            <EmptyState
              icon={Rocket}
              title="No sandbox yet"
              description="Launch an isolated local sandbox from the workspace provision plan (generate the provision plan first if you haven't)."
            />
          ) : (
            <>
              <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-sm font-semibold text-ink">Status</h2>
                  <span className={`inline-flex rounded border px-2 py-0.5 text-xs font-semibold ${statusColor(launch.status)}`}>
                    {launch.status}
                    {launch.health_status ? ` · ${launch.health_status}` : ""}
                  </span>
                </div>
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
                  <Field label="Runtime" value={launch.runtime} />
                  <Field label="Image" value={launch.image} />
                  <Field label="Container" value={launch.container_id} />
                  <div>
                    <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">URL</dt>
                    <dd className="mt-1 font-mono text-sm">
                      {launch.published_url ? (
                        <a className="text-brand hover:underline" href={launch.published_url} target="_blank" rel="noreferrer">
                          {launch.published_url}
                        </a>
                      ) : "—"}
                    </dd>
                  </div>
                  <Field label="Start command" value={launch.start_command} />
                  <Field
                    label="Ports"
                    value={launch.port_mappings.map((p) => `${p.host}→${p.container}`).join(", ") || null}
                  />
                  <Field label="Started" value={launch.started_at ? formatDateTime(launch.started_at) : null} />
                  <Field label="Expires (TTL)" value={launch.expires_at ? formatDateTime(launch.expires_at) : null} />
                </dl>
                {launch.failure_reason ? (
                  <div className="mt-3 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
                    {launch.failure_reason}
                  </div>
                ) : null}
                {launch.health_detail ? (
                  <div className="mt-3 text-xs text-slate-500">Health: {launch.health_detail}</div>
                ) : null}
              </section>

              <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
                <h2 className="text-sm font-semibold text-ink">Isolation &amp; quotas</h2>
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3 xl:grid-cols-5">
                  <div><dt className="text-xs text-slate-500">CPU</dt><dd className="font-semibold text-ink">{String(limits.cpu ?? "—")}</dd></div>
                  <div><dt className="text-xs text-slate-500">Memory</dt><dd className="font-semibold text-ink">{String(limits.memory_mb ?? "—")} MB</dd></div>
                  <div><dt className="text-xs text-slate-500">PIDs</dt><dd className="font-semibold text-ink">{String(limits.pids_limit ?? "—")}</dd></div>
                  <div><dt className="text-xs text-slate-500">Network</dt><dd className="font-semibold text-ink">{String(limits.network ?? "—")}</dd></div>
                  <div><dt className="text-xs text-slate-500">TTL</dt><dd className="font-semibold text-ink">{Math.round(launch.ttl_seconds / 60)} min</dd></div>
                </dl>
                <p className="mt-3 text-xs text-slate-500">
                  Read-only source mount · secrets never materialized · no merge/deploy/push · auto-cleanup on TTL.
                </p>
              </section>

              <section className="rounded-lg border border-line bg-panel shadow-surface">
                <div className="border-b border-line px-4 py-3"><h2 className="text-sm font-semibold text-ink">Logs</h2></div>
                <div className="p-4">
                  {launch.logs_tail.length === 0 ? (
                    <p className="text-sm text-slate-500">No logs.</p>
                  ) : (
                    <pre className="max-h-80 overflow-auto rounded bg-ink/95 p-3 font-mono text-xs leading-relaxed text-mist">
                      {launch.logs_tail.join("\n")}
                    </pre>
                  )}
                </div>
              </section>

              <p className="text-xs text-slate-400">Last updated {formatDateTime(launch.updated_at)}.</p>
            </>
          )}
        </div>
      ) : null}
    </AppShell>
  );
}
