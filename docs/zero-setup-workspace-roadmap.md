# Zero-Setup Workspace Engine — Roadmap (Phase 11)

> Status: roadmap / design only. Not implemented. This document defines the
> vision, architecture, phasing, and safety model for a future Phase 11. It is
> intentionally separate from Phase 10 (the AI execution engine), which is being
> built incrementally and remains the foundation this feature builds on.

## 1. One-line vision

Let any user upload a project or connect any repository and have CodeDNA
**automatically detect the stack, read the README/setup files, generate
environment configuration, and launch a working cloud workspace** — with no
manual developer setup, and with the same safety guardrails that govern the AI
execution engine.

## 2. Why this matters

Onboarding to an unfamiliar codebase is the single biggest source of "works on
my machine" friction: installing the right language runtime, services
(Postgres/Redis), environment variables, and build tooling. CodeDNA already
*understands* repositories (Repository DNA) and can *safely operate* inside
isolated workspaces (Secure Workspace Manager, Repository Materializer, Safe
Change Applier). The Zero-Setup Workspace Engine turns that understanding into a
running environment: a reviewer, a new hire, or the AI engineering agent can be
productive in minutes instead of hours.

## 3. Competitor comparison

The table compares capability *categories* (not pricing, which changes
frequently). CodeDNA's differentiator is that the workspace is driven by an
existing governance + AI-review engine, not a generic container.

| Capability | GitHub Codespaces | Gitpod | Replit | Coder | CodeSandbox | **CodeDNA Zero-Setup** |
| --- | --- | --- | --- | --- | --- | --- |
| Cloud dev workspace | Yes | Yes | Yes | Yes | Yes | Yes (planned) |
| Works from any repo/upload | Repo | Repo | Repo/upload | Repo | Repo/upload | Repo **and** upload |
| Requires a config file to "just work" | Often (devcontainer) | Often (.gitpod.yml) | Minimal | Often | Minimal | **No — auto-detected** |
| Automatic stack detection | Partial | Partial | Partial | No | Partial | **First-class (Repository DNA)** |
| Reads README/setup to infer setup | No | No | No | No | No | **Yes (AI-assisted)** |
| Generates env config automatically | No | No | Partial | No | Partial | **Yes** |
| Built-in code review / governance | No | No | No | No | No | **Yes (core product)** |
| Safe AI code execution in workspace | No | No | Agent (beta) | No | No | **Yes (human-gated)** |
| Secrets never materialized | N/A | N/A | N/A | N/A | N/A | **Enforced (redaction)** |

Takeaway: existing tools give you a container; CodeDNA gives you an *understood,
governed, AI-operable* environment that configures itself.

## 4. Product vision

1. **Connect or upload.** A user connects a GitHub repository (existing flow) or
   uploads a project archive.
2. **Understand.** CodeDNA generates/refreshes Repository DNA — languages,
   frameworks, package managers, databases, queues, test/build tooling, Docker,
   CI/CD, important files.
3. **Read intent.** An AI pass reads README, CONTRIBUTING, Makefile, scripts,
   and dependency manifests to infer the intended setup, run, and test commands.
4. **Generate environment configuration.** Produce a normalized, reviewable
   environment spec (base image, services, env-var template, install/build/run/
   test commands) — never inventing secret values.
5. **Launch.** Provision an isolated cloud workspace from that spec and report a
   ready-to-use environment, with health checks.
6. **Operate (optional).** The AI execution engine (Phase 10) can then plan,
   generate, validate, and stage changes inside that workspace — all human-gated.

Every step is **previewable and overridable** before anything runs.

## 5. Architecture

The engine is a thin orchestration layer over components that already exist or
are being built in Phase 10. No component bypasses the established safety model.

```
Upload / Connect Repo
        │
        ▼
[Repository DNA]  ──────────────►  stack fingerprint (languages, frameworks, services)
        │
        ▼
[Setup Intent Reader]  (AI Provider Router)
        │   reads README / Makefile / scripts / manifests (read-only)
        ▼
[Environment Spec Generator]
        │   normalized spec: base image, services, env template,
        │   install/build/run/test commands  (NO secret values)
        ▼
[Workspace Provisioner]
        │   uses Secure Workspace Manager + Repository Materializer
        │   isolated sandbox, size/forbidden-path limits, secrets redacted
        ▼
[Runtime Launcher]  ──►  health checks, ready signal
        │
        ▼ (optional, human-gated)
[AI Execution Engine]  (Phase 10: plan → generate → apply → validate → draft PR)
```

Key building blocks and their reuse:

- **Repository DNA service** — provides the stack fingerprint that seeds
  detection (already implemented).
- **Setup Intent Reader** — a new AI pass, routed through the **AI Provider
  Router** (Groq default; OpenAI/Anthropic pluggable), that reads docs/manifests
  read-only and proposes setup/run/test commands.
- **Environment Spec Generator** — converts DNA + intent into a structured,
  reviewable spec. Deterministic fallback when AI is unavailable.
- **Secure Workspace Manager** — isolated temp/cloud workspace, path-traversal
  and forbidden-path protection, max-size enforcement, cleanup (implemented).
- **Repository Materializer** — read-only source materialization with secret
  redaction and `.git` protection (implemented).
- **Runtime Launcher** — provisions the container/VM from the spec and runs
  health checks. New in Phase 11; pluggable backend (local Docker, then a cloud
  runner).

## 6. Phases

- **Phase 11.0 — Environment Spec (metadata only).** Detect stack via DNA, read
  setup intent, emit a structured environment spec + reviewable preview. No
  containers launched. (Closest to current capabilities.)
- **Phase 11.1 — Local sandbox launch.** Provision an isolated local/dev
  container from the spec; health-check; expose logs. Read-only source.
- **Phase 11.2 — Cloud workspace.** Run the same spec on a managed cloud runner
  with per-workspace isolation, quotas, and TTL/auto-cleanup.
- **Phase 11.3 — Upload support.** Accept project archives (not just connected
  repos), with the same detection and safety pipeline.
- **Phase 11.4 — AI-operable workspace.** Connect the Phase 10 execution engine
  so an approved engineering request can be planned, generated, applied, and
  validated *inside* the launched workspace — still ending only in a human-gated
  draft PR.

Each phase ships behind verification (tests + build) and a separate commit, and
never regresses existing functionality.

## 7. Safety limits (non-negotiable)

- **No secrets are ever materialized.** `.env`, credentials, private keys, and
  `.git` are redacted/protected by the Repository Materializer; the spec uses an
  env-var *template* and never invents or stores secret values.
- **Isolation.** Every workspace is sandboxed (Secure Workspace Manager): no
  path escapes the workspace, forbidden system paths are rejected, and a maximum
  size is enforced.
- **No autonomous side effects.** The engine does not commit, push, merge,
  deploy, or modify the real repository. AI-driven changes remain preview-only
  and human-approved, ending in a draft PR.
- **Network egress control.** Launched workspaces run with restricted, allow-
  listed network access; no arbitrary outbound by default.
- **Resource quotas + TTL.** CPU/memory/disk limits and automatic expiry/cleanup
  to prevent runaway cost or orphaned environments.
- **Provider-agnostic AI.** All AI passes go through the AI Provider Router;
  there is no hard dependency on any single provider and no automatic Ollama
  fallback.
- **Auditability.** Every materialization, spec generation, launch, and AI
  action is logged and audit-recorded, consistent with the rest of CodeDNA.

## 8. How it connects to Repository DNA and the AI execution engine

- **Repository DNA is the detection substrate.** The engine consumes the DNA
  fingerprint (languages, frameworks, package managers, databases, queues,
  testing/build tools, Docker, CI/CD, important files) instead of re-deriving the
  stack. DNA is read-only and inferred from CodeDNA's own data — no cloning.
- **The environment spec feeds the AI execution engine.** Once a workspace is
  launched, the Phase 10 pipeline operates against it:
  - Repository Materializer prepares source read-only (secrets redacted).
  - Code Generation Engine produces a structured change plan (provider-routed).
  - Safe Change Applier applies the plan **inside the workspace only**, with
    dry-run, patch preview, and rollback.
  - Autonomous Validation runs tests/build/Semgrep/CodeDNA review/rules and, only
    on success, prepares a **draft pull request** — never a merge or deploy.
- **Same guardrails end to end.** Branch safety (isolated `codedna/ai/...`
  branches), protected-file rejection, size/diff limits, and human approval are
  shared across the Zero-Setup engine and the execution engine, so launching a
  workspace never widens the agent's authority.

## 9. Open questions (to resolve before building)

- Cloud runner backend choice and isolation primitive (microVM vs container).
- Per-org quotas, TTL defaults, and cost controls.
- Upload size/type limits and malware scanning for the upload path.
- Caching strategy for base images and dependency layers to keep launch fast.
- How much of the env spec should be user-editable before launch.
