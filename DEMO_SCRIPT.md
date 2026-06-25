# CodeDNA AI — 5-Minute Demo Script

A tight, repeatable 5-minute walkthrough for a mixed audience (engineering
leaders, developers, investors). Stay on the path; skip side-trips.

## Setup (before you present, off-camera)

1. Stack running: API (`:8000`), worker, frontend (`:3000`), Postgres, Redis.
   Confirm `GET /health` returns 200.
2. Seed demo data so every view is populated:
   `python -m app.scripts.seed_demo_data`
3. Tabs ready: landing page `http://localhost:3000/`; (optional) a real GitHub
   PR showing a CodeDNA Check Run.
4. Credentials: `demo@codedna.ai` / `Demo@12345`.

> One-liner: **"CodeDNA AI reviews every pull request automatically — static
> analysis, AI review, and a risk score — delivered right inside GitHub and a
> governance dashboard."**

---

## Walkthrough (~5:00)

### 1. Landing page — the "why" (0:30)

Open `/`. Show the hero, the sample Check Run card, the feature grid.

- Say: "Every pull request is a moment of risk. CodeDNA AI turns each one into
  reviewed, scored, audit-ready evidence — without changing how developers work."

### 2. Dashboard — the operating view (1:00)

Click **Open the dashboard**, sign in.

- Show: summary metrics, then the Risk / Health / Queue cards, then Recent scans.
- Say: "One operating view: how much was scanned, how risky it was, and whether
  the platform itself is healthy — idempotent webhooks, retries, a dead-letter
  queue behind the scenes."
- Audience: *leaders* → portfolio risk + throughput; *developers* → real ops
  health; *investors* → production-hardened, not a prototype.

### 3. Scan detail — the evidence (1:30)

Go to **Scans**, filter to **high** risk, open one.

- Show, in order: status + risk badges → risk score / findings / files metrics →
  the **AI Review** → the findings tables (Company rules, Architecture, Semgrep,
  AI).
- Say: "The heart of it. A consistent risk score, then concrete evidence — what
  the scanner found, what the AI flagged, and which company and architecture
  rules were violated, each with a file and line."
- Audience: *leaders* → enforceable standards + audit trail; *developers* →
  specific and actionable; *investors* → two engines compounding into one signal.

### 4. The GitHub moment (1:00)

Switch to the GitHub Check Run tab (or the landing-page sample card).

- Show: the Check Run — Summary verdict, Risk, Findings, Company Rules,
  Architecture Notes, AI Review.
- Say: "Same verdict, delivered where developers already are. No context switch —
  the review is just part of the pull request."

### 5. Close (1:00)

Return to the **Dashboard**.

- Say: "Every pull request, automatically reviewed, scored, and governed —
  in GitHub and in one operating view. That's CodeDNA AI."
- Tailor the last line:
  - *Leaders:* "Consistent governance without slowing teams down."
  - *Developers:* "Better reviews, zero extra workflow."
  - *Investors:* "An automatable check on every PR — recurring by construction."

---

## If something breaks

- Empty views → `python -m app.scripts.seed_demo_data --reset`.
- Health card errors → confirm Postgres/Redis up and the worker running; refresh.
- No live PR → narrate the landing-page sample card (format is identical to prod).
- Login fails → re-run the seed script (it resets the demo password).

## Time budget

| Segment | Target |
| --- | --- |
| Landing page | 0:30 |
| Dashboard | 1:00 |
| Scan detail | 1:30 |
| GitHub Check Run | 1:00 |
| Close | 1:00 |
| **Total** | **~5:00** |
