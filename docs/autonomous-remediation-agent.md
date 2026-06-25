# Autonomous Remediation Agent Design

## Purpose

The remediation agent will help teams move from detecting PR issues to proposing safe fixes. It should create small, reviewable patches for common findings while preserving human approval as the final authority.

## What It Can Fix

- Remove obvious debug logging such as `console.log`.
- Add missing validation for simple input paths.
- Update low-risk configuration or lint issues.
- Add focused tests for straightforward rule violations.
- Apply small dependency-safe code hygiene changes.

## What It Must Not Auto-fix

- Authentication, authorization, or cryptography logic without explicit human review.
- Payment, billing, financial, medical, or safety-critical behavior.
- Large architecture rewrites.
- Database migrations that alter production data semantics.
- Changes requiring unclear product decisions.
- Anything that would expose secrets, tokens, or private code in logs or comments.

## Human Approval Flow

1. CodeDNA AI detects findings during a PR scan.
2. The agent determines whether findings are eligible for remediation.
3. The agent posts a proposal summary on the PR.
4. A maintainer approves remediation.
5. The agent creates a branch and opens a fix PR or pushes to an allowed remediation branch.
6. A human reviews and merges the remediation PR.

## Branch Creation Flow

The agent should create branches using a predictable prefix:

`codedna/remediate/<scan-id-short>/<finding-slug>`

Branch creation must use the GitHub App installation token and respect repository permissions. The agent must never overwrite user branches.

## PR Comment Flow

The agent should comment with:

- Findings selected for remediation
- Files expected to change
- Risk level of the proposed fix
- Commands/tests it plans to run
- Clear approval instructions

After generating a patch, it should comment with a concise summary, test results, and links to the remediation branch or PR.

## Safety Limits

- Maximum files changed per remediation run.
- Maximum diff size per run.
- Only one active remediation branch per scan/finding group.
- No secrets in prompts, logs, comments, or branch names.
- No automatic merge.
- No remediation when tests cannot be run or the repository context is incomplete.

## Future Roadmap

- Policy-driven auto-remediation allowlists by organization.
- Repository-specific remediation playbooks.
- Sandboxed test execution for generated fixes.
- Human feedback loop to improve fix quality.
- Multi-step remediation plans for larger architectural issues.
- Approval integrations with Slack, Jira, and GitHub review states.
