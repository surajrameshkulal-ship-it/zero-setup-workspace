"use client";

import { useCallback } from "react";
import { AlertTriangle, Brain, GitBranch, ListChecks, Map, RefreshCw, Server, Target } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/badges";
import { CardsSkeleton, EmptyState, ErrorState } from "@/components/data-state";
import { StatCard } from "@/components/metric-card";
import { ActionButton, SectionCard } from "@/components/ui";
import { getProductBrainOverview } from "@/lib/api";
import { useApiResource } from "@/hooks/use-api-resource";

function severityTone(severity: string) {
  if (severity === "critical" || severity === "high") return "danger" as const;
  if (severity === "medium") return "warning" as const;
  return "neutral" as const;
}

export default function ProductBrainPage() {
  const loader = useCallback(() => getProductBrainOverview(), []);
  const { data, error, isLoading, reload } = useApiResource(loader);

  return (
    <AppShell
      title="Product Brain"
      description="Roadmap, delivery state, blockers, and recommended priorities"
      actions={
        <ActionButton variant="secondary" size="sm" icon={RefreshCw} onClick={() => reload().catch(() => undefined)}>
          Refresh
        </ActionButton>
      }
    >
      {isLoading ? <CardsSkeleton count={4} /> : null}
      {error ? <ErrorState message={error} onRetry={() => reload().catch(() => undefined)} /> : null}
      {data ? (
        <div className="space-y-6">
          <section className="rounded-xl border border-line bg-panel p-5 shadow-surface">
            <div className="flex items-start gap-3">
              <span className="flex h-9 w-9 flex-none items-center justify-center rounded-xl bg-brand-soft text-brand ring-1 ring-brand/10">
                <Brain className="h-4 w-4" aria-hidden="true" />
              </span>
              <p className="text-sm text-slate-700">{data.summary}</p>
            </div>
          </section>

          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard icon={GitBranch} label="Repositories" value={data.delivery.repositories} />
            <StatCard icon={ListChecks} label="Engineering requests" value={data.delivery.engineering_requests_total} />
            <StatCard icon={AlertTriangle} label="Blockers" value={data.blockers.length} />
            <StatCard icon={Server} label="High-risk scans" value={data.delivery.high_risk_scans} />
          </section>

          <div className="grid gap-6 xl:grid-cols-2">
            <SectionCard title="Recommended priorities" icon={Target}>
              {data.priorities.length === 0 ? (
                <p className="text-sm text-slate-500">Nothing queued.</p>
              ) : (
                <ol className="space-y-3">
                  {data.priorities.map((p, i) => (
                    <li key={i} className="flex items-start gap-3">
                      <span className="mt-0.5 flex h-6 w-6 flex-none items-center justify-center rounded-full bg-brand text-xs font-semibold text-white">
                        {i + 1}
                      </span>
                      <div>
                        <div className="text-sm font-medium text-ink">{p.title}</div>
                        <div className="text-xs text-slate-500">{p.rationale}</div>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </SectionCard>

            <SectionCard title="Blockers" icon={AlertTriangle}>
              {data.blockers.length === 0 ? (
                <p className="text-sm text-emerald-700">No blockers detected.</p>
              ) : (
                <ul className="space-y-3">
                  {data.blockers.map((b, i) => (
                    <li key={i} className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-ink">{b.title}</div>
                        <div className="text-xs text-slate-500">{b.reason}</div>
                        <div className="mt-0.5 text-[11px] uppercase tracking-[0.08em] text-slate-400">{b.type}</div>
                      </div>
                      <Badge tone={severityTone(b.severity)}>{b.severity}</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </SectionCard>
          </div>

          <SectionCard title="Roadmap" icon={Map} bodyClassName="p-0">
            {data.roadmap.length === 0 ? (
              <div className="p-5">
                <EmptyState icon={Map} title="No roadmap found" description="No roadmap document was detected in docs/." />
              </div>
            ) : (
              <ul className="divide-y divide-line">
                {data.roadmap.map((phase) => (
                  <li key={phase.id} className="flex items-start gap-3 px-5 py-3">
                    <span className="mt-0.5 inline-flex rounded-md border border-line bg-mist px-2 py-0.5 font-mono text-xs text-slate-600">
                      {phase.id}
                    </span>
                    <div>
                      <div className="text-sm font-medium text-ink">{phase.title}</div>
                      {phase.summary ? <div className="text-xs text-slate-500">{phase.summary}</div> : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>
        </div>
      ) : null}
    </AppShell>
  );
}
