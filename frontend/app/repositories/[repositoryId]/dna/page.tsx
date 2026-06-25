"use client";

import Link from "next/link";
import { use, useCallback, useState } from "react";
import { ArrowLeft, Dna, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/data-state";
import { generateRepositoryDna, getRepository, getRepositoryDna } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApiResource } from "@/hooks/use-api-resource";

function Chips({ items }: { items: string[] }) {
  if (!items || items.length === 0) {
    return <span className="text-sm text-slate-400">—</span>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <span key={item} className="inline-flex rounded border border-line bg-mist px-2 py-0.5 text-xs text-slate-700">
          {item}
        </span>
      ))}
    </div>
  );
}

function Field({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-[0.08em] text-slate-500">{label}</div>
      <div className="mt-1">
        <Chips items={items} />
      </div>
    </div>
  );
}

export default function RepositoryDnaPage({
  params
}: {
  params: Promise<{ repositoryId: string }>;
}) {
  const { repositoryId } = use(params);
  const loader = useCallback(async () => {
    const [repository, dna] = await Promise.all([getRepository(repositoryId), getRepositoryDna(repositoryId)]);
    return { repository, dna };
  }, [repositoryId]);
  const { data, error, isLoading, reload } = useApiResource(loader);

  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function generate() {
    setActionError(null);
    setBusy(true);
    try {
      await generateRepositoryDna(repositoryId);
      await reload();
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Could not generate DNA");
    } finally {
      setBusy(false);
    }
  }

  const dna = data?.dna ?? null;
  const health = dna?.repository_health ?? {};

  return (
    <AppShell
      title={data ? `${data.repository.full_name} · DNA` : "Repository DNA"}
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
      {isLoading ? <LoadingState label="Loading repository DNA" /> : null}
      {error ? <ErrorState message={error} onRetry={() => reload().catch(() => undefined)} /> : null}
      {data ? (
        <div className="space-y-6">
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-panel p-4 shadow-surface">
            <div className="flex items-center gap-2">
              <Dna className="h-4 w-4 text-brand" aria-hidden="true" />
              <div>
                <div className="text-sm font-semibold text-ink">Repository DNA</div>
                <div className="text-xs text-slate-500">
                  Read-only fingerprint inferred from scan history. No cloning or Git writes.
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
              {busy ? "Generating" : dna ? "Regenerate" : "Generate DNA"}
            </button>
          </section>

          {actionError ? <ErrorState message={actionError} /> : null}

          {!dna ? (
            <EmptyState
              icon={Dna}
              title="No DNA generated yet"
              description="Generate the repository DNA to see inferred languages, frameworks, tooling, health, and risk notes."
            />
          ) : (
            <>
              <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-xs uppercase tracking-[0.08em] text-slate-500">Repository health</div>
                    <div className="mt-1 text-2xl font-semibold text-ink">
                      {health.score ?? "—"}
                      {typeof health.score === "number" ? <span className="text-base text-slate-400"> / 100</span> : null}
                    </div>
                  </div>
                  <span className="inline-flex rounded border border-line bg-mist px-2 py-0.5 text-xs font-medium text-slate-700">
                    {health.status ?? "unknown"}
                  </span>
                </div>
                {health.notes && health.notes.length > 0 ? (
                  <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">
                    {health.notes.map((note, index) => (
                      <li key={index}>{note}</li>
                    ))}
                  </ul>
                ) : null}
                <p className="mt-3 text-xs text-slate-400">Last generated {formatDateTime(dna.updated_at)}</p>
              </section>

              <section className="grid gap-4 rounded-lg border border-line bg-panel p-4 shadow-surface sm:grid-cols-2 xl:grid-cols-3">
                <Field label="Languages" items={dna.languages} />
                <Field label="Frameworks" items={dna.frameworks} />
                <Field label="Package managers" items={dna.package_managers} />
                <Field label="Databases" items={dna.databases} />
                <Field label="Queues" items={dna.queues} />
                <Field label="Testing tools" items={dna.testing_tools} />
                <Field label="Build tools" items={dna.build_tools} />
                <Field label="CI / CD" items={dna.cicd} />
                <Field label="Security tools" items={dna.security_tools} />
                <Field label="Docker" items={dna.docker?.files ?? []} />
              </section>

              <div className="grid gap-6 xl:grid-cols-2">
                <section className="rounded-lg border border-line bg-panel shadow-surface">
                  <div className="border-b border-line px-4 py-3">
                    <h2 className="text-sm font-semibold text-ink">Architecture &amp; dependencies</h2>
                  </div>
                  <div className="space-y-3 p-4 text-sm text-slate-700">
                    <p>{dna.architecture_summary ?? "Not available."}</p>
                    <p className="text-slate-600">{dna.dependency_summary?.note}</p>
                    <Chips items={dna.dependency_summary?.manifests_detected ?? []} />
                  </div>
                </section>
                <section className="rounded-lg border border-line bg-panel shadow-surface">
                  <div className="border-b border-line px-4 py-3">
                    <h2 className="text-sm font-semibold text-ink">Risk notes</h2>
                  </div>
                  <div className="p-4">
                    {dna.risk_notes.length === 0 ? (
                      <p className="text-sm text-slate-500">None.</p>
                    ) : (
                      <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
                        {dna.risk_notes.map((note, index) => (
                          <li key={index}>{note}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </section>
              </div>

              <section className="rounded-lg border border-line bg-panel shadow-surface">
                <div className="border-b border-line px-4 py-3">
                  <h2 className="text-sm font-semibold text-ink">Important files</h2>
                </div>
                <div className="p-4">
                  {dna.important_files.length === 0 ? (
                    <p className="text-sm text-slate-500">None detected yet.</p>
                  ) : (
                    <ul className="space-y-1 font-mono text-sm text-slate-700">
                      {dna.important_files.map((path) => (
                        <li key={path}>{path}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </section>
            </>
          )}
        </div>
      ) : null}
    </AppShell>
  );
}
