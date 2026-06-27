"use client";

import { useCallback, useEffect, useState } from "react";
import { Bug, Repeat, Stethoscope } from "lucide-react";
import { Badge } from "@/components/badges";
import { ErrorState } from "@/components/data-state";
import { ActionButton, SectionCard } from "@/components/ui";
import { diagnoseFailure, getDebugPatterns } from "@/lib/api";
import type { DebugDiagnosis, DebugPattern } from "@/types/api";

function severityTone(severity: string) {
  if (severity === "critical" || severity === "high") return "danger" as const;
  if (severity === "medium") return "warning" as const;
  return "neutral" as const;
}

function confidenceTone(score: number) {
  if (score >= 0.7) return "success" as const;
  if (score >= 0.4) return "warning" as const;
  return "neutral" as const;
}

export function DebugIntelligencePanel() {
  const [logs, setLogs] = useState("");
  const [diagnosis, setDiagnosis] = useState<DebugDiagnosis | null>(null);
  const [patterns, setPatterns] = useState<DebugPattern[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadPatterns = useCallback(async () => {
    try {
      setPatterns(await getDebugPatterns());
    } catch {
      /* patterns are best-effort */
    }
  }, []);

  useEffect(() => {
    loadPatterns().catch(() => undefined);
  }, [loadPatterns]);

  const diagnose = useCallback(async () => {
    const text = logs.trim();
    if (!text) return;
    setError(null);
    setBusy("diagnose");
    try {
      setDiagnosis(await diagnoseFailure(text));
      await loadPatterns();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Diagnosis failed");
    } finally {
      setBusy(null);
    }
  }, [logs, loadPatterns]);

  return (
    <SectionCard title="Debug intelligence" icon={Stethoscope}>
      <p className="text-xs text-slate-500">
        Paste a failing test/build/runtime log. The Brain classifies it, finds the probable root cause and affected
        files via the Engineering Graph, and recommends a fix. Read-only — it never edits code or opens a PR.
      </p>

      <textarea
        value={logs}
        onChange={(e) => setLogs(e.target.value)}
        rows={6}
        placeholder="Paste logs, test output, or a traceback here…"
        className="focus-ring mt-3 w-full rounded-lg border border-line bg-white p-3 font-mono text-xs text-ink placeholder:text-slate-400"
      />
      <div className="mt-2 flex justify-end">
        <ActionButton icon={Bug} loading={busy === "diagnose"} onClick={diagnose}>
          Diagnose
        </ActionButton>
      </div>

      {error ? <div className="mt-3"><ErrorState message={error} /></div> : null}

      {diagnosis ? (
        <div className="mt-4 space-y-3 rounded-lg border border-line bg-panel p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Badge tone="info">{diagnosis.failure?.failure_type ?? "failure"}</Badge>
              <Badge tone={severityTone(diagnosis.severity)}>{diagnosis.severity}</Badge>
            </div>
            <Badge tone={confidenceTone(diagnosis.confidence_score)}>
              confidence {(diagnosis.confidence_score * 100).toFixed(0)}%
            </Badge>
          </div>

          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">Summary</div>
            <p className="mt-1 text-sm text-slate-800">{diagnosis.summary}</p>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">Probable cause</div>
            <p className="mt-1 text-sm text-slate-700">{diagnosis.probable_cause}</p>
          </div>
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
            <div className="text-xs font-semibold uppercase tracking-[0.08em] text-emerald-700">Recommended fix</div>
            <p className="mt-1 text-sm text-emerald-900">{diagnosis.recommended_fix}</p>
          </div>

          {diagnosis.affected_files.length ? (
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">Affected files</div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {diagnosis.affected_files.map((f) => (
                  <span key={f} className="rounded border border-line bg-mist px-2 py-0.5 font-mono text-xs text-slate-700">{f}</span>
                ))}
              </div>
            </div>
          ) : null}

          {diagnosis.related_graph_nodes.length ? (
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">Related components</div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {diagnosis.related_graph_nodes.map((n) => (
                  <span key={n.id} className="rounded-full border border-line bg-mist px-2 py-0.5 text-xs text-slate-600">
                    {n.node_type}: {n.title}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {diagnosis.evidence.length ? (
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">Evidence</div>
              <ul className="mt-1 space-y-1">
                {diagnosis.evidence.map((e, i) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <span className="rounded border border-line bg-mist px-1.5 py-0.5 text-xs text-slate-500">{e.source}</span>
                    <span className="text-slate-700">{e.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Recurring patterns */}
      <div className="mt-4">
        <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
          <Repeat className="h-3.5 w-3.5" aria-hidden="true" /> Recurring patterns
        </div>
        {patterns.length === 0 ? (
          <p className="text-sm text-slate-500">No failures recorded yet.</p>
        ) : (
          <ul className="space-y-1.5">
            {patterns.slice(0, 6).map((p) => (
              <li key={p.signature} className="flex items-center justify-between gap-2 text-sm">
                <span className="truncate text-slate-700">{p.example_title}</span>
                <span className="flex flex-none items-center gap-1">
                  <span className="rounded border border-line bg-mist px-2 py-0.5 text-xs text-slate-600">{p.failure_type}</span>
                  <Badge tone={p.count > 1 ? "warning" : "neutral"}>×{p.count}</Badge>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </SectionCard>
  );
}
