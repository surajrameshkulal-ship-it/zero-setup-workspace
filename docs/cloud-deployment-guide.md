# CodeDNA AI — Cloud Deployment Guide (Railway / Render)

This guide deploys the **full** CodeDNA AI application — FastAPI API, Celery
worker, PostgreSQL, Redis, and the Next.js frontend — to a managed cloud
platform. CodeDNA AI is not a static site; GitHub Pages or any static host
cannot run it, because it needs a database, a queue, a background worker, and
authenticated webhook processing.

It covers, in order:

1. Architecture and what gets deployed
2. Deploying on Railway
3. Deploying on Render
4. Production Docker Compose review (single-VM alternative)
5. Production environment variables checklist
6. GitHub App production callback / webhook URL checklist
7. Database migration steps
8. Redis / Celery worker deployment steps
9. Frontend `NEXT_PUBLIC_API_URL` production setup
10. Final launch checklist

Companion files in the repo: `docker-compose.prod.yml`, `.env.production.example`,
and `docs/production-deployment-checklist.md` (the generic hardening checklist).

---

## 1. Architecture and what gets deployed

You will run **five** logical components:

| Component | What it is | How it runs |
| --- | --- | --- |
| API | FastAPI app | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Worker | Celery worker | `celery -A app.core.celery_app.celery_app worker --loglevel=INFO` |
| PostgreSQL | Primary database | Managed service (recommended) |
| Redis | Celery broker + result backend | Managed service (recommended) |
| Frontend | Next.js (standalone) | `node server.js` (runner image) |

The API and the worker share the **same Docker image** (`backend/Dockerfile`),
just with different start commands. The frontend is a separate image
(`frontend/Dockerfile`, `runner` target). Both Postgres and Redis should be
managed add-ons in the cloud rather than containers you operate.

---

## 2. Deploying on Railway

Railway models each component as a "service" inside one project.

1. **Create the project and data stores.**
   - New Project → add **PostgreSQL** and **Redis** plugins. Railway provisions
     them and exposes connection variables.
2. **Backend (API) service.**
   - New Service → Deploy from your GitHub repo.
   - Settings → Build: use the Dockerfile at `backend/Dockerfile` (set the
     Docker build context to the repo root so `pyproject.toml` is available).
   - Settings → Deploy → Start Command:
     `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
     (Railway injects `$PORT`; bind to it.)
   - Add the environment variables from section 5. For `DATABASE_URL`, reference
     the Postgres plugin's value but ensure the scheme is
     `postgresql+psycopg://...` (rewrite `postgres://` → `postgresql+psycopg://`).
     For `REDIS_URL`, reference the Redis plugin's URL.
   - Add a health check path: `/health`.
3. **Worker service.**
   - New Service from the same repo / same `backend/Dockerfile`.
   - Start Command:
     `celery -A app.core.celery_app.celery_app worker --loglevel=INFO --concurrency=2`
   - Give it the **same** environment variables as the API (it needs DB, Redis,
     GitHub, and AI settings). No public port and no health path.
4. **Frontend service.**
   - New Service from the repo using `frontend/Dockerfile`, target `runner`.
   - Add a **build argument** `NEXT_PUBLIC_API_URL` = your API's public URL +
     `/api/v1` (see section 9). This must be a build arg, not just a runtime var.
   - Start Command (from the runner image): `node server.js`. Expose port 3000
     (or bind `$PORT` if Railway requires it).
5. **Run migrations** (section 7) once the database is reachable.
6. **Wire the GitHub App URLs** (section 6) to the API's public domain.

> Tip: set `ALLOWED_ORIGINS` on the API to the frontend's public URL, and set
> the frontend's `NEXT_PUBLIC_API_URL` to the API's public URL. These two must
> point at each other.

---

## 3. Deploying on Render

Render models components as "Web Services", "Background Workers", and managed
"PostgreSQL"/"Key Value (Redis)" instances.

1. **Create data stores.**
   - New → PostgreSQL. Copy its Internal Connection String.
   - New → Key Value (Redis). Copy its Internal URL.
2. **Backend (API) — Web Service.**
   - New → Web Service → from your repo → Runtime: Docker → Dockerfile path
     `backend/Dockerfile`, Docker context `.` (repo root).
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
   - Health Check Path: `/health`.
   - Add the environment variables from section 5 (set `DATABASE_URL` to the
     Postgres string rewritten to `postgresql+psycopg://...`, `REDIS_URL` to the
     Redis internal URL).
3. **Worker — Background Worker.**
   - New → Background Worker → same repo and `backend/Dockerfile`.
   - Start Command:
     `celery -A app.core.celery_app.celery_app worker --loglevel=INFO --concurrency=2`.
   - Copy the same environment variables as the API.
4. **Frontend — Web Service.**
   - New → Web Service → Docker → `frontend/Dockerfile`, target `runner`.
   - Add **Build Argument** `NEXT_PUBLIC_API_URL` = `https://<api-domain>/api/v1`.
   - Health Check Path: `/`.
5. **Migrations:** use a one-off Job or the service Shell to run
   `alembic upgrade head` (section 7).
6. **GitHub App URLs:** point them at the API web service domain (section 6).

> Render rebuilds the frontend when you change the build argument, because
> `NEXT_PUBLIC_API_URL` is compiled into the bundle.

---

## 4. Production Docker Compose review (single-VM alternative)

If you deploy to a plain VM instead of Railway/Render, use the provided
`docker-compose.prod.yml`. Key differences from the development
`docker-compose.yml` (which must **not** be used in production):

| Concern | Dev compose | Prod compose (`docker-compose.prod.yml`) |
| --- | --- | --- |
| API command | `uvicorn ... --reload` | `uvicorn ...` (no reload) |
| Source code | bind-mounted `./backend` | baked into the image (immutable) |
| Frontend | `dev` target (`next dev`) | `runner` target (`next start`, standalone) |
| Restarts | none | `restart: unless-stopped` |
| Secrets | `.env` | `.env.production` (never committed) |
| Postgres/Redis ports | published to host | not published |
| Redis persistence | none | append-only file + volume |
| Frontend API URL | runtime env | **build arg** `NEXT_PUBLIC_API_URL` |

Run it:

```bash
cp .env.production.example .env.production     # fill in real values
export NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api/v1
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head
docker compose -f docker-compose.prod.yml up -d
```

Put a TLS-terminating reverse proxy (Caddy, nginx, or the platform's load
balancer) in front of ports 8000 (API) and 3000 (frontend). Even on a VM,
consider a managed Postgres for backups and failover.

---

## 5. Production environment variables checklist

Set these on **both** the API and the worker (they share configuration). The
frontend needs only `NEXT_PUBLIC_API_URL` (at build time). Full template:
`.env.production.example`.

Required:

- [ ] `SECRET_KEY` — long random string (>= 16 chars).
- [ ] `ENVIRONMENT=production` and `DEBUG=false`.
- [ ] `DATABASE_URL` — `postgresql+psycopg://USER:PASS@HOST:5432/DB`.
- [ ] `REDIS_URL` — e.g. `rediss://default:PASS@HOST:6379/0`.
- [ ] `ALLOWED_ORIGINS` — exact frontend origin(s), comma-separated, no `*`.
- [ ] `GITHUB_WEBHOOK_SECRET` — matches the GitHub App webhook secret.

Required for live GitHub scanning:

- [ ] `GITHUB_APP_ID`, `GITHUB_APP_SLUG`, `GITHUB_PRIVATE_KEY` (PEM with `\n`
      escapes on one line).

Required for AI review (unless `AI_REVIEW_ENABLED=false`):

- [ ] `AI_PROVIDER` (`groq` recommended) and the matching key/model:
      `GROQ_API_KEY` + `GROQ_MODEL`, or `OPENAI_API_KEY` + `OPENAI_MODEL`.
- [ ] `AI_DAILY_REQUEST_LIMIT` / `AI_MONTHLY_REQUEST_LIMIT` (cost guardrails).

Frontend (build-time):

- [ ] `NEXT_PUBLIC_API_URL` — `https://<api-domain>/api/v1`.

Common gotchas:

- `DATABASE_URL` must use the `postgresql+psycopg` scheme. Platform-provided
  `postgres://...` strings will fail — rewrite the scheme.
- `ALLOWED_ORIGINS` is parsed as a comma-separated list; a trailing slash or a
  scheme mismatch (`http` vs `https`) breaks CORS.
- `GITHUB_PRIVATE_KEY` newlines: store with literal `\n`; the app converts them.

---

## 6. GitHub App production callback / webhook URL checklist

In the GitHub App settings (GitHub → Settings → Developer settings → GitHub Apps
→ your app), update for production:

- [ ] **Webhook URL** → `https://<api-domain>/api/v1/github/webhooks`.
- [ ] **Webhook secret** → matches `GITHUB_WEBHOOK_SECRET` exactly.
- [ ] **Webhook active** → enabled, with SSL verification on.
- [ ] **Callback / setup URL** (if used for install flow) → a public URL on your
      API or frontend domain (e.g. `https://<frontend-domain>/`). Confirm it
      matches what `GET /api/v1/github/install-url` expects.
- [ ] **Permissions** → Contents: Read, Pull requests: Read & write,
      Checks: Read & write.
- [ ] **Subscribe to events** → Pull request (and any events the platform
      consumes).
- [ ] After saving, **reinstall or update** the App on the target org so the new
      permissions take effect.
- [ ] Send a test delivery from the App's "Advanced" → Recent Deliveries and
      confirm a `2xx` response from the API.

---

## 7. Database migration steps

Migrations are managed by Alembic and run from the backend working directory.
They must run once before first use and after every deploy that includes schema
changes. They are safe to run repeatedly (no-op when already current).

Railway / Render (one-off shell or job on the API service):

```bash
alembic upgrade head
```

Docker Compose (single VM):

```bash
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head
```

Notes:

- Run migrations **before** routing production traffic.
- Take a database backup before running migrations that alter existing tables.
- Create the demo data set only in non-production/demo environments:
  `python -m app.scripts.seed_demo_data`.
- Create or reset an admin user (then change the password):
  `python -m app.scripts.reset_admin_user`.

---

## 8. Redis / Celery worker deployment steps

- [ ] Provision **managed Redis** and set `REDIS_URL` (with auth/TLS — use the
      `rediss://` scheme when TLS is offered). Redis is both the Celery broker
      and the result backend.
- [ ] Deploy the worker as a **separate** long-running process from the API,
      using the same image and environment:
      `celery -A app.core.celery_app.celery_app worker --loglevel=INFO --concurrency=2`.
- [ ] Ensure the worker has the same `DATABASE_URL`, `REDIS_URL`, GitHub, and AI
      variables as the API — it does the actual scanning.
- [ ] Scale workers horizontally by running more worker instances (each connects
      to the same Redis). Tune `--concurrency` to the instance's CPU.
- [ ] Confirm processing end to end: open a PR and watch the scan move
      `queued → running → completed`.
- [ ] Monitor queue depth and dead letters via
      `GET /api/v1/admin/queue-metrics` and `GET /api/v1/admin/dead-letter-scans`.
- [ ] (Optional) Run a Celery beat / monitoring sidecar if you add scheduled
      tasks later; not required for the current workflow.

---

## 9. Frontend `NEXT_PUBLIC_API_URL` production setup

`NEXT_PUBLIC_API_URL` is read in `frontend/lib/api.ts` and, like all
`NEXT_PUBLIC_*` variables, is **inlined into the JavaScript bundle at build
time**. Setting it only at runtime has no effect — the value baked in at build
is what ships.

- [ ] Set it to your API's public base URL **including** `/api/v1`, e.g.
      `https://api.yourdomain.com/api/v1`.
- [ ] Provide it as a **build argument** to the frontend image. The
      `frontend/Dockerfile` `builder` stage accepts
      `ARG NEXT_PUBLIC_API_URL` for this purpose.
  - Railway/Render: add it under the frontend service's **Build Arguments**.
  - Docker Compose: `docker-compose.prod.yml` passes
    `args.NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL}` — export the value before
    `docker compose build`.
- [ ] If you change the API domain later, **rebuild** the frontend image — a
      restart alone will not pick up the new URL.
- [ ] Make sure the API's `ALLOWED_ORIGINS` includes the frontend's public
      origin, or browser requests will be blocked by CORS.

Quick check after deploy: open the frontend, sign in, and confirm the dashboard
loads data (network calls should target your API domain, not `localhost`).

---

## 10. Final launch checklist

Pre-flight:

- [ ] Managed Postgres and Redis provisioned; `DATABASE_URL` (psycopg scheme)
      and `REDIS_URL` set on API and worker.
- [ ] `SECRET_KEY`, `GITHUB_WEBHOOK_SECRET`, GitHub App, and AI provider vars set.
- [ ] `ALLOWED_ORIGINS` = frontend origin; `NEXT_PUBLIC_API_URL` = API origin +
      `/api/v1` (passed as a build arg).
- [ ] `alembic upgrade head` run successfully.
- [ ] API `/health` and `/api/v1/health` return 200.
- [ ] Worker is running and connected to Redis.
- [ ] TLS enabled on API and frontend; HTTP redirects to HTTPS.
- [ ] Default admin password rotated; demo seed data NOT loaded in production.
- [ ] GitHub App webhook URL/secret/permissions updated and a test delivery
      returns 2xx.

Smoke test:

- [ ] Sign in on the production frontend; dashboard renders real data.
- [ ] Open a real pull request → scan runs → Check Run with the AI review appears
      → scan shows in the dashboard.

Post-launch:

- [ ] Watch `/api/v1/admin/queue-metrics` and dead-letter count for the first
      hours.
- [ ] Confirm logs are shipping and `LOG_LEVEL` is appropriate.
- [ ] Verify AI usage/cost stays within the configured limits.
- [ ] Confirm database backups are configured and a restore has been tested.
