"""Product Brain (Phase 12 — CodeDNA Brain, first agent).

A read-only product-intelligence agent. It synthesizes a single situational
overview from the roadmap document and the real delivery data in the database:

  * knows the roadmap (parsed from docs/*roadmap*.md)
  * tracks delivery state (engineering requests, scans, workspaces, repos)
  * identifies blockers (failed/rejected work, crashed sandboxes, risky code)
  * recommends priorities (ranked, with rationale)

It is deterministic and side-effect free: it never changes code, opens PRs, or
mutates any record — it only reads and reports, so a human stays in control.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.engineering_request import EngineeringRequest, RequestStatus
from app.models.repository import Repository
from app.models.scan import PullRequestScan, RiskLevel
from app.models.workspace_instance import WorkspaceInstance

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}

# Phase parsing is tolerant of the common ways roadmaps are written. A line is
# only treated as a phase if it is a markdown heading/bullet (so prose like
# "Phase 11 delivers ..." is not mistaken for a phase), or — for backward
# compatibility — a plain paragraph in the strict "Phase N — Title" form.
_HEADING_RE = re.compile(r"^\s*(?:#{1,6}\s+|[-*]\s+)(.*)$")
# Optional "Phase" keyword; separator after the id is optional (handles
# "Phase 11.1 — Title", "Phase 11.1: Title", and "Phase 11.1 Title").
_KEYWORD_RE = re.compile(r"^(?:phase\s+)?(\d+(?:\.\d+)*)\b[\s.:)\]—\-–]*\s*(.*)$", re.IGNORECASE)
# Bare versioned heading without the word "Phase" (requires a dot so section
# numbers like "## 6. Phases" are not captured): "## 11.1 — Title".
_VERSION_RE = re.compile(r"^(\d+\.\d+(?:\.\d+)*)\b[\s.:)\]—\-–]*\s*(.*)$")
# Backward-compatible strict form for non-heading prose lines.
_PROSE_RE = re.compile(r"(?i)\bphase\s+(\d+(?:\.\d+)*)\s*[—\-–:]\s*(.+)")


def _parse_phase_line(raw: str) -> tuple[str, str] | None:
    """Return (phase_id, rest) if a line describes a roadmap phase, else None."""
    heading = _HEADING_RE.match(raw)
    if heading:
        body = heading.group(1).strip().strip("*").strip("`").strip()
        # Prefer the explicit "Phase N" form; fall back to a bare dotted version.
        km = _KEYWORD_RE.match(body)
        if km and (body[:1].lower() == "p" or "." in km.group(1)):
            return km.group(1), km.group(2)
        vm = _VERSION_RE.match(body)
        if vm:
            return vm.group(1), vm.group(2)
        return None
    prose = _PROSE_RE.search(raw)
    if prose:
        return prose.group(1), prose.group(2)
    return None


class ProductBrain:
    def __init__(self, db: Session, *, docs_root: Path | str | None = None) -> None:
        self.db = db
        # An explicit docs_root is authoritative (used by tests). Otherwise search
        # several candidate locations so the roadmap is found across repo layouts.
        if docs_root is not None:
            self._roots = [Path(docs_root)]
        else:
            self._roots = self._candidate_docs_roots()
        # Kept for backward compatibility / introspection.
        self.docs_root = self._roots[0] if self._roots else None

    # -- public ----------------------------------------------------------------

    def overview(self, organization_id: uuid.UUID) -> dict:
        roadmap = self.roadmap()
        delivery = self._delivery(organization_id)
        blockers = self._blockers(organization_id)
        priorities = self._priorities(organization_id, blockers, delivery)
        return {
            "roadmap": roadmap,
            "delivery": delivery,
            "blockers": blockers,
            "priorities": priorities,
            "summary": self._summary(delivery, blockers, priorities),
        }

    def roadmap(self) -> list[dict]:
        """Parse roadmap phases from docs/*roadmap*.md (best-effort, tolerant)."""
        phases: list[dict] = []
        seen: set[str] = set()
        for path in self._roadmap_files():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for raw in text.splitlines():
                parsed = _parse_phase_line(raw)
                if not parsed:
                    continue
                phase_id, rest = parsed
                rest = rest.strip().lstrip("*").strip()
                # Split "Title. description" on the first sentence boundary.
                title, _, summary = rest.partition(".")
                key = f"{phase_id}:{title.strip().lower()}"
                if key in seen:
                    continue
                seen.add(key)
                phases.append(
                    {"id": phase_id, "title": title.strip().strip("*"), "summary": summary.strip().strip("*")}
                )
        phases.sort(key=lambda p: [int(x) for x in p["id"].split(".") if x.isdigit()])
        return phases

    # -- delivery state --------------------------------------------------------

    def _delivery(self, organization_id: uuid.UUID) -> dict:
        request_counts = self._count_by(
            EngineeringRequest, EngineeringRequest.status, organization_id, value_attr="value"
        )
        workspace_counts = self._count_by(WorkspaceInstance, WorkspaceInstance.status, organization_id)
        repositories = self.db.scalar(
            select(func.count()).select_from(Repository).where(Repository.organization_id == organization_id)
        )
        total_scans = self.db.scalar(
            select(func.count()).select_from(PullRequestScan).where(PullRequestScan.organization_id == organization_id)
        )
        high_risk = self.db.scalar(
            select(func.count())
            .select_from(PullRequestScan)
            .where(
                PullRequestScan.organization_id == organization_id,
                PullRequestScan.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]),
            )
        )
        return {
            "repositories": int(repositories or 0),
            "engineering_requests": request_counts,
            "engineering_requests_total": sum(request_counts.values()),
            "workspaces": workspace_counts,
            "scans_total": int(total_scans or 0),
            "high_risk_scans": int(high_risk or 0),
        }

    # -- blockers --------------------------------------------------------------

    def _blockers(self, organization_id: uuid.UUID) -> list[dict]:
        blockers: list[dict] = []

        failed_or_rejected = self.db.scalars(
            select(EngineeringRequest).where(
                EngineeringRequest.organization_id == organization_id,
                EngineeringRequest.status.in_([RequestStatus.FAILED, RequestStatus.REJECTED]),
            )
        )
        for req in failed_or_rejected:
            blockers.append(
                {
                    "type": "engineering_request",
                    "severity": "high" if req.status == RequestStatus.FAILED else "medium",
                    "title": req.title,
                    "reason": f"Engineering request is {req.status.value}.",
                    "reference_id": str(req.id),
                }
            )

        crashed = self.db.scalars(
            select(WorkspaceInstance).where(
                WorkspaceInstance.organization_id == organization_id,
                WorkspaceInstance.status.in_(["failed", "crashed"]),
            )
        )
        for ws in crashed:
            blockers.append(
                {
                    "type": "workspace",
                    "severity": "high" if ws.status == "crashed" else "medium",
                    "title": f"Sandbox {ws.status}: {ws.repository_full_name or ws.repository_id}",
                    "reason": ws.error_message or f"Workspace instance {ws.status}.",
                    "reference_id": str(ws.id),
                }
            )

        risky = self.db.scalars(
            select(PullRequestScan).where(
                PullRequestScan.organization_id == organization_id,
                PullRequestScan.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]),
            )
        )
        for scan in risky:
            blockers.append(
                {
                    "type": "scan",
                    "severity": "critical" if scan.risk_level == RiskLevel.CRITICAL else "high",
                    "title": scan.title or f"PR #{scan.github_pr_number}",
                    "reason": f"Scan flagged {scan.risk_level.value} risk.",
                    "reference_id": str(scan.id),
                }
            )

        blockers.sort(key=lambda b: _SEVERITY_ORDER.get(b["severity"], 0), reverse=True)
        return blockers

    # -- priorities ------------------------------------------------------------

    def _priorities(self, organization_id: uuid.UUID, blockers: list[dict], delivery: dict) -> list[dict]:
        reqs = delivery["engineering_requests"]
        priorities: list[dict] = []

        if blockers:
            crit = sum(1 for b in blockers if b["severity"] in ("critical", "high"))
            priorities.append(
                {
                    "title": f"Clear {len(blockers)} blocker(s)",
                    "rationale": f"{crit} are high/critical severity and gate forward progress.",
                    "category": "blockers",
                    "score": 100 + crit * 10,
                }
            )

        approved = reqs.get("approved", 0)
        if approved:
            priorities.append(
                {
                    "title": f"Execute {approved} approved engineering request(s)",
                    "rationale": "Plans are approved and ready to generate, validate, and open as draft PRs.",
                    "category": "execute",
                    "score": 80 + approved,
                }
            )

        plan_ready = reqs.get("plan_ready", 0)
        if plan_ready:
            priorities.append(
                {
                    "title": f"Review {plan_ready} plan(s) awaiting approval",
                    "rationale": "Analysis is complete; human approval unblocks execution.",
                    "category": "review",
                    "score": 70 + plan_ready,
                }
            )

        submitted = reqs.get("submitted", 0)
        if submitted:
            priorities.append(
                {
                    "title": f"Analyze {submitted} new request(s)",
                    "rationale": "New requests need an AI plan before they can progress.",
                    "category": "analyze",
                    "score": 50 + submitted,
                }
            )

        if not priorities:
            priorities.append(
                {
                    "title": "Intake new engineering work",
                    "rationale": "No blockers or in-flight work; capacity is available for the next roadmap item.",
                    "category": "idle",
                    "score": 10,
                }
            )

        priorities.sort(key=lambda p: p["score"], reverse=True)
        return priorities

    # -- summary ---------------------------------------------------------------

    @staticmethod
    def _summary(delivery: dict, blockers: list[dict], priorities: list[dict]) -> str:
        parts = [
            f"Tracking {delivery['repositories']} repository(ies) and "
            f"{delivery['engineering_requests_total']} engineering request(s)."
        ]
        if blockers:
            parts.append(f"{len(blockers)} blocker(s) need attention.")
        else:
            parts.append("No blockers detected.")
        if priorities:
            parts.append(f"Top priority: {priorities[0]['title']}.")
        return " ".join(parts)

    # -- helpers ---------------------------------------------------------------

    def _count_by(self, model, column, organization_id: uuid.UUID, *, value_attr: str | None = None) -> dict[str, int]:
        rows = self.db.execute(
            select(column, func.count())
            .where(model.organization_id == organization_id)
            .group_by(column)
        ).all()
        counts: dict[str, int] = {}
        for value, count in rows:
            key = getattr(value, value_attr) if (value_attr and value is not None) else value
            counts[str(key)] = int(count)
        return counts

    def _roadmap_files(self) -> list[Path]:
        files: dict[str, Path] = {}
        for root in self._roots:
            if not root or not root.exists():
                continue
            for path in sorted(root.glob("*roadmap*.md")):
                files.setdefault(path.name, path)  # dedupe by filename across roots
        return list(files.values())

    @staticmethod
    def _candidate_docs_roots() -> list[Path]:
        """Likely locations of a docs/ directory across repo layouts."""
        here = Path(__file__).resolve()
        candidates = [
            here.parents[4] / "docs",  # <repo>/docs (backend/app/services/brain/..)
            here.parents[3] / "docs",  # <repo>/backend/docs (alt layout)
            Path.cwd() / "docs",
            Path.cwd().parent / "docs",
        ]
        seen: set[Path] = set()
        roots: list[Path] = []
        for c in candidates:
            rc = c.resolve()
            if rc not in seen:
                seen.add(rc)
                roots.append(rc)
        return roots
