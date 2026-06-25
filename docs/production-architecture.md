# CodeDNA AI Production Architecture

## Overview

CodeDNA AI is an AI engineering governance platform for corporate software teams. In production it receives GitHub App webhook events, creates idempotent pull request scan jobs, runs Semgrep and AI review workers, stores scan reports in PostgreSQL, and publishes results back to GitHub using Checks and PR comments.

## Components

### GitHub App

The GitHub App is the trust boundary for repository access. It should be installed only on repositories managed by the customer organization. Required permissions are:

- Pull requests: read
- Checks: read/write
- Contents: read
- Metadata: read

Subscribed events include pull request, check run, check suite, installation, and installation repositories.

### Cloudflare / Production Ingress

Production ingress terminates TLS and routes webhook/API traffic to the FastAPI service. GitHub webhooks must reach `/api/v1/github/webhooks`. Cloudflare should enforce HTTPS, request size limits, and basic edge protections. The backend still verifies the GitHub signature for every webhook.

### FastAPI Backend

The backend owns API auth, organization scoping, GitHub webhook validation, scan creation, dashboard APIs, admin settings, health checks, and operational metrics. It persists application state in PostgreSQL and enqueues scan jobs through Redis/Celery.

### PostgreSQL

PostgreSQL stores organizations, users, GitHub installations, repositories, rules, scans, reports, and audit logs. Pull request scans include an idempotency key derived from installation, repository, PR number, head SHA, and event action to prevent duplicate scan jobs.

### Redis

Redis is used as the Celery broker/result backend and for operational queues/counters:

- Celery queue: `celery`
- Dead-letter scans: `codedna:dead_letter_scans`
- AI review usage counters: daily and monthly request keys

### Celery Worker

The worker runs `scan.run_pr_scan`. It fetches changed PR files, runs Semgrep, checks company and architecture rules, optionally runs AI review, calculates risk, stores the report, updates the GitHub Check Run, and posts a PR comment.

### Semgrep

Semgrep provides deterministic security and code-quality findings. Semgrep failures are treated as retryable task failures until the worker exhausts retries.

### Groq AI Review

Groq generates human-readable PR review sections. AI review is guarded by configurable limits for daily/monthly request counts, max files, and max diff characters. If limits are exceeded, the scan still completes and the GitHub Check Run includes an AI skipped message.

### GitHub Check Run Flow

1. Pull request webhook arrives.
2. Backend verifies webhook signature.
3. Backend creates or reuses an idempotent scan record.
4. Worker creates or updates the `CodeDNA AI` Check Run as `in_progress`.
5. Worker runs scan services.
6. Worker updates the Check Run as `completed`.
7. Check conclusion is `failure` for company or architecture violations, `success` for clean scans, and `neutral` when AI is skipped and no findings exist.

### Failure, Retry, and Dead-letter Flow

`scan.run_pr_scan` retries transient failures with exponential backoff and a maximum of three retries. Retry attempts are logged. When retries are exhausted:

1. The scan is marked failed.
2. The GitHub Check Run is completed with conclusion `failure`.
3. Failed scan metadata is pushed to Redis list `codedna:dead_letter_scans`.
4. Admins can inspect dead-letter items through `/api/v1/admin/dead-letter-scans`.

### Deployment Notes

- Store secrets only in environment variables or the deployment secret manager.
- Run Alembic migrations before deploying new backend/worker images.
- Deploy backend and worker from the same image/version.
- Monitor `/health`, `/api/v1/health`, `/api/v1/admin/queue-metrics`, worker logs, and dead-letter volume.
- Keep Redis and PostgreSQL private to the application network.
- Rotate GitHub App private keys and webhook secrets on a regular schedule.
