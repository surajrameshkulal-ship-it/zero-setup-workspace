# CodeDNA AI — Release Notes

Release notes are organized by delivery phase, newest first. Dates use ISO format.

---

## Phase 8 — Demo readiness & polish (2026-06-25)

Focus: make the product demo-ready and presentable to customers without changing
core scanning behavior.

### Added

- **Marketing landing page** at `/` — replaces the bare dashboard redirect with a
  real public page (hero, sample Check Run card, feature grid, how-it-works, and
  calls to action) built on the existing design system.
- **Demo seed data script** (`app.scripts.seed_demo_data`) — provisions a demo
  organization, admin user, repositories, and a deterministic, lifelike set of
  pull-request scans (varied status, risk, findings, and AI review summaries).
  Idempotent and re-runnable; supports `--reset`.
- **Production deployment checklist** (`docs/production-deployment-checklist.md`).
- **Richer UI states** — skeleton loaders, retryable error states, and empty
  states with icons, descriptions, and guidance across the dashboard, scans,
  repositories, scan history, rules, and dead-letter pages.

### Changed

- **Responsive polish** — rule tables now scroll on narrow screens, dashboard card
  rows fill the tablet breakpoint, the app header truncates gracefully on mobile,
  and an explicit responsive viewport is set.
- **README** updated to reflect the Groq (OpenAI-compatible) AI provider, the
  health/admin operations endpoints, the dashboard feature set, and demo seeding.

### Notes

- No changes to the scan pipeline, data model semantics, or existing APIs.
- Verification: backend tests (`pytest backend/tests`) and frontend build
  (`cd frontend && npm run build`) should pass with no regressions.

---

## Phase 7 — Frontend dashboard

### Added

- Overview dashboard with summary metrics, risk summary, health status, and queue
  metrics cards.
- Repository list, per-repository scan history, and scan detail views.
- Scan detail rendering of the AI review (from `ai_review_markdown`), risk summary,
  findings tables, and metadata.
- Admin pages for queue metrics and dead-letter scans.
- Typed API client, response type definitions, and formatting utilities.

---

## Phase 6 — Production hardening

### Added

- Duplicate scan prevention and webhook idempotency.
- Celery retry with exponential backoff and a dead-letter queue.
- Health endpoints (`/health`, `/api/v1/health`) covering application, PostgreSQL,
  Redis, and the Celery queue.
- Redis queue metrics and an AI rate/cost limiter.
- Security hardening, audit logging, and organization-scoped admin APIs.
- Production architecture and autonomous remediation design documents.

### Endpoints

- `GET /health`
- `GET /api/v1/health`
- `GET /api/v1/admin/queue-metrics`
- `GET /api/v1/admin/dead-letter-scans`

---

## Phases 1–5 — Core platform

### Added

- GitHub App integration, webhook processing, and (tunnelled) local delivery.
- Repository registration and pull-request scanning.
- Semgrep static analysis integration.
- AI review generation and presentation inside GitHub Check Runs.
- Dashboard APIs and verified backend functionality.
