"use client";

import { FormEvent, useCallback, useState } from "react";
import clsx from "clsx";
import { Plus, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { SeverityBadge } from "@/components/badges";
import { EmptyState, ErrorState, LoadingState } from "@/components/data-state";
import {
  createArchitectureRule,
  createCompanyRule,
  listArchitectureRules,
  listCompanyRules
} from "@/lib/api";
import { useApiResource } from "@/hooks/use-api-resource";
import type { ArchitectureRule, CompanyRule, RuleSeverity } from "@/types/api";

type RuleTab = "company" | "architecture";

const severities: RuleSeverity[] = ["info", "low", "medium", "high", "critical"];

function RuleStatus({ active }: { active: boolean }) {
  return (
    <span className="inline-flex rounded border border-line bg-mist px-2 py-0.5 text-xs font-medium text-slate-700">
      {active ? "active" : "inactive"}
    </span>
  );
}

export default function RulesPage() {
  const [tab, setTab] = useState<RuleTab>("company");
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [companyForm, setCompanyForm] = useState({
    name: "",
    description: "",
    rule_type: "forbidden_text" as CompanyRule["rule_type"],
    pattern: "console.log",
    severity: "medium" as RuleSeverity
  });
  const [architectureForm, setArchitectureForm] = useState({
    name: "",
    description: "",
    source_path_pattern: "frontend/**/*.tsx",
    forbidden_import_pattern: "app\\.models",
    severity: "high" as RuleSeverity
  });
  const loader = useCallback(async () => {
    const [companyRules, architectureRules] = await Promise.all([listCompanyRules(), listArchitectureRules()]);
    return { companyRules, architectureRules };
  }, []);
  const { data, error: loadError, isLoading, reload } = useApiResource(loader);

  async function onCreateCompanyRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSaving(true);
    try {
      await createCompanyRule(companyForm);
      setCompanyForm((current) => ({ ...current, name: "", description: "" }));
      await reload();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create company rule");
    } finally {
      setIsSaving(false);
    }
  }

  async function onCreateArchitectureRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSaving(true);
    try {
      await createArchitectureRule(architectureForm);
      setArchitectureForm((current) => ({ ...current, name: "", description: "" }));
      await reload();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create architecture rule");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <AppShell
      title="Rules"
      actions={
        <button
          type="button"
          className="focus-ring inline-flex h-9 w-9 items-center justify-center rounded border border-line bg-panel text-slate-700 hover:bg-mist"
          onClick={() => reload().catch(() => undefined)}
          title="Refresh"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
        </button>
      }
    >
      <div className="mb-4 inline-flex rounded border border-line bg-panel p-1 shadow-surface">
        {(["company", "architecture"] as RuleTab[]).map((nextTab) => (
          <button
            key={nextTab}
            type="button"
            className={clsx(
              "focus-ring rounded px-3 py-1.5 text-sm font-medium",
              tab === nextTab ? "bg-brand text-white" : "text-slate-700 hover:bg-mist"
            )}
            onClick={() => setTab(nextTab)}
          >
            {nextTab === "company" ? "Company" : "Architecture"}
          </button>
        ))}
      </div>

      {isLoading ? <LoadingState label="Loading rules" /> : null}
      {loadError ? <ErrorState message={loadError} onRetry={() => reload().catch(() => undefined)} /> : null}
      {error ? <div className="mb-4"><ErrorState message={error} /></div> : null}

      {data && tab === "company" ? (
        <div className="grid gap-6 xl:grid-cols-[380px_1fr]">
          <form className="space-y-3 rounded-lg border border-line bg-panel p-4 shadow-surface" onSubmit={onCreateCompanyRule}>
            <h2 className="text-sm font-semibold text-ink">Company rule</h2>
            <input
              className="focus-ring w-full rounded border border-line px-3 py-2 text-sm"
              placeholder="Name"
              value={companyForm.name}
              onChange={(event) => setCompanyForm((current) => ({ ...current, name: event.target.value }))}
              required
            />
            <textarea
              className="focus-ring min-h-24 w-full rounded border border-line px-3 py-2 text-sm"
              placeholder="Description"
              value={companyForm.description}
              onChange={(event) => setCompanyForm((current) => ({ ...current, description: event.target.value }))}
              required
            />
            <select
              className="focus-ring w-full rounded border border-line px-3 py-2 text-sm"
              value={companyForm.rule_type}
              onChange={(event) => setCompanyForm((current) => ({ ...current, rule_type: event.target.value as CompanyRule["rule_type"] }))}
            >
              <option value="forbidden_text">Forbidden text</option>
              <option value="required_text">Required text</option>
              <option value="regex">Regex</option>
              <option value="file_path">File path</option>
            </select>
            <textarea
              className="focus-ring min-h-20 w-full rounded border border-line px-3 py-2 font-mono text-sm"
              placeholder="Pattern"
              value={companyForm.pattern}
              onChange={(event) => setCompanyForm((current) => ({ ...current, pattern: event.target.value }))}
              required
            />
            <select
              className="focus-ring w-full rounded border border-line px-3 py-2 text-sm"
              value={companyForm.severity}
              onChange={(event) => setCompanyForm((current) => ({ ...current, severity: event.target.value as RuleSeverity }))}
            >
              {severities.map((severity) => (
                <option key={severity} value={severity}>
                  {severity}
                </option>
              ))}
            </select>
            <button
              type="submit"
              className="focus-ring inline-flex w-full items-center justify-center gap-2 rounded bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-[#125870] disabled:opacity-70"
              disabled={isSaving}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add rule
            </button>
          </form>
          <CompanyRuleTable rules={data.companyRules} />
        </div>
      ) : null}

      {data && tab === "architecture" ? (
        <div className="grid gap-6 xl:grid-cols-[380px_1fr]">
          <form className="space-y-3 rounded-lg border border-line bg-panel p-4 shadow-surface" onSubmit={onCreateArchitectureRule}>
            <h2 className="text-sm font-semibold text-ink">Architecture rule</h2>
            <input
              className="focus-ring w-full rounded border border-line px-3 py-2 text-sm"
              placeholder="Name"
              value={architectureForm.name}
              onChange={(event) => setArchitectureForm((current) => ({ ...current, name: event.target.value }))}
              required
            />
            <textarea
              className="focus-ring min-h-24 w-full rounded border border-line px-3 py-2 text-sm"
              placeholder="Description"
              value={architectureForm.description}
              onChange={(event) => setArchitectureForm((current) => ({ ...current, description: event.target.value }))}
              required
            />
            <input
              className="focus-ring w-full rounded border border-line px-3 py-2 font-mono text-sm"
              value={architectureForm.source_path_pattern}
              onChange={(event) => setArchitectureForm((current) => ({ ...current, source_path_pattern: event.target.value }))}
              required
            />
            <input
              className="focus-ring w-full rounded border border-line px-3 py-2 font-mono text-sm"
              value={architectureForm.forbidden_import_pattern}
              onChange={(event) => setArchitectureForm((current) => ({ ...current, forbidden_import_pattern: event.target.value }))}
              required
            />
            <select
              className="focus-ring w-full rounded border border-line px-3 py-2 text-sm"
              value={architectureForm.severity}
              onChange={(event) => setArchitectureForm((current) => ({ ...current, severity: event.target.value as RuleSeverity }))}
            >
              {severities.map((severity) => (
                <option key={severity} value={severity}>
                  {severity}
                </option>
              ))}
            </select>
            <button
              type="submit"
              className="focus-ring inline-flex w-full items-center justify-center gap-2 rounded bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-[#125870] disabled:opacity-70"
              disabled={isSaving}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add rule
            </button>
          </form>
          <ArchitectureRuleTable rules={data.architectureRules} />
        </div>
      ) : null}
    </AppShell>
  );
}

function CompanyRuleTable({ rules }: { rules: CompanyRule[] }) {
  if (rules.length === 0) {
    return (
      <EmptyState
        title="No company rules"
        description="Add a company rule using the form to enforce organization policies on every pull request."
      />
    );
  }

  return (
    <section className="overflow-hidden rounded-lg border border-line bg-panel shadow-surface">
      <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-line text-sm">
        <thead className="bg-mist text-left text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
          <tr>
            <th className="px-4 py-3">Name</th>
            <th className="px-4 py-3">Type</th>
            <th className="px-4 py-3">Severity</th>
            <th className="px-4 py-3">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rules.map((rule) => (
            <tr key={rule.id} className="hover:bg-mist/70">
              <td className="min-w-72 px-4 py-3">
                <div className="font-medium text-ink">{rule.name}</div>
                <div className="mt-1 max-w-2xl truncate text-slate-500">{rule.pattern}</div>
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-slate-700">{rule.rule_type}</td>
              <td className="whitespace-nowrap px-4 py-3">
                <SeverityBadge severity={rule.severity} />
              </td>
              <td className="whitespace-nowrap px-4 py-3">
                <RuleStatus active={rule.is_active} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </section>
  );
}

function ArchitectureRuleTable({ rules }: { rules: ArchitectureRule[] }) {
  if (rules.length === 0) {
    return (
      <EmptyState
        title="No architecture rules"
        description="Define architecture rules to catch layer-boundary and dependency violations automatically."
      />
    );
  }

  return (
    <section className="overflow-hidden rounded-lg border border-line bg-panel shadow-surface">
      <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-line text-sm">
        <thead className="bg-mist text-left text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
          <tr>
            <th className="px-4 py-3">Name</th>
            <th className="px-4 py-3">Source</th>
            <th className="px-4 py-3">Forbidden import</th>
            <th className="px-4 py-3">Severity</th>
            <th className="px-4 py-3">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rules.map((rule) => (
            <tr key={rule.id} className="hover:bg-mist/70">
              <td className="min-w-64 px-4 py-3 font-medium text-ink">{rule.name}</td>
              <td className="whitespace-nowrap px-4 py-3 font-mono text-slate-700">{rule.source_path_pattern}</td>
              <td className="whitespace-nowrap px-4 py-3 font-mono text-slate-700">{rule.forbidden_import_pattern}</td>
              <td className="whitespace-nowrap px-4 py-3">
                <SeverityBadge severity={rule.severity} />
              </td>
              <td className="whitespace-nowrap px-4 py-3">
                <RuleStatus active={rule.is_active} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </section>
  );
}
