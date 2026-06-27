"use client";

import { useCallback, useState } from "react";
import {
  AlertTriangle,
  Brain,
  GitBranch,
  ListChecks,
  Map,
  Rocket,
  Send,
  Server,
  Target
} from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/badges";
import { ErrorState } from "@/components/data-state";
import { ActionButton, SectionCard } from "@/components/ui";
import {
  askBrain,
  getHealth,
  getProductBrainOverview,
  getWorkspaceMetrics
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApiResource } from "@/hooks/use-api-resource";
import type { BrainRun } from "@/types/api";

function confidenceTone(score: number) {
  if (score >= 0.7) return "success" as const;
  if (score >= 0.4) return "warning" as const;
  return "neutral" as const;
}

async function loadIntel() {
  const [overview, health, workspaces] = await Promise.allSettled([
    getProductBrainOverview(),
    getHealth(),
    getWorkspaceMetrics()
  ]);
  return {
    overview: overview.status === "fulfilled" ? overview.value : null,
    health: health.status === "fulfilled" ? health.value : null,
    workspaces: workspaces.status === "fulfilled" ? workspaces.value : null
  };
}

const SUGGESTIONS = [
  "What should we work on next?",
  "Why did anything fail recently?",
  "Are any sandboxes unhealthy?",
  "What are the current blockers?"
];

export default function BrainPage() {
  const loader = useCallback(() => loadIntel(), []);
  const { data: intel } = useApiResource(loader);

  const [question, setQuestion] = useState("");
  const [run, setRun] = useState<BrainRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = useCallback(
    async (q: string) => {
      const text = q.trim();
      if (!text) return;
      setError(null);
      setBusy(true);
      try {
        setRun(await askBrain(text));
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Brain request failed");
      } finally {
        setBusy(false);
      }
    },
    []
  );

  const overview = intel?.overview ?? null;
  const phase = overview && overview.roadmap.length ? overview.roadmap[overview.roadmap.length - 1] : null;
  const ws = intel?.workspaces ?? null;
  const wsRunning = ws?.by_status?.running ?? 0;
  const wsUnhealthy = (ws?.by_status?.crashed ?? 0) + (ws?.by_status?.failed ?? 0);
  const healthOk = intel?.health?.status === "ok" || intel?.health?.status === "healthy";

  return (
    <AppShell title="CodeDNA Brain" description="Internal, read-only reasoning across every CodeDNA signal">
      <div className="space-y-6">
        {/* Ask */}
        <section className="rounded-xl border border-line bg-panel p-5 shadow-surface">
          <div className="flex items-center gap-2">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-soft text-brand ring-1 ring-brand/10">
              <Brain className="h-4 w-4" aria-hidden="true" />
            </span>
            <div>
              <div className="text-sm font-semibold text-ink">Ask CodeDNA Brain</div>
              <div className="text-xs text-slate-500">Evidence-based, read-only. It reasons and recommends — it never executes actions.</div>
            </div>
          </div>
          <div className="mt-4 flex flex-col gap-2 sm:flex-row">
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") ask(question);
              }}
              placeholder="e.g. What should we prioritize next?"
              className="focus-ring flex-1 rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-ink placeholder:text-slate-400"
            />
            <ActionButton icon={Send} loading={busy} onClick={() => ask(question)}>
              Ask
            </ActionButton>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => {
                  setQuestion(s);
                  ask(s);
                }}
                className="focus-ring rounded-full border border-line bg-mist px-3 py-1 text-xs text-slate-600 hover:bg-brand-soft hover:text-brand-ink"
              >
                {s}
              </button>
            ))}
          </div>
          {error ? <div className="mt-3"><ErrorState message={error} /></div> : null}
        </section>

        {/* Answer */}
        {run ? (
          <SectionCard
            title="Answer"
            icon={Brain}
            actions={
              <div className="flex items-center gap-2">
                {run.primary_brain ? <Badge tone="brand">{run.primary_brain}</Badge> : null}
                <Badge tone={confidenceTone(run.confidence_score)}>
                  confidence {(run.confidence_score * 100).toFixed(0)}%
                </Badge>
              </div>
            }
          >
            <p className="whitespace-pre-wrap text-sm text-slate-800">{run.answer}</p>
            {run.brains_consulted.length ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {run.brains_consulted.map((b) => (
                  <span key={b} className="rounded-full border border-line bg-mist px-2 py-0.5 text-xs text-slate-600">{b}</span>
                ))}
              </div>
            ) : null}
          </SectionCard>
        ) : null}

        {run && run.suggested_actions.length ? (
          <SectionCard title="Suggested next actions" icon={Target}>
            <ol className="space-y-3">
              {run.suggested_actions.map((a, i) => (
                <li key={i} className="flex items-start gap-3">
                  <span className="mt-0.5 flex h-6 w-6 flex-none items-center justify-center rounded-full bg-brand text-xs font-semibold text-white">{i + 1}</span>
                  <div>
                    <div className="text-sm font-medium text-ink">{a.title}</div>
                    <div className="text-xs text-slate-500">{a.rationale} · <span className="italic">{a.brain}</span></div>
                  </div>
                </li>
              ))}
            </ol>
          </SectionCard>
        ) : null}

        {run && run.evidence.length ? (
          <SectionCard title="Evidence" bodyClassName="p-0">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-line text-sm">
                <thead className="bg-mist text-left text-xs font-semibold uppercase tracking-[0.06em] text-slate-500">
                  <tr>
                    <th className="px-4 py-2">Source</th>
                    <th className="px-4 py-2">Detail</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {run.evidence.map((e, i) => (
                    <tr key={i}>
                      <td className="px-4 py-2 align-top"><span className="rounded border border-line bg-mist px-2 py-0.5 text-xs text-slate-600">{e.source}</span></td>
                      <td className="px-4 py-2 text-slate-700">{e.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        ) : null}

        {run && run.steps.length ? (
          <SectionCard title="Brain run timeline">
            <ol className="space-y-3">
              {run.steps.map((s) => (
                <li key={s.id} className="flex items-start gap-3 text-sm">
                  <span className="mt-1 h-1.5 w-1.5 flex-none rounded-full bg-brand" aria-hidden="true" />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-ink">{s.brain}</span>
                      <Badge tone={confidenceTone(s.confidence)}>{(s.confidence * 100).toFixed(0)}%</Badge>
                    </div>
                    <div className="text-slate-600">{s.summary}</div>
                  </div>
                </li>
              ))}
            </ol>
            <p className="mt-3 text-xs text-slate-400">Run {run.id} · {formatDateTime(run.created_at)}</p>
          </SectionCard>
        ) : null}

        {/* Intelligence cards */}
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <SectionCard title="Current phase" icon={Map}>
            {phase ? (
              <div>
                <div className="font-mono text-xs text-slate-500">Phase {phase.id}</div>
                <div className="text-sm font-medium text-ink">{phase.title}</div>
                {phase.summary ? <div className="mt-1 text-xs text-slate-500">{phase.summary}</div> : null}
              </div>
            ) : (
              <p className="text-sm text-slate-500">No roadmap detected.</p>
            )}
          </SectionCard>

          <SectionCard title="System health" icon={Server}>
            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${healthOk ? "bg-emerald-500" : intel?.health ? "bg-amber-500" : "bg-slate-300"}`} />
              <span className="text-sm font-semibold capitalize text-ink">{intel?.health?.status ?? "unknown"}</span>
            </div>
            {intel?.health ? (
              <div className="mt-2 text-xs text-slate-500">
                DB {intel.health.database_status} · Redis {intel.health.redis_status} · Celery {intel.health.celery_queue_reachable ? "ok" : "error"}
              </div>
            ) : null}
          </SectionCard>

          <SectionCard title="Active blockers" icon={AlertTriangle}>
            {overview && overview.blockers.length ? (
              <ul className="space-y-1.5 text-sm">
                {overview.blockers.slice(0, 4).map((b, i) => (
                  <li key={i} className="flex items-start justify-between gap-2">
                    <span className="text-slate-700">{b.title}</span>
                    <Badge tone={b.severity === "critical" || b.severity === "high" ? "danger" : "warning"}>{b.severity}</Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-emerald-700">No blockers detected.</p>
            )}
          </SectionCard>

          <SectionCard title="Repository intelligence" icon={GitBranch}>
            {overview ? (
              <dl className="grid grid-cols-3 gap-2 text-sm">
                <div><dt className="text-xs text-slate-500">Repos</dt><dd className="font-semibold text-ink">{overview.delivery.repositories}</dd></div>
                <div><dt className="text-xs text-slate-500">Scans</dt><dd className="font-semibold text-ink">{overview.delivery.scans_total}</dd></div>
                <div><dt className="text-xs text-slate-500">High risk</dt><dd className="font-semibold text-ink">{overview.delivery.high_risk_scans}</dd></div>
              </dl>
            ) : (
              <p className="text-sm text-slate-500">Unavailable.</p>
            )}
          </SectionCard>

          <SectionCard title="Workspace intelligence" icon={Rocket}>
            {ws ? (
              <dl className="grid grid-cols-3 gap-2 text-sm">
                <div><dt className="text-xs text-slate-500">Total</dt><dd className="font-semibold text-ink">{ws.total}</dd></div>
                <div><dt className="text-xs text-slate-500">Running</dt><dd className="font-semibold text-ink">{wsRunning}</dd></div>
                <div><dt className="text-xs text-slate-500">Unhealthy</dt><dd className="font-semibold text-ink">{wsUnhealthy}</dd></div>
              </dl>
            ) : (
              <p className="text-sm text-slate-500">Unavailable.</p>
            )}
          </SectionCard>

          <SectionCard title="Engineering" icon={ListChecks}>
            {overview ? (
              <div className="text-sm text-slate-700">{overview.delivery.engineering_requests_total} engineering request(s) tracked.</div>
            ) : (
              <p className="text-sm text-slate-500">Unavailable.</p>
            )}
          </SectionCard>
        </section>
      </div>
    </AppShell>
  );
}
