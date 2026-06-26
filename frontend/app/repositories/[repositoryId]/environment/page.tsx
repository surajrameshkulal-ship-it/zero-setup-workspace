"use client";

import Link from "next/link";
import { use, useCallback, useState } from "react";
import { ArrowLeft, Boxes, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/data-state";
import { generateEnvironmentSpec, getEnvironmentSpec, getRepository } from "@/lib/api";
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

function List({ items, empty }: { items: string[]; empty: string }) {
  if (!items || items.length === 0) {
    return <p className="text-sm text-slate-500">{empty}</p>;
  }
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
}

export default function EnvironmentSpecPage({
  params
}: {
  params: Promise<{ repositoryId: string }>;
}) {
  const { repositoryId } = use(params);
  const loader = useCallback(async () => {
    const [repository, spec] = await Promise.all([getRepository(repositoryId), getEnvironmentSpec(repositoryId)]);
    return { repository, spec };
  }, [repositoryId]);
  const { data, error, isLoading, reload } = useApiResource(loader);

  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function generate() {
    setActionError(null);
    setBusy(true);
    try {
      await generateEnvironmentSpec(repositoryId);
      await reload();
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Could not generate environment spec");
    } finally {
      setBusy(false);
    }
  }

  const spec = data?.spec ?? null;
  const wr = spec?.workspace_requirements ?? {};

  return (
    <AppShell
      title={data ? `${data.repository.full_name} · Environment` : "Environment spec"}
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
      {isLoading ? <LoadingState label="Loading environment spec" /> : null}
      {error ? <ErrorState message={error} onRetry={() => reload().catch(() => undefined)} /> : null}
      {data ? (
        <div className="space-y-6">
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-panel p-4 shadow-surface">
            <div className="flex items-center gap-2">
              <Boxes className="h-4 w-4 text-brand" aria-hidden="true" />
              <div>
                <div className="text-sm font-semibold text-ink">Environment specification</div>
                <div className="text-xs text-slate-500">
                  A normalized blueprint derived from the setup intent. Nothing is launched, executed, or installed.
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={generate}
              disabled={busy}
              className="focus-ring inline-flex items-center gap-2 rounded bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-[#125870] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              {busy ? "Generating" : spec ? "Regenerate" : "Generate spec"}
            </button>
          </section>

          {actionError ? <ErrorState message={actionError} /> : null}

          {!spec ? (
            <EmptyState
              icon={Boxes}
              title="No environment spec yet"
              description="Generate a normalized environment spec from the repository's setup intent (analyze the setup first if you haven't)."
            />
          ) : (
            <>
              <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-sm font-semibold text-ink">Runtime &amp; strategy</h2>
                  <div className="flex items-center gap-2">
                    <span className="inline-flex rounded border border-line bg-mist px-2 py-0.5 text-xs font-medium text-slate-700">
                      {spec.container_strategy}
                    </span>
                    <span className="inline-flex rounded border border-line bg-mist px-2 py-0.5 text-xs font-medium text-slate-700">
                      confidence {Math.round((spec.confidence_score ?? 0) * 100)}%
                    </span>
                  </div>
                </div>
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-5">
                  <Field label="Language" value={spec.primary_language} />
                  <Field label="Runtime" value={spec.runtime_name} />
                  <Field label="Version" value={spec.runtime_version} />
                  <Field label="Package manager" value={spec.package_manager} />
                  <Field label="Framework" value={spec.framework} />
                </dl>
              </section>

              <section className="rounded-lg border border-line bg-panel shadow-surface">
                <div className="border-b border-line px-4 py-3">
                  <h2 className="text-sm font-semibold text-ink">Commands</h2>
                </div>
                <dl className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3">
                  <Field label="Install" value={spec.install_command} />
                  <Field label="Develop" value={spec.dev_command} />
                  <Field label="Production" value={spec.prod_command} />
                  <Field label="Build" value={spec.build_command} />
                  <Field label="Test" value={spec.test_command} />
                  <Field label="Lint" value={spec.lint_command} />
                  <Field label="Health check" value={spec.health_check_command} />
                </dl>
              </section>

              <div className="grid gap-6 xl:grid-cols-2">
                <section className="rounded-lg border border-line bg-panel shadow-surface">
                  <div className="border-b border-line px-4 py-3">
                    <h2 className="text-sm font-semibold text-ink">Services</h2>
                  </div>
                  <dl className="space-y-3 p-4 text-sm">
                    <div>
                      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Databases</dt>
                      <dd className="mt-1"><Chips items={spec.databases} /></dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Caches</dt>
                      <dd className="mt-1"><Chips items={spec.caches} /></dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Queues</dt>
                      <dd className="mt-1"><Chips items={spec.queues} /></dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">External services</dt>
                      <dd className="mt-1"><Chips items={spec.external_services} /></dd>
                    </div>
                  </dl>
                </section>

                <section className="rounded-lg border border-line bg-panel shadow-surface">
                  <div className="border-b border-line px-4 py-3">
                    <h2 className="text-sm font-semibold text-ink">Ports &amp; resources</h2>
                  </div>
                  <dl className="space-y-3 p-4 text-sm">
                    <div>
                      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">App ports</dt>
                      <dd className="mt-1"><Chips items={spec.app_ports} /></dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Service ports</dt>
                      <dd className="mt-1"><Chips items={spec.service_ports} /></dd>
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                      <div><dt className="text-xs text-slate-500">CPU</dt><dd className="font-semibold text-ink">{wr.cpu ?? "—"}</dd></div>
                      <div><dt className="text-xs text-slate-500">Memory</dt><dd className="font-semibold text-ink">{wr.memory_mb ?? "—"} MB</dd></div>
                      <div><dt className="text-xs text-slate-500">Disk</dt><dd className="font-semibold text-ink">{wr.disk_mb ?? "—"} MB</dd></div>
                    </div>
                    <div>
                      <dt className="text-xs uppercase tracking-[0.08em] text-slate-500">Persistent volumes</dt>
                      <dd className="mt-1"><Chips items={wr.persistent_volumes ?? []} /></dd>
                    </div>
                    <div className="text-xs text-slate-500">
                      Network access required: <strong>{wr.network_access ? "yes" : "no"}</strong>
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
                  {spec.env_vars.length === 0 ? (
                    <p className="text-sm text-slate-500">None detected.</p>
                  ) : (
                    <ul className="flex flex-wrap gap-2 text-xs">
                      {spec.env_vars.map((env) => (
                        <li
                          key={env.name}
                          className="inline-flex items-center gap-1 rounded border border-line bg-mist px-2 py-0.5 font-mono text-slate-700"
                        >
                          {env.name}
                          <span className={env.required ? "text-rose-600" : "text-slate-400"}>
                            {env.required ? "required" : "optional"}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {spec.missing_env_example ? (
                    <p className="mt-2 text-xs text-amber-700">No .env.example found — the variable list may be incomplete.</p>
                  ) : null}
                </div>
              </section>

              {spec.warnings.length || spec.assumptions.length || spec.missing_information.length ? (
                <div className="grid gap-6 xl:grid-cols-3">
                  <section className="rounded-lg border border-line bg-panel shadow-surface">
                    <div className="border-b border-line px-4 py-3"><h2 className="text-sm font-semibold text-ink">Warnings</h2></div>
                    <div className="p-4"><List items={spec.warnings} empty="None." /></div>
                  </section>
                  <section className="rounded-lg border border-line bg-panel shadow-surface">
                    <div className="border-b border-line px-4 py-3"><h2 className="text-sm font-semibold text-ink">Assumptions</h2></div>
                    <div className="p-4"><List items={spec.assumptions} empty="None." /></div>
                  </section>
                  <section className="rounded-lg border border-line bg-panel shadow-surface">
                    <div className="border-b border-line px-4 py-3"><h2 className="text-sm font-semibold text-ink">Missing information</h2></div>
                    <div className="p-4"><List items={spec.missing_information} empty="None." /></div>
                  </section>
                </div>
              ) : null}

              {spec.evidence && spec.evidence.length ? (
                <section className="rounded-lg border border-line bg-panel shadow-surface">
                  <div className="border-b border-line px-4 py-3">
                    <h2 className="text-sm font-semibold text-ink">Inference evidence</h2>
                    <p className="mt-1 text-xs text-slate-500">Why each value was inferred, and from which source.</p>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-line text-sm">
                      <thead className="bg-mist text-left text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
                        <tr>
                          <th className="px-4 py-2">Field</th>
                          <th className="px-4 py-2">Value</th>
                          <th className="px-4 py-2">Source</th>
                          <th className="px-4 py-2">Why</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-line">
                        {spec.evidence.map((e, i) => (
                          <tr key={i} className="align-top">
                            <td className="px-4 py-2 font-mono text-xs text-slate-700">{e.field}</td>
                            <td className="px-4 py-2 font-mono text-xs text-slate-800">{String(Array.isArray(e.value) ? e.value.join(", ") : e.value)}</td>
                            <td className="px-4 py-2 text-xs text-slate-600">{e.source}</td>
                            <td className="px-4 py-2 text-xs text-slate-500">{e.detail}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              ) : null}

              <p className="text-xs text-slate-400">Last generated {formatDateTime(spec.updated_at)}.</p>
            </>
          )}
        </div>
      ) : null}
    </AppShell>
  );
}
