# Zero Setup Workspace Roadmap

## Phase 11 — Zero Setup Workspace
Repository setup intelligence, environment specification, workspace blueprint generation, real sandbox launch, workspace reliability, and workspace health.

## Phase 11.1 — Real Sandbox Launch
Launch real workspace instances from repository setup plans.

## Phase 11.2 — Workspace Health and Readiness
Validate running workspaces using process, heartbeat, port, HTTP, disk, CPU, memory, dependency, database, and Redis checks.

## Phase 12 — CodeDNA Super Brain
Internal CodeDNA AI brain with memory, knowledge graph, product intelligence, engineering intelligence, debugging intelligence, and planning intelligence.

## Phase 12.0 — Super Brain Core
Internal read-only brain orchestrator with Product, Engineering, Debug, Workspace, Security, Planning, and Memory brains.

## Phase 12.1 — Persistent Memory and Knowledge Graph
Persistent knowledge nodes, edges, retrieval, ingestion, stale detection, and evidence-backed answers.

## Phase 12.2 — Engineering Intelligence
Build module maps, service graphs, API graphs, dependency graphs, import graphs, and impact analysis. Read-only: surface impacted files/components for a change, dependents and dependencies for a component, and architecture review flags (orphans, high fan-in hotspots, integration coupling, stale knowledge). No code execution and no GitHub writes.

## Phase 12.3 — Debug Intelligence and Self-Healing Diagnosis
Read-only diagnosis only — no automatic code changes. Classify test/build/runtime failures, read logs, identify probable root cause, suggest a fix, and map the failure to affected files using the Engineering Graph.

## Phase 12.5 — Controlled Self-Healing Execution
After explicit human approval, apply safe fixes in an isolated workspace, run tests/build, retry with a maximum attempt limit, roll back unsafe patches, and end only in a human-gated draft PR. Never merges, deploys, or pushes to protected branches.
