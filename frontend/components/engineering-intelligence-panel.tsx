"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Boxes, Search, Workflow } from "lucide-react";
import { Badge } from "@/components/badges";
import { ErrorState } from "@/components/data-state";
import { ActionButton, SectionCard } from "@/components/ui";
import { getEngineeringArchitecture, getEngineeringImpact, getEngineeringOverview } from "@/lib/api";
import type { ArchitectureReview, EngineeringOverview, ImpactResult } from "@/types/api";

function severityTone(severity: string) {
  if (severity === "critical" || severity === "high") return "danger" as const;
  if (severity === "medium") return "warning" as const;
  if (severity === "info") return "info" as const;
  return "neutral" as const;
}

export function EngineeringIntelligencePanel() {
  const [overview, setOverview] = useState<EngineeringOverview | null>(null);
  const [review, setReview] = useState<ArchitectureReview | null>(null);
  const [query, setQuery] = useState("");
  const [impact, setImpact] = useState<ImpactResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [ov, ar] = await Promise.all([getEngineeringOverview(), getEngineeringArchitecture()]);
      setOverview(ov);
      setReview(ar);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load engineering intelligence");
    }
  }, []);

  useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  const runImpact = useCallback(async (q: string) => {
    const text = q.trim();
    if (!text) return;
    setError(null);
    setBusy("impact");
    try {
      setImpact(await getEngineeringImpact(text));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Impact analysis failed");
    } finally {
      setBusy(null);
    }
  }, []);

  return (
    <SectionCard title="Engineering intelligence" icon={Workflow}>
      {error ? <div className="mb-3"><ErrorState message={error} /></div> : null}

      {overview ? (
        <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
          <div className="rounded-lg bg-mist px-3 py-2">
            <div className="text-xs text-slate-500">Components</div>
            <div className="text-lg font-semibold text-ink">{overview.total_components}</div>
          </div>
          {Object.entries(overview.node_counts).slice(0, 4).map(([k, v]) => (
            <div key={k} className="rounded-lg bg-mist px-3 py-2">
              <div className="text-xs capitalize text-slate-500">{k}</div>
              <div className="text-lg font-semibold text-ink">{v}</div>
            </div>
          ))}
          <div className="rounded-lg bg-mist px-3 py-2">
            <div className="text-xs text-slate-500">Orphans</div>
            <div className="text-lg font-semibold text-ink">{overview.orphans}</div>
          </div>
        </div>
      ) : null}

      {/* Impact analysis */}
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") runImpact(query);
            }}
            placeholder="Impact of a change (e.g. workspace launch, github)"
            className="focus-ring w-full rounded-lg border border-line bg-white py-2.5 pl-9 pr-3 text-sm text-ink placeholder:text-slate-400"
          />
        </div>
        <ActionButton icon={Boxes} loading={busy === "impact"} onClick={() => runImpact(query)}>
          Analyze impact
        </ActionButton>
      </div>

      {impact ? (
        <div className="mt-3 rounded-lg border border-line bg-panel p-3">
          <p className="text-sm text-slate-700">{impact.summary}</p>
          {impact.impacted.length ? (
            <ul className="mt-2 space-y-1">
              {impact.impacted.slice(0, 10).map((i) => (
                <li key={i.id} className="flex items-center justify-between gap-2 text-sm">
                  <span className="text-slate-700">{i.title}</span>
                  <span className="flex items-center gap-1">
                    <span className="rounded border border-line bg-mist px-2 py-0.5 text-xs text-slate-600">{i.node_type}</span>
                    <span className="text-xs text-slate-400">via {i.via}</span>
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">Top dependencies</div>
          {overview && overview.top_dependencies.length ? (
            <ul className="space-y-1.5">
              {overview.top_dependencies.map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-2 text-sm">
                  <span className="text-slate-700">{d.title}</span>
                  <Badge tone="info">{d.dependents} dependents</Badge>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">No dependencies recorded. Ingest the knowledge graph first.</p>
          )}
        </div>

        <div>
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> Architecture review
          </div>
          {review && review.flags.length ? (
            <ul className="space-y-2">
              {review.flags.map((f, i) => (
                <li key={i} className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-medium text-ink">{f.title}</div>
                    <div className="text-xs text-slate-500">{f.detail}</div>
                  </div>
                  <Badge tone={severityTone(f.severity)}>{f.severity}</Badge>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-emerald-700">No architecture concerns detected.</p>
          )}
        </div>
      </div>
    </SectionCard>
  );
}
