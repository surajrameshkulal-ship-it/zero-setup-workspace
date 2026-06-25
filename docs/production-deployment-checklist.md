# CodeDNA AI — Production Deployment Checklist

Use this checklist when promoting CodeDNA AI to a staging or production
environment. Work top to bottom; do not skip the security and verification
sections. Items marked **(required)** must be satisfied before taking traffic.

## 1. Configuration and secrets

- [ ] **(required)** Set `ENVIRONMENT=production` and `DEBUG=false`.
- [ ] **(required)** Generate a unique, long, random `SECRET_KEY` (do not reuse the example value).
- [ ] **(required)** Set a strong `GITHUB_WEBHOOK_SECRET` and configure the same value in the GitHub App.
- [ ] **(required)** Provide the GitHub App credentials: `GITHUB_APP_ID`, `GITHUB_APP_SLUG`, and `GITHUB_PRIVATE_KEY`.
- [ ] **(required)** Configure the AI provider: set `AI_PROVIDER` and the matching API key (`GROQ_API_KEY` or `OPENAI_API_KEY`) and model, or set `AI_REVIEW_ENABLED=false`.
- [ ] Set `ALLOWED_ORIGINS` to the exact production frontend origin(s) — no wildcards.
- [ ] Set `ACCESS_TOKEN_EXPIRE_MINUTES` to an appropriate session lifetime.
- [ ] Store all secrets in a managed secret store or the platform's secret manager — never commit `.env`.
- [ ] Confirm `.env` and private keys are excluded by `.gitignore` / `.dockerignore`.

## 2. Database

- [ ] **(required)** Provision a managed PostgreSQL instance (separate from app hosts).
- [ ] **(required)** Set `DATABASE_URL` to the production database with TLS enabled.
- [ ] **(required)** Run migrations: `alembic upgrade head`.
- [ ] Create a least-privilege application database user (no superuser).
- [ ] Configure automated backups and verify a test restore.
- [ ] Set connection pool sizing appropriate to expected worker/API concurrency.

## 3. Redis and queue

- [ ] **(required)** Provision a managed Redis instance and set `REDIS_URL` (with auth/TLS).
- [ ] Confirm Redis persistence/eviction policy is appropriate for the broker and result backend.
- [ ] Verify the Celery worker connects and processes the scan queue.
- [ ] Confirm retry/backoff and the dead-letter queue behave as expected under failure.

## 4. Services and processes

- [ ] **(required)** Run the API without `--reload` (e.g. `uvicorn app.main:app --host 0.0.0.0 --port 8000` behind a process manager, or Gunicorn with Uvicorn workers).
- [ ] **(required)** Run at least one Celery worker process: `celery -A app.core.celery_app.celery_app worker --loglevel=INFO`.
- [ ] Build and serve the frontend with `npm run build` + `npm start` (not `npm run dev`).
- [ ] Set `NEXT_PUBLIC_API_URL` to the production API base URL at build time.
- [ ] Place the API and frontend behind a TLS-terminating reverse proxy / load balancer.
- [ ] Configure process supervision and automatic restart for API, worker, and frontend.

## 5. Security

- [ ] **(required)** Enforce HTTPS everywhere; redirect HTTP to HTTPS.
- [ ] **(required)** Verify webhook signature checking (`X-Hub-Signature-256`) is active and rejects bad signatures.
- [ ] Confirm tenant isolation: organization-scoped endpoints reject cross-org access.
- [ ] Rotate the default admin password; do not ship `admin@codedna.ai` / `Admin@123` to production.
- [ ] Restrict admin endpoints (`/api/v1/admin/*`) to authorized users only.
- [ ] Review CORS, security headers, and rate limits at the proxy layer.
- [ ] Confirm audit logging is enabled and captured to durable storage.

## 6. Observability

- [ ] **(required)** Wire health checks to the load balancer: `GET /health` (or `/api/v1/health`).
- [ ] Ship application logs to a central log system; set `LOG_LEVEL` appropriately (e.g. `INFO`).
- [ ] Monitor `GET /api/v1/admin/queue-metrics` (queue depth, dead-letter count) and alert on thresholds.
- [ ] Alert when dead-letter scans appear (`GET /api/v1/admin/dead-letter-scans`).
- [ ] Track API latency/error rates and worker throughput.
- [ ] Monitor AI request volume against `AI_DAILY_REQUEST_LIMIT` / `AI_MONTHLY_REQUEST_LIMIT`.

## 7. GitHub App

- [ ] **(required)** Point the GitHub App webhook URL at the production endpoint (`/api/v1/github/webhooks`).
- [ ] Confirm required permissions: contents (read), pull requests (write), checks (write).
- [ ] Subscribe to the pull request events the platform consumes.
- [ ] Install the App on the target organization/repositories and register them.
- [ ] Open a test PR and confirm a Check Run with the AI review is produced.

## 8. Pre-launch verification

- [ ] **(required)** Backend tests pass: `pytest backend/tests`.
- [ ] **(required)** Frontend builds cleanly: `cd frontend && npm run build`.
- [ ] Frontend lint passes: `npm run lint`.
- [ ] Smoke test: sign in, view dashboard, open a scan, view the AI review.
- [ ] End-to-end test: open a real PR and confirm scan → findings → risk → Check Run.
- [ ] (Optional) Load demo data in a demo environment: `python -m app.scripts.seed_demo_data`.

## 9. Rollback plan

- [ ] Tag/record the current release and the previous known-good release.
- [ ] Document the database migration downgrade path (or forward-fix policy).
- [ ] Verify you can redeploy the previous image/build quickly.
- [ ] Confirm backups are recent before running destructive migrations.

## 10. Post-launch

- [ ] Watch health, queue metrics, and dead-letter counts for the first hours.
- [ ] Confirm scans complete and Check Runs post on live PRs.
- [ ] Review audit logs for unexpected activity.
- [ ] Confirm AI usage and costs are within expected bounds.
