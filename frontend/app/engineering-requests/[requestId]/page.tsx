"use client";

import Link from "next/link";
import { use, useCallback, useState } from "react";
import { ArrowLeft, Ban, CheckCircle2, Play, ShieldAlert, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { PriorityBadge, RequestStatusBadge, RiskBadge } from "@/components/badges";
import { EmptyState, ErrorState, LoadingState } from "@/components/data-state";
import {
  analyzeEngineeringRequest,
  approveEngineeringRequestPlan,
  getEngineeringRequest,
  rejectEngineeringRequestPlan
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApiResource } from "@/hooks/use-api-resource";

const ANALYZABLE = new Set(["submitted", "plan_ready", "rejected", "failed"]);

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-line bg-panel shadow-surface">
      <div className="border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function BulletList({ items, empty }: { items: string[]; empty: string }) {
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

export default function EngineeringRequestDetailPage({
  params
}: {
  params: Promise<{ requestId: string }>;
}) {
  const { requestId } = use(params);
  const loader = useCallback(() => getEngineeringRequest(requestId), [requestId]);
  const { data: request, error, isLoading, reload } = useApiResource(loader);

  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reason, setReason] = useState("");

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

  const canAnalyze = request ? ANALYZABLE.has(request.status) : false;
  const isPlanReady = request?.status === "plan_ready";
  const safety = request?.safety_notes ?? {};

  return (
    <AppShell
      title={request ? request.title : "Engineering request"}
      actions={
        <Link
          className="focus-ring inline-flex h-9 w-9 items-center justify-center rounded border border-line bg-panel text-slate-700 hover:bg-mist"
          href="/engineering-requests"
          title="Engineering requests"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </Link>
      }
    >
      {isLoading ? <LoadingState label="Loading request" /> : null}
      {error ? <ErrorState message={error} onRetry={() => reload().catch(() => undefined)} /> : null}
      {request ? (
        <div className="space-y-6">
          <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
            <div className="flex flex-wrap items-center gap-2">
              <RequestStatusBadge status={request.status} />
              <PriorityBadge priority={request.priority} />
              <RiskBadge level={request.risk_level} />
              <span className="text-xs text-slate-500">{request.request_type}</span>
            </div>
            <h2 className="mt-3 text-lg font-semibold text-ink">{request.title}</h2>
            {request.repository_full_name ? (
              <p className="mt-1 text-sm text-slate-500">{request.repository_full_name}</p>
            ) : null}
            <p className="mt-3 whitespace-pre-wrap text-sm text-slate-700">{request.description}</p>
            <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
              <div>
                <dt className="text-slate-500">Created</dt>
                <dd className="text-slate-800">{formatDateTime(request.created_at)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Updated</dt>
                <dd className="text-slate-800">{formatDateTime(request.updated_at)}</dd>
              </div>
            </dl>
          </section>

          {/* Actions */}
          <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={!canAnalyze || busy !== null}
                onClick={() => run("analyze", () => analyzeEngineeringRequest(request.id))}
                className="focus-ring inline-flex items-center gap-2 rounded bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-[#125870] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                {busy === "analyze" ? "Analyzing" : request.status === "submitted" ? "Run analysis" : "Re-run analysis"}
              </button>
              <button
                type="button"
                disabled={!isPlanReady || busy !== null}
                onClick={() => run("approve", () => approveEngineeringRequestPlan(request.id))}
                className="focus-ring inline-flex items-center gap-2 rounded border border-emerald-300 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-800 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                {busy === "approve" ? "Approving" : "Approve plan"}
              </button>
              <button
                type="button"
                disabled={!isPlanReady || busy !== null}
                onClick={() => run("reject", () => rejectEngineeringRequestPlan(request.id, reason || undefined))}
                className="focus-ring inline-flex items-center gap-2 rounded border border-rose-300 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-800 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Ban className="h-4 w-4" aria-hidden="true" />
                {busy === "reject" ? "Rejecting" : "Reject plan"}
              </button>
            </div>
            {isPlanReady ? (
              <textarea
                className="focus-ring mt-3 w-full rounded border border-line bg-white px-3 py-2 text-sm"
                placeholder="Optional reason for rejection"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            ) : null}
            {actionError ? (
              <div className="mt-3 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">{actionError}</div>
            ) : null}
            <p className="mt-3 text-xs text-slate-500">
              Approval marks the plan as accepted for a future human-driven pull request. The AI never merges, pushes, or deploys.
            </p>
          </section>

          {/* Plan */}
          <Section title="AI summary">
            {request.ai_summary ? (
              <p className="whitespace-pre-wrap text-sm text-slate-700">{request.ai_summary}</p>
            ) : (
              <EmptyState title="Not analyzed yet" description="Run analysis to generate a plan." />
            )}
          </Section>

          <div className="grid gap-6 xl:grid-cols-2">
            <Section title="Implementation plan">
              <BulletList items={request.implementation_plan} empty="No plan yet." />
            </Section>
            <Section title="Test plan">
              <BulletList items={request.test_plan} empty="No test plan yet." />
            </Section>
          </div>

          <Section title="Affected files">
            {request.affected_files.length === 0 ? (
              <p className="text-sm text-slate-500">No files identified yet.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {request.affected_files.map((file, index) => (
                  <li key={index} className="rounded border border-line bg-mist px-3 py-2">
                    <div className="font-mono text-slate-800">{file.path}</div>
                    {file.reason ? <div className="mt-1 text-slate-500">{file.reason}</div> : null}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          {/* Safety */}
          <section className="rounded-lg border border-line bg-panel shadow-surface">
            <div className="flex items-center gap-2 border-b border-line px-4 py-3">
              <ShieldAlert className="h-4 w-4 text-signal" aria-hidden="true" />
              <h2 className="text-sm font-semibold text-ink">Safety guardrails</h2>
            </div>
            <div className="grid gap-4 p-4 md:grid-cols-2">
              <div>
                <div className="mb-2 flex items-center gap-2 text-sm font-medium text-emerald-700">
                  <ShieldCheck className="h-4 w-4" aria-hidden="true" />
                  AI is allowed to
                </div>
                <BulletList items={safety.allowed ?? []} empty="Not specified." />
              </div>
              <div>
                <div className="mb-2 flex items-center gap-2 text-sm font-medium text-rose-700">
                  <Ban className="h-4 w-4" aria-hidden="true" />
                  AI is never allowed to
                </div>
                <BulletList items={safety.forbidden ?? []} empty="Not specified." />
              </div>
            </div>
            {safety.notes && safety.notes.length > 0 ? (
              <div className="border-t border-line px-4 py-3">
                <div className="mb-1 text-sm font-medium text-ink">Notes</div>
                <BulletList items={safety.notes} empty="" />
              </div>
            ) : null}
            {safety.rejection_reason ? (
              <div className="border-t border-line px-4 py-3 text-sm text-rose-800">
                <span className="font-medium">Rejection reason:</span> {safety.rejection_reason}
              </div>
            ) : null}
            <div className="border-t border-line px-4 py-3 text-xs text-slate-500">
              Human approval required: <strong>{safety.human_approval_required === false ? "no" : "yes"}</strong>
            </div>
          </section>
        </div>
      ) : null}
    </AppShell>
  );
}
