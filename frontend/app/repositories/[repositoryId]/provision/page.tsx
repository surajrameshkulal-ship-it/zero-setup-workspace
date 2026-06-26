"use client";

import Link from "next/link";
import { use, useCallback, useState } from "react";
import { ArrowLeft, CheckCircle2, AlertTriangle, PackageCheck, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/data-state";
import { generateWorkspaceProvision, getRepository, getWorkspaceProvision } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApiResource } from "@/hooks/use-api-resource";

function Chips({ items }: { items: (string | number)[] }) {
  if (!items || items.length === 0) {
    return <span className="text-sm text-slate-400">—</span>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <span key={String(item)} className="inline-flex rounded border border-line bg-mist px-2 py-0.5 text-xs text-slate-700">
          {item}
        </span>
      ))}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">{label}</dt>
      <dd className="mt-1 font-mono text-sm text-slate-800">{value || "—"}</dd>
    </div>
  );
}

function readinessColor(score: number): string {
  if (score >= 80) return "border-emerald-300 bg-emerald-50 text-emerald-800";
  if (score >= 50) return "border-amber-300 bg-amber-50 text-amber-800";
  return "border-rose-300 bg-rose-50 text-rose-800";
}

export default function ProvisionPage({
  params
}: {
  params: Promise<{ repositoryId: string }>;
}) {
  const { repositoryId } = use(params);
  const loader = useCallback(async () => {
    const [repository, plan] = await Promise.all([
      getRepository(repositoryId),
      getWorkspaceProvision(repositoryId)
    ]);
    return { repository, plan };
  }, [repositoryId]);
  const { data, error, isLoading, reload } = useApiResource(loader);

  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function generate() {
    setActionError(null);
    setBusy(true);
    try {
      await generateWorkspaceProvision(repositoryId);
      await reload();
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Could not prepare workspace provision plan");
    } finally {
      setBusy(false);
    }
  }

  const plan = data?.plan ?? null;
  const dir = plan?.workspace_directory ?? {};
  const env = plan?.environment_preparation ?? {};
  const container = plan?.container_preparation ?? {};

  return (
    <AppShell
      title={data ? `${data.repository.full_name} · Provision` : "Provision"}
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
      {isLoading ? <LoadingState label="Loading provision plan" /> : null}
      {error ? <ErrorState message={error} onRetry={() => reload().catch(() => undefined)} /> : null}
      {data ? (
        <div className="space-y-6">
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-panel p-4 shadow-surface">
            <div className="flex items-center gap-2">
              <PackageCheck className="h-4 w-4 text-brand" aria-hidden="true" />
              <div>
                <div className="text-sm font-semibold text-ink">Workspace provision plan</div>
                <div className="text-xs text-slate-500">
                  Prepares everything needed to run the project later. Nothing is launched, executed, installed, or deployed.
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={generate}
              disabled={busy}
              className="focus-ring inline-flex items-center gap-2 rounded bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              {busy ? "Preparing" : plan ? "Regenerate" : "Prepare workspace"}
            </button>
          </section>

          {actionError ? <ErrorState message={actionError} /> : null}

          {!plan ? (
            <EmptyState
              icon={PackageCheck}
              title="No provision plan yet"
              description="Prepare a provision plan from the workspace blueprint (generate the blueprint first if you haven't)."
            />
          ) : (
            <>
              <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-sm font-semibold text-ink">Runtime &amp; readiness</h2>
                  <span className={`inline-flex rounded border px-2 py-0.5 text-xs font-semibold ${readinessColor(plan.readiness_score)}`}>
                    workspace ready {plan.readiness_score}%
                  </span>
                </div>
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-5">
                  <Field label="Language" value={plan.language} />
                  <Field label="Runtime" value={plan.runtime} />
                  <Field label="Version" value={plan.runtime_version} />
                  <Field label="Package manager" value={plan.package_manager} />
                  <Field label="Framework" value={plan.framework} />
                </dl>
              </section>

              <div className="grid gap-6 xl:grid-cols-2">
                <section className="rounded-lg border border-line bg-panel shadow-surface">
                  <div className="border-b border-line px-4 py-3">
                    <h2 className="text-sm font-semibold text-ink">Directory layout</h2>
                    <p className="mt-1 text-xs text-slate-500">{dir.note}</p>
                  </div>
                  <dl className="grid gap-3 p-4 text-sm">
                    <Field label="Workspace root" value={dir.workspace_root} />
                    <Field label="Repository" value={dir.repository_location} />
                    <Field label="Config" value={dir.config_directory} />
                    <Field label="Cache" value={dir.cache_directory} />
                    <Field label="Logs" value={dir.logs_directory} />
                    <Field label="Temp" value={dir.temp_directory} />
                  </dl>
                </section>

                <section className="rounded-lg border border-line bg-panel shadow-surface">
                  <div className="border-b border-line px-4 py-3">
                    <h2 className="text-sm font-semibold text-ink">Runtime &amp; environment preparation</h2>
                    <p className="mt-1 text-xs text-slate-500">{env.note}</p>
                  </div>
                  <dl className="grid gap-3 p-4 text-sm">
                    <div>
                      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Environment variables (names only)</dt>
                      <dd className="mt-1"><Chips items={env.env_template ?? []} /></dd>
                    </div>
                    <Field label="Generated template" value={env.generated_env_template} />
                    <div>
                      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Runtime version files</dt>
                      <dd className="mt-1"><Chips items={env.runtime_version_files ?? []} /></dd>
                    </div>
                    <Field label="Package manager config" value={env.package_manager_config?.config_file} />
                  </dl>
                </section>
              </div>

              <section className="rounded-lg border border-line bg-panel shadow-surface">
                <div className="border-b border-line px-4 py-3">
                  <h2 className="text-sm font-semibold text-ink">Dependency plan</h2>
                  <p className="mt-1 text-xs text-slate-500">Installation plan only — nothing is installed.</p>
                </div>
                <ul className="divide-y divide-line text-sm">
                  {plan.dependency_plan.map((step, i) => (
                    <li key={i} className="flex items-center justify-between gap-3 px-4 py-2">
                      <span className="font-mono text-slate-800">{step.command}</span>
                      <span className="inline-flex rounded border border-line bg-mist px-2 py-0.5 text-xs text-slate-600">{step.status}</span>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="rounded-lg border border-line bg-panel shadow-surface">
                <div className="border-b border-line px-4 py-3">
                  <h2 className="text-sm font-semibold text-ink">Docker plan</h2>
                  <p className="mt-1 text-xs text-slate-500">{container.note}</p>
                </div>
                <dl className="grid gap-3 p-4 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Image</dt>
                    <dd className="mt-1 font-mono text-slate-800">{container.docker_image_plan?.base_image}</dd>
                    <dd className="mt-0.5 text-xs text-slate-500">status: {container.docker_image_plan?.status}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Compose ({container.docker_compose_plan?.status})</dt>
                    <dd className="mt-1"><Chips items={container.docker_compose_plan?.services ?? []} /></dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Dev container</dt>
                    <dd className="mt-1 font-mono text-slate-800">{container.dev_container_plan?.file ?? "—"}</dd>
                    <dd className="mt-0.5 text-xs text-slate-500">status: {container.dev_container_plan?.status}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Network</dt>
                    <dd className="mt-1 text-xs text-slate-600">isolated: {String(container.network_plan?.isolated ?? true)}</dd>
                    <dd className="mt-1"><Chips items={container.network_plan?.exposed_ports ?? []} /></dd>
                  </div>
                </dl>
              </section>

              <section className="rounded-lg border border-line bg-panel shadow-surface">
                <div className="border-b border-line px-4 py-3"><h2 className="text-sm font-semibold text-ink">Startup sequence</h2></div>
                <ol className="divide-y divide-line text-sm">
                  {plan.startup_plan.map((phase) => (
                    <li key={phase.order} className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-brand text-[11px] font-semibold text-white">{phase.order}</span>
                        <span className="font-semibold text-ink">{phase.phase}</span>
                      </div>
                      <ul className="mt-1 list-disc pl-9 font-mono text-xs text-slate-600">
                        {phase.actions.map((a, i) => <li key={i}>{a}</li>)}
                      </ul>
                    </li>
                  ))}
                </ol>
              </section>

              <section className="rounded-lg border border-line bg-panel shadow-surface">
                <div className="border-b border-line px-4 py-3"><h2 className="text-sm font-semibold text-ink">Validation</h2></div>
                <ul className="divide-y divide-line text-sm">
                  {plan.validation.map((check) => (
                    <li key={check.label} className="flex items-start gap-3 px-4 py-2">
                      {check.status === "ok" ? (
                        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden="true" />
                      ) : (
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
                      )}
                      <div>
                        <div className="font-medium text-slate-800">{check.label}</div>
                        <div className="text-xs text-slate-500">{check.detail}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>

              <div className="grid gap-6 xl:grid-cols-2">
                <section className="rounded-lg border border-line bg-panel shadow-surface">
                  <div className="border-b border-line px-4 py-3"><h2 className="text-sm font-semibold text-ink">Warnings</h2></div>
                  <div className="p-4">
                    {plan.warnings.length === 0 ? <p className="text-sm text-emerald-700">None.</p> : (
                      <ul className="list-disc space-y-1 pl-5 text-sm text-amber-800">{plan.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
                    )}
                  </div>
                </section>
                <section className="rounded-lg border border-line bg-panel shadow-surface">
                  <div className="border-b border-line px-4 py-3"><h2 className="text-sm font-semibold text-ink">Recommendations</h2></div>
                  <div className="p-4">
                    {plan.recommendations.length === 0 ? <p className="text-sm text-slate-500">None.</p> : (
                      <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">{plan.recommendations.map((r, i) => <li key={i}>{r}</li>)}</ul>
                    )}
                  </div>
                </section>
              </div>

              <p className="text-xs text-slate-400">Last prepared {formatDateTime(plan.updated_at)}.</p>
            </>
          )}
        </div>
      ) : null}
    </AppShell>
  );
}
