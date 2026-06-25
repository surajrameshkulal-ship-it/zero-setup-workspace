# CodeDNA AI — Demo Script (5–7 minutes)

A tight, repeatable walkthrough for live demonstrations. It works for a mixed
audience — engineering leaders, developers, and investors — with audience-specific
talking points called out along the way.

## Before you start (setup, ~2 min, off-camera)

1. Ensure the stack is running: API (`:8000`), worker, frontend (`:3000`),
   PostgreSQL, and Redis. Confirm `GET /health` returns healthy.
2. Seed demo data so every view is populated:

   ```bash
   python -m app.scripts.seed_demo_data
   ```

3. Have these tabs ready:
   - Landing page: `http://localhost:3000/`
   - (Optional) A real GitHub PR with a CodeDNA Check Run, for the GitHub moment.
4. Sign-in credentials: `demo@codedna.ai` / `Demo@12345`.

> One-liner positioning (memorize this): **"CodeDNA AI reviews every pull request
> automatically — static analysis, AI review, and a risk score — and delivers the
> verdict right inside GitHub and a governance dashboard."**

---

## The walkthrough

### 1. Landing page — the "why" (~45s)

Open `http://localhost:3000/`.

- **Show:** the hero, the sample Check Run card, and the feature grid.
- **Say:** "Every pull request is a moment of risk. CodeDNA AI turns each one into
  reviewed, scored, audit-ready evidence — without changing how developers work."
- **Audience notes:**
  - *Leaders:* governance and consistency across every team and repo.
  - *Developers:* no new workflow — it meets them inside GitHub.
  - *Investors:* every PR is a recurring, automatable event — durable usage.

### 2. Dashboard — the operating view (~90s)

Click **Open the dashboard**, sign in.

- **Show:** the summary metrics (repositories, scans, completed, failed, high
  risk, average risk), then the Risk / Health / Queue cards, then Recent scans.
- **Say:** "This is the single operating view: how much was scanned, how risky it
  was, and whether the platform itself is healthy."
- **Do:** point at the **Health** card (DB, Redis, Celery) and the **Queue** card
  (pending scans, dead letters).
- **Audience notes:**
  - *Leaders:* a portfolio-level risk and throughput signal.
  - *Developers:* real operational health — idempotent webhooks, retries, a
    dead-letter queue behind the scenes.
  - *Investors:* this is production-hardened, not a prototype.

### 3. Scans list — filtering the firehose (~45s)

Go to **Scans**.

- **Show:** filter by status and risk level.
- **Say:** "Hundreds of PRs become a searchable, comparable stream. Let's open a
  high-risk one."
- **Do:** filter to **high** or **critical** risk and click into a scan.

### 4. Scan detail — the evidence (~90s)

On the scan detail page.

- **Show, in order:** status + risk badges → risk score / findings / files /
  line-delta metrics → the **AI Review** rendered from markdown → the findings
  tables (Company rules, Architecture, Semgrep, AI).
- **Say:** "This is the heart of it. A consistent risk score, then concrete
  evidence: what the secret scanner found, what the AI flagged, and which company
  and architecture rules were violated — each with a file and line."
- **Audience notes:**
  - *Leaders:* enforceable standards, audit trail, defensible decisions.
  - *Developers:* actionable, specific, with locations — not vague nags.
  - *Investors:* two engines (static + AI) compounding into one trusted signal.

### 5. The GitHub moment — where developers live (~60s)

Switch to the GitHub Check Run tab (real PR), or use the landing-page sample card
if no live PR is available.

- **Show:** the Check Run output — **Summary** verdict, **Risk**, **Findings**
  breakdown, **Company Rules**, **Architecture Notes**, and **AI Review**.
- **Say:** "Same verdict, delivered where developers already are. No context
  switch — the review is part of the PR."
- **Audience notes:**
  - *Developers:* zero friction; it's just another check.
  - *Leaders:* the policy gate lives in the merge workflow.

### 6. Rules — governance you control (~45s)

Go to **Rules**.

- **Show:** company rules and architecture rules.
- **Say:** "Governance is configurable. Define a company rule — say, no hard-coded
  secrets — and it's enforced on every PR automatically."

### 7. Close (~30s)

Return to the **Dashboard**.

- **Say:** "Every pull request, automatically reviewed, scored, and governed —
  surfaced in GitHub and in one operating view. That's CodeDNA AI."
- **Tailor the last line:**
  - *Leaders:* "Consistent engineering governance, without slowing teams down."
  - *Developers:* "Better reviews, zero extra workflow."
  - *Investors:* "An automatable check on every PR — recurring by construction."

---

## If something goes wrong

- **A view is empty:** re-run `python -m app.scripts.seed_demo_data --reset`.
- **Health card shows errors:** confirm PostgreSQL and Redis are up and the worker
  is running; refresh.
- **No live GitHub PR:** use the sample Check Run card on the landing page and
  narrate it — the format is identical to production output.
- **Login fails:** re-run the seed script (it resets the demo user's password).

## Time budget cheat sheet

| Segment | Target |
| --- | --- |
| Landing page | 0:45 |
| Dashboard | 1:30 |
| Scans list | 0:45 |
| Scan detail | 1:30 |
| GitHub Check Run | 1:00 |
| Rules | 0:45 |
| Close | 0:30 |
| **Total** | **~6:45** |
