"use client";

import { useCallback, useState } from "react";
import { Network, RefreshCw, Search } from "lucide-react";
import { Badge } from "@/components/badges";
import { ErrorState } from "@/components/data-state";
import { ActionButton, SectionCard } from "@/components/ui";
import { getKnowledgeGraph, ingestKnowledge, searchKnowledge } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { KnowledgeNeighbor, KnowledgeNode } from "@/types/api";

const STALE_DAYS = 30;

function isStale(updatedAt: string): boolean {
  return Date.now() - new Date(updatedAt).getTime() > STALE_DAYS * 86400_000;
}

function confidenceTone(score: number) {
  if (score >= 0.7) return "success" as const;
  if (score >= 0.4) return "warning" as const;
  return "neutral" as const;
}

export function KnowledgeGraphPanel() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<KnowledgeNode[] | null>(null);
  const [selected, setSelected] = useState<KnowledgeNeighbor | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const search = useCallback(async (q: string) => {
    const text = q.trim();
    if (!text) return;
    setError(null);
    setBusy("search");
    try {
      setResults(await searchKnowledge(text));
      setSelected(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Search failed");
    } finally {
      setBusy(null);
    }
  }, []);

  const select = useCallback(async (node: KnowledgeNode) => {
    setError(null);
    setBusy(`node:${node.id}`);
    try {
      setSelected(await getKnowledgeGraph(node.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Graph lookup failed");
    } finally {
      setBusy(null);
    }
  }, []);

  const ingest = useCallback(async () => {
    setError(null);
    setNotice(null);
    setBusy("ingest");
    try {
      const r = await ingestKnowledge();
      setNotice(`Ingested ${r.nodes} node(s) and ${r.edges} edge(s).`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Ingestion failed");
    } finally {
      setBusy(null);
    }
  }, []);

  return (
    <SectionCard
      title="Knowledge graph"
      icon={Network}
      actions={
        <ActionButton variant="secondary" size="sm" icon={RefreshCw} loading={busy === "ingest"} onClick={ingest}>
          Ingest
        </ActionButton>
      }
    >
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") search(query);
            }}
            placeholder="Search knowledge (e.g. workspace launch, github)"
            className="focus-ring w-full rounded-lg border border-line bg-white py-2.5 pl-9 pr-3 text-sm text-ink placeholder:text-slate-400"
          />
        </div>
        <ActionButton icon={Search} loading={busy === "search"} onClick={() => search(query)}>
          Search
        </ActionButton>
      </div>

      {notice ? <div className="mt-3 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800">{notice}</div> : null}
      {error ? <div className="mt-3"><ErrorState message={error} /></div> : null}

      {results ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">
              Results ({results.length})
            </div>
            {results.length === 0 ? (
              <p className="text-sm text-slate-500">No matching knowledge. Try Ingest first.</p>
            ) : (
              <ul className="space-y-1.5">
                {results.map((n) => (
                  <li key={n.id}>
                    <button
                      type="button"
                      onClick={() => select(n)}
                      className="focus-ring flex w-full items-start justify-between gap-2 rounded-lg border border-line bg-panel px-3 py-2 text-left hover:bg-mist"
                    >
                      <div>
                        <div className="text-sm font-medium text-ink">{n.title}</div>
                        <div className="text-xs text-slate-500">{n.node_type}</div>
                      </div>
                      <div className="flex flex-none items-center gap-1">
                        {isStale(n.updated_at) ? <Badge tone="warning">stale</Badge> : null}
                        <Badge tone={confidenceTone(n.confidence_score)}>{Math.round(n.confidence_score * 100)}%</Badge>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">Node detail</div>
            {!selected ? (
              <p className="text-sm text-slate-500">Select a node to see its relationships.</p>
            ) : (
              <div className="space-y-3 rounded-lg border border-line bg-panel p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-semibold text-ink">{selected.node.title}</div>
                  <div className="flex items-center gap-1">
                    {isStale(selected.node.updated_at) ? <Badge tone="warning">stale</Badge> : <Badge tone="success">fresh</Badge>}
                    <Badge tone={confidenceTone(selected.node.confidence_score)}>
                      {Math.round(selected.node.confidence_score * 100)}%
                    </Badge>
                  </div>
                </div>
                <div className="text-xs text-slate-500">{selected.node.node_type} · updated {formatDateTime(selected.node.updated_at)}</div>
                {selected.node.summary ? <p className="text-sm text-slate-700">{selected.node.summary}</p> : null}

                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">Related</div>
                  {selected.neighbors.length === 0 ? (
                    <p className="mt-1 text-sm text-slate-500">No related nodes.</p>
                  ) : (
                    <ul className="mt-1 space-y-1">
                      {selected.neighbors.map((nb) => {
                        const edge = selected.edges.find(
                          (e) => e.from_node_id === nb.id || e.to_node_id === nb.id
                        );
                        return (
                          <li key={nb.id} className="flex items-center justify-between gap-2 text-sm">
                            <span className="text-slate-700">{nb.title}</span>
                            {edge ? (
                              <span className="rounded border border-line bg-mist px-2 py-0.5 text-xs text-slate-600">
                                {edge.relationship_type}
                              </span>
                            ) : null}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        <p className="mt-3 text-xs text-slate-400">
          Search the persistent knowledge graph, or run Ingest to (re)build it from current CodeDNA data.
        </p>
      )}
    </SectionCard>
  );
}
