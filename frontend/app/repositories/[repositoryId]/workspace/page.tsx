"use client";

import Link from "next/link";
import { use, useCallback, useState } from "react";
import { ArrowLeft, LayoutTemplate, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/data-state";
import { generateWorkspaceBlueprint, getRepository, getWorkspaceBlueprint } from "@/lib/api";
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

function Sequence({ title, steps }: { title: string; steps: string[] | undefined }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-[0.08em] text-slate-500">{title}</div>
      {!steps || steps.length === 0 ? (
        <p className="mt-1 text-sm text-slate-400">—</p>
      ) : (
        <ol className="mt-1 space-y-1 font-mono text-xs text-slate-700">
          {steps.map((s, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-slate-400">{i + 1}.</span>
              <span>{s}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function readinessColor(score: number): string {
  if (score >= 80) return "border-emerald-300 bg-emerald-50 text-emerald-800";
  if (score >= 50) return "border-amber-300 bg-amber-50 text-amber-800";
  return "border-rose-300 bg-rose-50 text-rose-800";
}

export default function WorkspacePage({
  params
}: {
  params: Promise<{ repositoryId: string }>;
}) {
  const { repositoryId } = use(params);
  const loader = useCallback(async () => {
    const [repository, blueprint] = await Promise.all([
      getRepository(repositoryId),
      getWorkspaceBlueprint(repositoryId)
    ]);
    return { repository, blueprint };
  }, [repositoryId]);
  const { data, error, isLoading, reload } = useApiResource(loader);

  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function generate() {
    setActionError(null);
    setBusy(true);
    try {
      await generateWorkspaceBlueprint(repositoryId);
      await reload();
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Could not generate workspace blueprint");
    } finally {
      setBusy(false);
    }
  }

  const bp = data?.blueprint ?? null;
  const structure = bp?.workspace_structure ?? {};
  const plan = bp?.startup_plan ?? {};
  const resources = bp?.workspace_resources ?? {};

  return (
    <AppShell
      title={data ? `${data.repository.full_name} · Workspace` : "Workspace"}
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
      {isLoading ? <LoadingState label="Loading workspace blueprint" /> : null}
      {error ? <ErrorState message={error} onRetry={() => reload().catch(() => undefined)} /> : null}
      {data ? (
        <div className="space-y-6">
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-panel p-4 shadow-surface">
            <div className="flex items-center gap-2">
              <LayoutTemplate className="h-4 w-4 text-brand" aria-hidden="true" />
              <div>
                <div className="text-sm font-semibold text-ink">Workspace blueprint</div>
                <div className="text-xs text-slate-500">
                  A reproducible plan for launching this project later. Nothing is launched, executed, or installed.
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
              {busy ? "Generating" : bp ? "Regenerate" : "Generate blueprint"}
            </button>
          </section>

          {actionError ? <ErrorState message={actionError} /> : null}

          {!bp ? (
            <EmptyState
              icon={LayoutTemplate}
              title="No workspace blueprint yet"
              description="Generate a workspace blueprint from the environment spec (generate the environment spec first if you haven't)."
            />
          ) : (
            <>
              <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-sm font-semibold text-ink">Runtime &amp; readiness</h2>
                  <span className={`inline-flex rounded border px-2 py-0.5 text-xs font-semibold ${readinessColor(bp.readiness_score)}`}>
                    readiness {bp.readiness_score}/100
                  </span>
                </div>
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-5">
                  <Field label="Language" value={bp.language} />
                  <Field label="Runtime" value={bp.runtime} />
                  <Field label="Version" value={bp.runtime_version} />
                  <Field label="Package manager" value={bp.package_manager} />
                  <Field label="Framework" value={bp.framework} />
                </dl>
              </section>

              <section className="rounded-lg border border-line bg-panel shadow-surface">
                <div className="border-b border-line px-4 py-3"><h2 className="text-sm font-semibold text-ink">Workspace structure</h2></div>
                <dl className="grid gap-3 p-4 text-sm sm:grid-cols-2 xl:grid-cols-3">
                  <div><dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Source</dt><dd className="mt-1"><Chips items={structure.source_directories ?? []} /></dd></div>
                  <div><dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Tests</dt><dd className="mt-1"><Chips items={structure.test_directories ?? []} /></dd></div>
                  <div><dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Docs</dt><dd className="mt-1"><Chips items={structure.documentation_directories ?? []} /></dd></div>
                  <div><dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Config</dt><dd className="mt-1"><Chips items={structure.configuration_directories ?? []} /></dd></div>
                  <div><dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Generated</dt><dd className="mt-1"><Chips items={structure.generated_directories ?? []} /></dd></div>
                  <div><dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Ignored</dt><dd className="mt-1"><Chips items={structure.ignored_directories ?? []} /></dd></div>
                </dl>
              </section>

              <section className="rounded-lg border border-line bg-panel shadow-surface">
                <div className="border-b border-line px-4 py-3">
                  <h2 className="text-sm font-semibold text-ink">Startup plan</h2>
                  <p className="mt-1 text-xs text-slate-500">{plan.note}</p>
                </div>
                <div className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-5">
                  <Sequence title="Install" steps={plan.install_sequence} />
                  <Sequence title="Build" steps={plan.build_sequence} />
                  <Sequence title="Start" steps={plan.start_sequence} />
                  <Sequence title="Health check" steps={plan.health_check_sequence} />
                  <Sequence title="Shutdown" steps={plan.shutdown_sequence} />
                </div>
              </section>

              <div className="grid gap-6 xl:grid-cols-2">
                <section className="rounded-lg border border-line bg-panel shadow-surface">
                  <div className="border-b border-line px-4 py-3"><h2 className="text-sm font-semibold text-ink">Docker assets</h2></div>
                  <ul className="divide-y divide-line text-sm">
                    {bp.docker_assets.map((a) => (
                      <li key={a.name} className="flex items-start justify-between gap-3 px-4 py-2">
                        <div>
                          <div className="font-mono text-slate-800">{a.name}</div>
                          <div className="text-xs text-slate-500">{a.description}</div>
                        </div>
                        <span className="inline-flex rounded border border-line bg-mist px-2 py-0.5 text-xs text-slate-600">{a.status}</span>
                      </li>
                    ))}
                  </ul>
                </section>
                <section className="rounded-lg border border-line bg-panel shadow-surface">
                  <div className="border-b border-line px-4 py-3"><h2 className="text-sm font-semibold text-ink">IDE assets</h2></div>
                  {bp.ide_assets.length === 0 ? (
                    <p className="p-4 text-sm text-slate-500">Not applicable for this runtime.</p>
                  ) : (
                    <ul className="divide-y divide-line text-sm">
                      {bp.ide_assets.map((a) => (
                        <li key={a.name} className="flex items-start justify-between gap-3 px-4 py-2">
                          <div>
                            <div className="font-mono text-slate-800">{a.name}</div>
                            <div className="text-xs text-slate-500">{a.description}</div>
                          </div>
                          <span className="inline-flex rounded border border-line bg-mist px-2 py-0.5 text-xs text-slate-600">{a.status}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </div>

              <section className="rounded-lg border border-line bg-panel shadow-surface">
                <div className="border-b border-line px-4 py-3"><h2 className="text-sm font-semibold text-ink">Environment files</h2><p className="mt-1 text-xs text-slate-500">Variable names only — values are never read or stored.</p></div>
                <ul className="divide-y divide-line text-sm">
                  {bp.environment_files.map((f) => (
                    <li key={f.name} className="px-4 py-2">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-mono text-slate-800">{f.name}</span>
                        <span className="inline-flex rounded border border-line bg-mist px-2 py-0.5 text-xs text-slate-600">{f.action}</span>
                      </div>
                      <div className="mt-1 text-xs text-slate-500">{f.purpose}</div>
                      {f.variable_names?.length ? <div className="mt-1"><Chips items={f.variable_names} /></div> : null}
                    </li>
                  ))}
                </ul>
              </section>

              <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
                <h2 className="text-sm font-semibold text-ink">Resource estimates</h2>
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3 xl:grid-cols-6">
                  <div><dt className="text-xs text-slate-500">CPU</dt><dd className="font-semibold text-ink">{resources.cpu ?? "—"}</dd></div>
                  <div><dt className="text-xs text-slate-500">RAM</dt><dd className="font-semibold text-ink">{resources.ram_mb ?? "—"} MB</dd></div>
                  <div><dt className="text-xs text-slate-500">Disk</dt><dd className="font-semibold text-ink">{resources.disk_mb ?? "—"} MB</dd></div>
                  <div><dt className="text-xs text-slate-500">Network</dt><dd className="font-semibold text-ink">{resources.network_access ? "yes" : "no"}</dd></div>
                  <div className="sm:col-span-2"><dt className="text-xs text-slate-500">Services</dt><dd className="mt-1"><Chips items={resources.services ?? []} /></dd></div>
                </dl>
                <div className="mt-3"><dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Volumes</dt><dd className="mt-1"><Chips items={resources.volumes ?? []} /></dd></div>
              </section>

              <div className="grid gap-6 xl:grid-cols-2">
                <section className="rounded-lg border border-line bg-panel shadow-surface">
                  <div className="border-b border-line px-4 py-3"><h2 className="text-sm font-semibold text-ink">Warnings</h2></div>
                  <div className="p-4">
                    {bp.warnings.length === 0 ? <p className="text-sm text-emerald-700">None.</p> : (
                      <ul className="list-disc space-y-1 pl-5 text-sm text-amber-800">{bp.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
                    )}
                  </div>
                </section>
                <section className="rounded-lg border border-line bg-panel shadow-surface">
                  <div className="border-b border-line px-4 py-3"><h2 className="text-sm font-semibold text-ink">Recommendations</h2></div>
                  <div className="p-4">
                    {bp.recommendations.length === 0 ? <p className="text-sm text-slate-500">None.</p> : (
                      <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">{bp.recommendations.map((r, i) => <li key={i}>{r}</li>)}</ul>
                    )}
                  </div>
                </section>
              </div>

              <p className="text-xs text-slate-400">Last generated {formatDateTime(bp.updated_at)}.</p>
            </>
          )}
        </div>
      ) : null}
    </AppShell>
  );
}
