# CodeDNA AI

CodeDNA AI is an AI Engineering Governance Platform for corporate software teams. This MVP backend reviews GitHub pull requests, runs Semgrep, applies company and architecture rules, calculates risk scores, stores audit-ready reports, and comments back on GitHub PRs.

## Stack

- Backend: FastAPI
- Frontend: Next.js + Tailwind CSS
- Database: PostgreSQL
- Background jobs: Celery + Redis
- AI review: OpenAI API
- Static analysis: Semgrep
- Auth: JWT
- Deployment: Docker Compose

## Project Structure

```text
backend/
  app/
    api/              # FastAPI routers and dependencies
    core/             # config, database, security, logging, Celery
    integrations/     # GitHub and OpenAI clients
    models/           # SQLAlchemy domain models
    schemas/          # Pydantic request/response schemas
    services/         # business logic and scan workflow
    utils/            # reusable helpers
    workers/          # Celery tasks
  alembic/            # database migrations
  tests/              # unit tests for core services
frontend/
  app/                # Next.js App Router pages
  components/         # shared dashboard UI
  hooks/              # auth and API data hooks
  lib/                # typed API client
  types/              # backend response contracts
```

## Dependency Source

Runtime and development dependencies are defined in [pyproject.toml](pyproject.toml). Docker, editable local installs, and the compatibility `backend/requirements.txt` file all install from that same project metadata.

CodeDNA AI targets Python 3.12, matching the `python:3.12-slim` Docker image.

The frontend targets Node.js 20.9 or newer and installs from `frontend/package.json` plus `frontend/package-lock.json`.

## Local Setup

From a fresh clone:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

If your workstation has multiple Python versions, make sure `python3 --version` reports Python 3.12 or newer before creating the virtual environment.

Copy the environment file:

```bash
cp .env.example .env
```

Edit `.env` and set at least:

```bash
SECRET_KEY=replace-with-a-long-random-string
GITHUB_WEBHOOK_SECRET=replace-with-your-webhook-secret
```

When running the backend directly on your host machine with Docker Compose only for PostgreSQL and Redis, use host URLs:

```bash
DATABASE_URL=postgresql+psycopg://codedna:codedna@localhost:5432/codedna
REDIS_URL=redis://localhost:6379/0
```

Set these when enabling live GitHub and AI workflows:

```bash
OPENAI_API_KEY=...
GITHUB_APP_ID=...
GITHUB_APP_SLUG=...
GITHUB_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"
```

Run PostgreSQL and Redis locally, or use Docker Compose for those services. Then run migrations from the repository root:

```bash
cd backend
alembic upgrade head
cd ..
```

Start the API:

```bash
uvicorn app.main:app --reload
```

Start the worker in another terminal:

```bash
source .venv/bin/activate
celery -A app.core.celery_app.celery_app worker --loglevel=INFO
```

Create or reset the default admin user:

```bash
python -m app.scripts.reset_admin_user
```

Default credentials:

```text
Email: admin@codedna.ai
Password: Admin@123
```

Install and run the frontend in another terminal:

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open the API:

- Health: http://localhost:8000/health
- Docs in development: http://localhost:8000/docs

Open the dashboard:

- Frontend: http://localhost:3000

## Test Execution

After `pip install -e ".[dev]"`, run tests from the repository root:

```bash
pytest backend/tests
```

Equivalent:

```bash
python -m pytest backend/tests
```

Frontend checks:

```bash
cd frontend
npm run lint
npm run build
```

## Docker Setup

Docker uses the same dependency definitions from `pyproject.toml`.

```bash
cp .env.example .env
docker compose up --build
```

Run migrations inside the backend container:

```bash
docker compose exec backend alembic upgrade head
```

Useful Docker commands:

```bash
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f frontend
docker compose exec backend pytest backend/tests
docker compose down
```

Docker services:

- Backend API: http://localhost:8000
- Frontend dashboard: http://localhost:3000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

## Development Workflow

1. Create or update backend code under `backend/app`.
2. Create or update frontend code under `frontend/app`, `frontend/components`, and `frontend/lib`.
3. Add or update backend tests under `backend/tests`.
4. Run `pytest backend/tests` from the repository root.
5. Run `npm run lint` and `npm run build` from `frontend/`.
6. Run `alembic revision --autogenerate -m "message"` from `backend/` for schema changes.
7. Run `alembic upgrade head` before manually testing API paths.
8. Use Docker Compose when you need the full PostgreSQL, Redis, backend, worker, and frontend stack.

## Main Workflow

1. Company admin signs up with `POST /api/v1/auth/signup`.
2. Admin installs the GitHub App using `GET /api/v1/github/install-url`.
3. Admin registers the installation with `POST /api/v1/github/installations`.
4. Admin connects a repository with `POST /api/v1/repositories`.
5. GitHub sends PR events to `POST /api/v1/github/webhooks`.
6. The webhook handler verifies `X-Hub-Signature-256`, creates a queued scan, and enqueues Celery.
7. The worker fetches changed files from GitHub.
8. Semgrep scans current changed file contents.
9. OpenAI reviews code changes when `OPENAI_API_KEY` is configured.
10. Company rules and architecture rules are evaluated.
11. Risk score and report are saved.
12. CodeDNA AI posts a PR comment through the GitHub App.
13. Dashboard data is available at `GET /api/v1/dashboard`.
14. Scan results are available at `GET /api/v1/scans`, `GET /api/v1/scans/{scan_id}`, and `GET /api/v1/repositories/{repository_id}/scans`.
15. The dashboard UI shows repositories, scan history, scan details, and rules.

## Example API Calls

Signup:

```bash
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "organization_name": "Acme Engineering",
    "organization_slug": "acme-engineering",
    "full_name": "Ada Lovelace",
    "email": "ada@example.com",
    "password": "replace-with-a-long-password"
  }'
```

Register a GitHub installation:

```bash
curl -X POST http://localhost:8000/api/v1/github/installations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "installation_id": 123456,
    "account_login": "acme",
    "account_type": "Organization",
    "permissions": {"contents": "read", "pull_requests": "write"}
  }'
```

Connect a repository:

```bash
curl -X POST http://localhost:8000/api/v1/repositories \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "installation_id": 123456,
    "github_repository_id": 987654321,
    "owner": "acme",
    "name": "payments-api",
    "default_branch": "main"
  }'
```

Add a company rule:

```bash
curl -X POST http://localhost:8000/api/v1/rules/company \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "No debug logs",
    "description": "Debug logging must not be merged into production services.",
    "rule_type": "forbidden_text",
    "pattern": "console.log",
    "severity": "medium"
  }'
```

Add an architecture rule:

```bash
curl -X POST http://localhost:8000/api/v1/rules/architecture \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "API layer cannot import models directly",
    "description": "API handlers must go through service-layer boundaries.",
    "source_path_pattern": "backend/app/api/**/*.py",
    "forbidden_import_pattern": "app\\.models",
    "severity": "high"
  }'
```

## Security Notes

- Passwords are hashed with bcrypt through Passlib.
- JWT access tokens are signed with `SECRET_KEY`.
- GitHub webhooks are verified with HMAC SHA-256.
- GitHub App private keys and OpenAI keys are read only from environment variables.
- All organization-scoped APIs enforce tenant isolation through the current JWT user.
- Audit logs capture administrative and workflow events.
