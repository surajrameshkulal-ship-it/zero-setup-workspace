"use client";

import Link from "next/link";
import { use, useCallback, useState } from "react";
import { ArrowLeft, RefreshCw, Wrench } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/data-state";
import { generateSetupIntent, getRepository, getSetupIntent } from "@/lib/api";
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

export default function SetupIntentPage({
  params
}: {
  params: Promise<{ repositoryId: string }>;
}) {
  const { repositoryId } = use(params);
  const loader = useCallback(async () => {
    const [repository, intent] = await Promise.all([getRepository(repositoryId), getSetupIntent(repositoryId)]);
    return { repository, intent };
  }, [repositoryId]);
  const { data, error, isLoading, reload } = useApiResource(loader);

  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function generate() {
    setActionError(null);
    setBusy(true);
    try {
      await generateSetupIntent(repositoryId);
      await reload();
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Could not analyze setup");
    } finally {
      setBusy(false);
    }
  }

  const intent = data?.intent ?? null;

  return (
    <AppShell
      title={data ? `${data.repository.full_name} · Setup Intent` : "Setup Intent"}
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
      {isLoading ? <LoadingState label="Loading setup intent" /> : null}
      {error ? <ErrorState message={error} onRetry={() => reload().catch(() => undefined)} /> : null}
      {data ? (
        <div className="space-y-6">
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-panel p-4 shadow-surface">
            <div className="flex items-center gap-2">
              <Wrench className="h-4 w-4 text-brand" aria-hidden="true" />
              <div>
                <div className="text-sm font-semibold text-ink">Setup Intent</div>
                <div className="text-xs text-slate-500">
                  Read-only inference of how to build and run this repository. Code is never executed.
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
              {busy ? "Analyzing" : intent ? "Regenerate" : "Analyze setup"}
            </button>
          </section>

          {actionError ? <ErrorState message={actionError} /> : null}

          {!intent ? (
            <EmptyState
              icon={Wrench}
              title="No setup intent yet"
              description="Analyze the repository's manifests to infer its runtime, commands, dependencies, infrastructure, services, and environment variables."
            />
          ) : (
            <>
              <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-sm font-semibold text-ink">Runtime</h2>
                  <span className="inline-flex rounded border border-line bg-mist px-2 py-0.5 text-xs font-medium text-slate-700">
                    confidence {Math.round((intent.confidence_score ?? 0) * 100)}%
                  </span>
                </div>
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
                  <div>
                    <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Languages</dt>
                    <dd className="mt-1"><Chips items={intent.languages} /></dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Frameworks</dt>
                    <dd className="mt-1"><Chips items={intent.frameworks} /></dd>
                  </div>
                  <Field label="Package manager" value={intent.package_manager} />
                  <Field label="Runtime version" value={intent.runtime_version} />
                </dl>
              </section>

              <section className="rounded-lg border border-line bg-panel shadow-surface">
                <div className="border-b border-line px-4 py-3">
                  <h2 className="text-sm font-semibold text-ink">Commands</h2>
                </div>
                <dl className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3">
                  <Field label="Install" value={intent.install_command} />
                  <Field label="Develop" value={intent.dev_command} />
                  <Field label="Production" value={intent.prod_command} />
                  <Field label="Test" value={intent.test_command} />
                  <Field label="Build" value={intent.build_command} />
                  <Field label="Lint" value={intent.lint_command} />
                </dl>
              </section>

              <div className="grid gap-6 xl:grid-cols-2">
                <section className="rounded-lg border border-line bg-panel shadow-surface">
                  <div className="border-b border-line px-4 py-3">
                    <h2 className="text-sm font-semibold text-ink">Infrastructure</h2>
                  </div>
                  <dl className="space-y-3 p-4 text-sm">
                    <div>
                      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Ports</dt>
                      <dd className="mt-1"><Chips items={intent.ports} /></dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Docker</dt>
                      <dd className="mt-1"><Chips items={intent.docker?.files ?? []} /></dd>
                    </div>
                    <Field label="CI / CD" value={intent.cicd_provider} />
                    <Field label="Health check" value={intent.health_check_endpoint} />
                  </dl>
                </section>

                <section className="rounded-lg border border-line bg-panel shadow-surface">
                  <div className="border-b border-line px-4 py-3">
                    <h2 className="text-sm font-semibold text-ink">Services &amp; dependencies</h2>
                  </div>
                  <dl className="space-y-3 p-4 text-sm">
                    <div>
                      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Databases</dt>
                      <dd className="mt-1"><Chips items={intent.databases} /></dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Caches</dt>
                      <dd className="mt-1"><Chips items={intent.caches} /></dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Queues</dt>
                      <dd className="mt-1"><Chips items={intent.queues} /></dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">External services</dt>
                      <dd className="mt-1"><Chips items={intent.external_services} /></dd>
                    </div>
                  </dl>
                </section>
              </div>

              <section className="rounded-lg border border-line bg-panel shadow-surface">
                <div className="border-b border-line px-4 py-3">
                  <h2 className="text-sm font-semibold text-ink">Environment variables</h2>
                  <p className="mt-1 text-xs text-slate-500">Names only — values are never read or stored.</p>
                </div>
                <div className="p-4">
                  {intent.env_vars.length === 0 ? (
                    <p className="text-sm text-slate-500">None detected.</p>
                  ) : (
                    <Chips items={intent.env_vars} />
                  )}
                </div>
              </section>

              <p className="text-xs text-slate-400">
                Sources analyzed: {intent.sources_analyzed.length} file(s). Last generated {formatDateTime(intent.updated_at)}.
              </p>
            </>
          )}
        </div>
      ) : null}
    </AppShell>
  );
}
