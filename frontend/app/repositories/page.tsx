"use client";

import Link from "next/link";
import { useCallback } from "react";
import { GitBranch, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/badges";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/data-state";
import { ActionButton, Column, DataTable, SectionCard } from "@/components/ui";
import { listRepositories } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApiResource } from "@/hooks/use-api-resource";
import type { Repository } from "@/types/api";

const PIPELINE = [
  { slug: "dna", label: "DNA" },
  { slug: "setup-intent", label: "Setup" },
  { slug: "environment", label: "Env" },
  { slug: "workspace", label: "Workspace" },
  { slug: "provision", label: "Provision" },
  { slug: "launch", label: "Launch" },
  { slug: "scans", label: "Scans" }
];

export default function RepositoriesPage() {
  const loader = useCallback(() => listRepositories(), []);
  const { data, error, isLoading, reload } = useApiResource(loader);

  const columns: Column<Repository>[] = [
    {
      key: "repo",
      header: "Repository",
      render: (r) => (
        <div>
          <div className="font-medium text-ink">{r.full_name}</div>
          <div className="text-xs text-slate-500">#{r.github_repository_id}</div>
        </div>
      )
    },
    { key: "branch", header: "Default branch", render: (r) => <span className="font-mono text-xs text-slate-600">{r.default_branch}</span> },
    {
      key: "status",
      header: "Status",
      render: (r) => <Badge tone={r.is_active ? "success" : "neutral"}>{r.is_active ? "active" : "inactive"}</Badge>
    },
    { key: "created", header: "Created", render: (r) => <span className="text-slate-500">{formatDate(r.created_at)}</span> },
    {
      key: "actions",
      header: "Pipeline",
      align: "right",
      render: (r) => (
        <div className="flex flex-wrap justify-end gap-1">
          {PIPELINE.map((p) => (
            <Link
              key={p.slug}
              href={`/repositories/${r.id}/${p.slug}`}
              className="focus-ring rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-brand-soft hover:text-brand-ink"
            >
              {p.label}
            </Link>
          ))}
        </div>
      )
    }
  ];

  return (
    <AppShell
      title="Repositories"
      description="Connected repositories and their governance pipeline"
      actions={
        <ActionButton variant="secondary" size="sm" icon={RefreshCw} onClick={() => reload().catch(() => undefined)}>
          Refresh
        </ActionButton>
      }
    >
      {isLoading ? <TableSkeleton rows={5} columns={5} /> : null}
      {error ? <ErrorState message={error} onRetry={() => reload().catch(() => undefined)} /> : null}
      {data ? (
        <SectionCard title="Connected repositories" icon={GitBranch} bodyClassName="p-0">
          <DataTable
            columns={columns}
            rows={data}
            getRowKey={(r) => r.id}
            empty={
              <div className="p-5">
                <EmptyState
                  icon={GitBranch}
                  title="No repositories connected"
                  description="Install the CodeDNA GitHub App and register a repository to start scanning pull requests. For a demo, run the seed data script."
                />
              </div>
            }
          />
        </SectionCard>
      ) : null}
    </AppShell>
  );
}
