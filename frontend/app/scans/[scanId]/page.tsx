"use client";

import Link from "next/link";
import { use, useCallback } from "react";
import type { ReactNode } from "react";
import { ArrowLeft, FileCode2, Gauge, GitPullRequestArrow, ShieldAlert } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { RiskBadge, SeverityBadge, StatusBadge } from "@/components/badges";
import { EmptyState, ErrorState, LoadingState } from "@/components/data-state";
import { MetricCard } from "@/components/metric-card";
import { getScan } from "@/lib/api";
import { formatDateTime, formatScore, shortSha } from "@/lib/format";
import { useApiResource } from "@/hooks/use-api-resource";
import type { Finding } from "@/types/api";

function FindingTable({ title, findings }: { title: string; findings: Finding[] }) {
  return (
    <section className="rounded-lg border border-line bg-panel shadow-surface">
      <div className="border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
      </div>
      {findings.length === 0 ? (
        <EmptyState title="No findings" />
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-line text-sm">
            <thead className="bg-mist text-left text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
              <tr>
                <th className="px-4 py-3">Severity</th>
                <th className="px-4 py-3">Finding</th>
                <th className="px-4 py-3">Location</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {findings.map((finding, index) => (
                <tr key={`${finding.title ?? "finding"}-${index}`} className="hover:bg-mist/70">
                  <td className="whitespace-nowrap px-4 py-3">
                    <SeverityBadge severity={finding.severity} />
                  </td>
                  <td className="min-w-72 px-4 py-3">
                    <div className="font-medium text-ink">{finding.title ?? finding.source ?? finding.category ?? "Finding"}</div>
                    {finding.description ? <div className="mt-1 text-slate-500">{finding.description}</div> : null}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                    {finding.path ? `${finding.path}${finding.line ? `:${finding.line}` : ""}` : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function MarkdownBlock({ markdown }: { markdown: string }) {
  const nodes: ReactNode[] = [];
  let listItems: string[] = [];

  function flushList(key: string) {
    if (listItems.length === 0) {
      return;
    }
    nodes.push(
      <ul key={key} className="list-disc space-y-1 pl-5 text-sm text-slate-700">
        {listItems.map((item, index) => (
          <li key={`${key}-${index}`}>{item}</li>
        ))}
      </ul>
    );
    listItems = [];
  }

  markdown.split(/\r?\n/).forEach((rawLine, index) => {
    const line = rawLine.trim();
    if (!line) {
      flushList(`list-${index}`);
      return;
    }

    const bullet = line.match(/^[-*]\s+(.*)$/);
    if (bullet) {
      listItems.push(bullet[1]);
      return;
    }

    flushList(`list-${index}`);

    if (line.startsWith("### ")) {
      nodes.push(
        <h3 key={index} className="pt-2 text-sm font-semibold text-ink">
          {line.slice(4)}
        </h3>
      );
    } else if (line.startsWith("## ")) {
      nodes.push(
        <h2 key={index} className="pt-2 text-base font-semibold text-ink">
          {line.slice(3)}
        </h2>
      );
    } else if (line.startsWith("# ")) {
      nodes.push(
        <h2 key={index} className="text-base font-semibold text-ink">
          {line.slice(2)}
        </h2>
      );
    } else {
      nodes.push(
        <p key={index} className="text-sm leading-6 text-slate-700">
          {line}
        </p>
      );
    }
  });
  flushList("list-final");

  return <div className="space-y-3">{nodes}</div>;
}

function AIReviewSection({ markdown }: { markdown: string | null }) {
  return (
    <section className="rounded-lg border border-line bg-panel shadow-surface">
      <div className="border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold text-ink">AI Review</h2>
      </div>
      <div className="p-4">
        {markdown && markdown.trim().length > 0 ? <MarkdownBlock markdown={markdown} /> : <EmptyState title="AI review not available for this scan" />}
      </div>
    </section>
  );
}

export default function ScanDetailPage({
  params,
}: {
  params: Promise<{ scanId: string }>;
}) {
  const { scanId } = use(params);

  const loader = useCallback(() => getScan(scanId), [scanId]);

  const { data: scan, error, isLoading, reload } = useApiResource(loader);

  return (
    <AppShell
      title={scan ? `PR #${scan.github_pr_number}` : "Scan detail"}
      actions={
        <Link
          className="focus-ring inline-flex h-9 w-9 items-center justify-center rounded border border-line bg-panel text-slate-700 hover:bg-mist"
          href="/scans"
          title="Scans"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </Link>
      }
    >
      {isLoading ? <LoadingState label="Loading scan" /> : null}
      {error ? <ErrorState message={error} onRetry={() => reload().catch(() => undefined)} /> : null}
      {scan ? (
        <div className="space-y-6">
          <section className="rounded-lg border border-line bg-panel p-4 shadow-surface">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={scan.status} />
                  <RiskBadge level={scan.risk_level} />
                </div>
                <h2 className="mt-3 text-lg font-semibold text-ink">{scan.title ?? scan.repository_full_name ?? scan.id}</h2>
                <p className="mt-1 text-sm text-slate-500">{scan.repository_full_name}</p>
              </div>
              {scan.github_pr_url ? (
                <a
                  className="focus-ring rounded px-2 py-1 text-sm font-medium text-brand hover:bg-mist"
                  href={scan.github_pr_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  GitHub PR
                </a>
              ) : null}
            </div>
            <dl className="mt-4 grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
              <div>
                <dt className="text-slate-500">Head SHA</dt>
                <dd className="font-mono text-slate-800">{shortSha(scan.head_sha)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Base SHA</dt>
                <dd className="font-mono text-slate-800">{shortSha(scan.base_sha)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Check Run</dt>
                <dd className="font-mono text-slate-800">{scan.github_check_run_id ?? "-"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Trigger</dt>
                <dd className="text-slate-800">{scan.trigger}</dd>
              </div>
            </dl>
            <dl className="mt-4 grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
              <div>
                <dt className="text-slate-500">Started</dt>
                <dd className="text-slate-800">{formatDateTime(scan.started_at)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Completed</dt>
                <dd className="text-slate-800">{formatDateTime(scan.completed_at)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Created</dt>
                <dd className="text-slate-800">{formatDateTime(scan.created_at)}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Updated</dt>
                <dd className="text-slate-800">{formatDateTime(scan.updated_at)}</dd>
              </div>
            </dl>
          </section>

          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard icon={Gauge} label="Risk score" value={formatScore(scan.risk_score)} detail="/100" />
            <MetricCard icon={ShieldAlert} label="Findings" value={scan.findings_count} />
            <MetricCard icon={FileCode2} label="Files changed" value={scan.files_changed} />
            <MetricCard icon={GitPullRequestArrow} label="Line delta" value={`+${scan.lines_added} / -${scan.lines_deleted}`} />
          </section>

          {scan.failure_reason ? <ErrorState message={scan.failure_reason} /> : null}
          {scan.summary ? (
            <section className="rounded-lg border border-line bg-panel p-4 text-sm text-slate-700 shadow-surface">{scan.summary}</section>
          ) : null}

          <AIReviewSection markdown={scan.ai_review_markdown} />

          <div className="grid gap-6 xl:grid-cols-2">
            <FindingTable title="Company rule violations" findings={scan.company_rule_violations} />
            <FindingTable title="Architecture violations" findings={scan.architecture_violations} />
            <FindingTable title="Semgrep findings" findings={scan.semgrep_findings} />
            <FindingTable title="AI findings" findings={scan.ai_findings} />
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}
