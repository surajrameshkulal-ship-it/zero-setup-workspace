"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { ArrowLeft, ExternalLink, Play, Rocket, Square, Trash2 } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/badges";
import { EmptyState, ErrorState, LoadingState } from "@/components/data-state";
import { ActionButton, SectionCard } from "@/components/ui";
import {
  deleteWorkspaceInstance,
  getLatestWorkspaceInstance,
  getRepository,
  launchWorkspaceInstance,
  stopWorkspaceInstance
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApiResource } from "@/hooks/use-api-resource";
import type { WorkspaceInstance } from "@/types/api";

const TRANSITIONAL = new Set(["pending", "provisioning", "installing", "starting"]);
const ACTIVE = new Set(["running", "pending", "provisioning", "installing", "starting"]);

function statusTone(status: string) {
  if (status === "running") return "success" as const;
  if (status === "failed") return "danger" as const;
  if (status === "stopped") return "neutral" as const;
  return "info" as const;
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">{label}</dt>
      <dd className="mt-1 font-mono text-sm text-slate-800">{value || "—"}</dd>
    </div>
  );
}

export default function LaunchPage({ params }: { params: Promise<{ repositoryId: string }> }) {
  const { repositoryId } = use(params);
  const loader = useCallback(async () => {
    const [repository, instance] = await Promise.all([
      getRepository(repositoryId),
      getLatestWorkspaceInstance(repositoryId)
    ]);
    return { repository, instance };
  }, [repositoryId]);
  const { data, error, isLoading, reload } = useApiResource(loader);

  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const instance: WorkspaceInstance | null = data?.instance ?? null;
  const status = instance?.status ?? "";

  // Poll while the sandbox is moving through its lifecycle.
  useEffect(() => {
    if (!TRANSITIONAL.has(status)) return;
    const timer = setInterval(() => {
      reload().catch(() => undefined);
    }, 3000);
    return () => clearInterval(timer);
  }, [status, reload]);

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

  const canStop = instance && ACTIVE.has(instance.status) && instance.status !== "stopped";

  return (
    <AppShell
      title={data ? `${data.repository.full_name} · Launch` : "Launch"}
      description="Run the project in an isolated local sandbox"
      actions={
        <Link
          className="focus-ring inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-panel text-slate-700 hover:bg-mist"
          href="/repositories"
          title="Repositories"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </Link>
      }
    >
      {isLoading ? <LoadingState label="Loading sandbox" /> : null}
      {error ? <ErrorState message={error} onRetry={() => reload().catch(() => undefined)} /> : null}
      {data ? (
        <div className="space-y-6">
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-panel p-5 shadow-surface">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-soft text-brand ring-1 ring-brand/10">
                <Rocket className="h-4 w-4" aria-hidden="true" />
              </span>
              <div>
                <div className="text-sm font-semibold text-ink">Sandbox lifecycle</div>
                <div className="text-xs text-slate-500">
                  Fetches the repo into an isolated workspace, installs dependencies, starts the runtime, and probes
                  readiness. Read-only checkout — never merges, deploys, or modifies the repository.
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <ActionButton
                icon={Play}
                loading={busy === "launch"}
                onClick={() => run("launch", () => launchWorkspaceInstance(repositoryId))}
              >
                {instance ? "Relaunch" : "Launch sandbox"}
              </ActionButton>
              {canStop ? (
                <ActionButton
                  variant="secondary"
                  icon={Square}
                  loading={busy === "stop"}
                  onClick={() => instance && run("stop", () => stopWorkspaceInstance(instance.id))}
                >
                  Stop
                </ActionButton>
              ) : null}
              {instance ? (
                <ActionButton
                  variant="danger"
                  icon={Trash2}
                  loading={busy === "delete"}
                  onClick={() => run("delete", () => deleteWorkspaceInstance(instance.id))}
                >
                  Delete
                </ActionButton>
              ) : null}
            </div>
          </section>

          {actionError ? <ErrorState message={actionError} /> : null}

          {!instance ? (
            <EmptyState
              icon={Rocket}
              title="No sandbox yet"
              description="Launch an isolated sandbox from the workspace provision plan (generate the provision plan first if you haven't)."
            />
          ) : (
            <>
              <SectionCard
                title="Status"
                actions={
                  <div className="flex items-center gap-2">
                    {TRANSITIONAL.has(status) ? (
                      <span className="text-xs text-slate-400">auto-refreshing…</span>
                    ) : null}
                    <Badge tone={statusTone(status)}>{status}</Badge>
                  </div>
                }
              >
                <dl className="grid gap-4 text-sm sm:grid-cols-2 xl:grid-cols-3">
                  <Field label="Runtime" value={instance.runtime} />
                  <div>
                    <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Preview URL</dt>
                    <dd className="mt-1 font-mono text-sm">
                      {instance.preview_url && instance.preview_url.startsWith("http") ? (
                        <a className="inline-flex items-center gap-1 text-brand hover:underline" href={instance.preview_url} target="_blank" rel="noreferrer">
                          {instance.preview_url}
                          <ExternalLink className="h-3 w-3" aria-hidden="true" />
                        </a>
                      ) : (
                        instance.preview_url || "—"
                      )}
                    </dd>
                  </div>
                  <Field label="Ports" value={instance.exposed_ports.join(", ") || null} />
                  <Field label="Install command" value={instance.install_command} />
                  <Field label="Start command" value={instance.runtime_command} />
                  <Field label="Started" value={formatDateTime(instance.created_at)} />
                </dl>
                {instance.error_message ? (
                  <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
                    {instance.error_message}
                  </div>
                ) : null}
              </SectionCard>

              <SectionCard title="Logs" bodyClassName="p-0">
                {instance.logs.length === 0 ? (
                  <p className="p-5 text-sm text-slate-500">No logs yet.</p>
                ) : (
                  <pre className="max-h-96 overflow-auto rounded-b-xl bg-ink/95 p-4 font-mono text-xs leading-relaxed text-mist">
                    {instance.logs.map((l) => `[${l.stream}] ${l.message}`).join("\n")}
                  </pre>
                )}
              </SectionCard>
            </>
          )}
        </div>
      ) : null}
    </AppShell>
  );
}
