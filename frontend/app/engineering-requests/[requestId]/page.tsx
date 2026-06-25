"use client";

import Link from "next/link";
import { use, useCallback, useState } from "react";
import clsx from "clsx";
import {
  ArrowLeft,
  Ban,
  CheckCircle2,
  Cpu,
  FileCode2,
  Play,
  ShieldAlert,
  ShieldCheck
} from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { PriorityBadge, RequestStatusBadge, RiskBadge } from "@/components/badges";
import { EmptyState, ErrorState, LoadingState } from "@/components/data-state";
import {
  analyzeEngineeringRequest,
  approveEngineeringRequestPlan,
  generateCodePreview,
  generateExecutionPlan,
  getCodePreview,
  getEngineeringRequest,
  getExecutionPlan,
  rejectEngineeringRequestPlan
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useApiResource } from "@/hooks/use-api-resource";
import type { ExecutionSafetyStatus } from "@/types/api";

const ANALYZABLE = new Set(["submitted", "plan_ready", "rejected", "failed"]);

const SAFETY_STATUS_CLASS: Record<ExecutionSafetyStatus, string> = {
  safe: "border-emerald-300 bg-emerald-50 text-emerald-800",
  needs_approval: "border-amber-300 bg-amber-50 text-amber-800",
  blocked: "border-rose-300 bg-rose-50 text-rose-800"
};

function SafetyStatusBadge({ status }: { status: ExecutionSafetyStatus }) {
  return (
    <span className={clsx("inline-flex rounded border px-2 py-0.5 text-xs font-medium", SAFETY_STATUS_CLASS[status])}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

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

  const planLoader = useCallback(() => getExecutionPlan(requestId), [requestId]);
  const { data: executionPlan, reload: reloadPlan } = useApiResource(planLoader);

  const codeLoader = useCallback(() => getCodePreview(requestId), [requestId]);
  const { data: codePreview, reload: reloadCode } = useApiResource(codeLoader);

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
        await reloadPlan().catch(() => undefined);
        await reloadCode().catch(() => undefined);
      } catch (caught) {
        setActionError(caught instanceof Error ? caught.message : "Action failed");
      } finally {
        setBusy(null);
      }
    },
    [reload, reloadPlan, reloadCode]
  );

  const canAnalyze = request ? ANALYZABLE.has(request.status) : false;
  const isPlanReady = request?.status === "plan_ready";
  const isApproved = request?.status === "approved";
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

          {/* Execution framework (Phase 9 Step 2) — planning metadata only */}
          <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Cpu className="h-4 w-4 text-brand" aria-hidden="true" />
                <h2 className="text-sm font-semibold text-ink">Execution framework</h2>
              </div>
              <button
                type="button"
                disabled={(!isApproved && !executionPlan) || busy !== null}
                onClick={() => run("execplan", () => generateExecutionPlan(request.id))}
                className="focus-ring inline-flex items-center gap-2 rounded border border-line bg-panel px-3 py-1.5 text-sm font-semibold text-slate-700 hover:bg-mist disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                {busy === "execplan" ? "Generating" : executionPlan ? "Regenerate plan" : "Generate execution plan"}
              </button>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              Planning metadata only. No code is written, committed, pushed, merged, or deployed.
              {isApproved ? null : executionPlan ? null : " Approve the plan first to enable generation."}
            </p>
          </section>

          {executionPlan ? (
            (() => {
              const ctx = executionPlan.repository_context as {
                repository?: { full_name?: string; default_branch?: string; github_linked?: boolean } | null;
                architecture_rules?: unknown[];
                company_rules?: unknown[];
                latest_scans?: unknown[];
                latest_ai_review?: string | null;
                workspace?: { branch_name?: string; state?: { issues?: string[]; clean?: boolean } };
              };
              const issues = ctx.workspace?.state?.issues ?? [];
              return (
                <>
                  {/* Estimated impact */}
                  <Section title="Estimated impact">
                    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      <div>
                        <div className="text-xs uppercase tracking-[0.08em] text-slate-500">Complexity</div>
                        <div className="mt-1 text-lg font-semibold text-ink">{executionPlan.complexity}</div>
                      </div>
                      <div>
                        <div className="text-xs uppercase tracking-[0.08em] text-slate-500">Est. duration</div>
                        <div className="mt-1 text-lg font-semibold text-ink">{executionPlan.estimated_duration ?? "-"}</div>
                      </div>
                      <div>
                        <div className="text-xs uppercase tracking-[0.08em] text-slate-500">Files to modify</div>
                        <div className="mt-1 text-lg font-semibold text-ink">{executionPlan.estimated_files.length}</div>
                      </div>
                      <div>
                        <div className="text-xs uppercase tracking-[0.08em] text-slate-500">Safety</div>
                        <div className="mt-1">
                          <SafetyStatusBadge status={executionPlan.safety_status} />
                        </div>
                      </div>
                    </div>
                    <p className="mt-3 text-sm text-slate-600">{executionPlan.dependency_analysis?.note}</p>
                    {executionPlan.branch_name ? (
                      <p className="mt-1 text-xs text-slate-500">
                        Proposed branch: <span className="font-mono text-slate-700">{executionPlan.branch_name}</span>
                      </p>
                    ) : null}
                  </Section>

                  {/* Execution plan */}
                  <div className="grid gap-6 xl:grid-cols-2">
                    <Section title="Implementation tasks">
                      {executionPlan.tasks.length === 0 ? (
                        <p className="text-sm text-slate-500">No tasks.</p>
                      ) : (
                        <ol className="space-y-2 text-sm text-slate-700">
                          {executionPlan.tasks.map((task) => (
                            <li key={task.order} className="flex gap-2">
                              <span className="font-mono text-slate-400">{task.order}.</span>
                              <span>{task.title}</span>
                            </li>
                          ))}
                        </ol>
                      )}
                    </Section>
                    <Section title="Estimated files">
                      {executionPlan.estimated_files.length === 0 ? (
                        <p className="text-sm text-slate-500">No files estimated.</p>
                      ) : (
                        <ul className="space-y-1 font-mono text-sm text-slate-700">
                          {executionPlan.estimated_files.map((path) => (
                            <li key={path} className="flex items-center gap-2">
                              <FileCode2 className="h-3.5 w-3.5 flex-none text-slate-400" aria-hidden="true" />
                              {path}
                            </li>
                          ))}
                        </ul>
                      )}
                    </Section>
                    <Section title="Rollback strategy">
                      <BulletList items={executionPlan.rollback_strategy} empty="Not specified." />
                    </Section>
                    <Section title="Validation checklist">
                      <BulletList items={executionPlan.validation_checklist} empty="Not specified." />
                    </Section>
                  </div>

                  {/* Safety validation */}
                  <section className="rounded-lg border border-line bg-panel shadow-surface">
                    <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
                      <div className="flex items-center gap-2">
                        <ShieldAlert className="h-4 w-4 text-signal" aria-hidden="true" />
                        <h2 className="text-sm font-semibold text-ink">Safety validation</h2>
                      </div>
                      <SafetyStatusBadge status={executionPlan.safety_status} />
                    </div>
                    <div className="p-4">
                      {executionPlan.safety_findings.length === 0 ? (
                        <p className="text-sm text-emerald-700">No safety findings — change set looks safe.</p>
                      ) : (
                        <ul className="space-y-2 text-sm">
                          {executionPlan.safety_findings.map((finding, index) => (
                            <li
                              key={index}
                              className={clsx(
                                "rounded border px-3 py-2",
                                finding.level === "block"
                                  ? "border-rose-200 bg-rose-50 text-rose-800"
                                  : "border-amber-200 bg-amber-50 text-amber-800"
                              )}
                            >
                              <span className="font-medium">{finding.category}:</span> {finding.message}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </section>

                  {/* Repository context */}
                  <Section title="Repository context">
                    <dl className="grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
                      <div>
                        <dt className="text-slate-500">Repository</dt>
                        <dd className="text-slate-800">{ctx.repository?.full_name ?? "-"}</dd>
                      </div>
                      <div>
                        <dt className="text-slate-500">Default branch</dt>
                        <dd className="text-slate-800">{ctx.repository?.default_branch ?? "-"}</dd>
                      </div>
                      <div>
                        <dt className="text-slate-500">Company rules</dt>
                        <dd className="text-slate-800">{ctx.company_rules?.length ?? 0}</dd>
                      </div>
                      <div>
                        <dt className="text-slate-500">Architecture rules</dt>
                        <dd className="text-slate-800">{ctx.architecture_rules?.length ?? 0}</dd>
                      </div>
                    </dl>
                    <div className="mt-3 text-sm text-slate-600">
                      Recent scans considered: {ctx.latest_scans?.length ?? 0}. Latest AI review:{" "}
                      {ctx.latest_ai_review ? "available" : "none"}.
                    </div>
                    {issues.length > 0 ? (
                      <div className="mt-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                        <div className="font-medium">Repository state issues</div>
                        <BulletList items={issues} empty="" />
                      </div>
                    ) : null}
                  </Section>
                </>
              );
            })()
          ) : null}

          {/* Code generation preview (Phase 9 Step 4) — preview only */}
          <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <FileCode2 className="h-4 w-4 text-brand" aria-hidden="true" />
                <h2 className="text-sm font-semibold text-ink">Code generation preview</h2>
              </div>
              <button
                type="button"
                disabled={(!isApproved && !codePreview) || busy !== null}
                onClick={() => run("codegen", () => generateCodePreview(request.id))}
                className="focus-ring inline-flex items-center gap-2 rounded border border-line bg-panel px-3 py-1.5 text-sm font-semibold text-slate-700 hover:bg-mist disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                {busy === "codegen" ? "Generating" : codePreview ? "Regenerate preview" : "Generate preview"}
              </button>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              Preview only. No files are written, committed, pushed, branched, or turned into a PR.
              {isApproved || codePreview ? null : " Approve the plan first to enable preview."}
            </p>
          </section>

          {codePreview ? (
            <>
              <Section title="Proposed changes">
                {codePreview.summary ? <p className="text-sm text-slate-700">{codePreview.summary}</p> : null}
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
                  <div>
                    <dt className="text-slate-500">Files</dt>
                    <dd className="text-lg font-semibold text-ink">{codePreview.estimated_changes?.files ?? 0}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Est. additions</dt>
                    <dd className="text-lg font-semibold text-emerald-700">
                      +{codePreview.estimated_changes?.estimated_additions ?? 0}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Est. deletions</dt>
                    <dd className="text-lg font-semibold text-rose-700">
                      -{codePreview.estimated_changes?.estimated_deletions ?? 0}
                    </dd>
                  </div>
                </dl>
                {codePreview.affected_files.length > 0 ? (
                  <ul className="mt-3 space-y-1 text-sm">
                    {codePreview.affected_files.map((file, index) => (
                      <li key={index} className="flex items-center gap-2 font-mono text-slate-700">
                        <span className="inline-flex rounded border border-line bg-mist px-1.5 text-xs text-slate-600">
                          {file.change_type}
                        </span>
                        {file.path}
                      </li>
                    ))}
                  </ul>
                ) : null}
                <p className="mt-2 text-xs text-slate-400">
                  {codePreview.ai_available ? "Generated with AI." : "AI unavailable — illustrative fallback."}
                </p>
              </Section>

              <Section title="Diff preview (illustrative — not applied)">
                <pre className="overflow-x-auto rounded border border-line bg-mist p-3 text-xs leading-5 text-slate-800">
                  {codePreview.diff_preview ?? "No diff preview."}
                </pre>
              </Section>

              <div className="grid gap-6 xl:grid-cols-3">
                <Section title="Implementation tasks">
                  <BulletList items={codePreview.implementation_tasks} empty="None." />
                </Section>
                <Section title="Tests to create">
                  <BulletList items={codePreview.tests_to_create} empty="None." />
                </Section>
                <Section title="Documentation updates">
                  <BulletList items={codePreview.documentation_updates} empty="None." />
                </Section>
              </div>
            </>
          ) : null}
        </div>
      ) : null}
    </AppShell>
  );
}
