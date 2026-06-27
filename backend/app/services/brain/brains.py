"""The specialized brains consulted by the Super Brain.

Each brain is a read-only, evidence-producing reasoner over data CodeDNA already
owns. They share a small contract: can_handle(task) -> relevance score,
build_context(task) -> dict, reason(task, context) -> BrainResult (summary,
confidence, evidence, suggested_actions).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.engineering_request import EngineeringRequest, RequestStatus
from app.models.scan import PullRequestScan, RiskLevel
from app.models.validation_run import ValidationRun
from app.models.workspace_instance import WorkspaceInstance
from app.services.brain.knowledge_retrieval import KnowledgeRetrievalService
from app.services.brain.memory_service import BrainMemoryService
from app.services.brain.product_brain import ProductBrain as ProductBrainService
from app.services.brain.types import BrainResult, action, evidence


class BaseBrain:
    name: str = "base"
    keywords: tuple[str, ...] = ()

    def can_handle(self, task: str) -> float:
        if not self.keywords:
            return 0.0
        low = task.lower()
        matches = sum(1 for k in self.keywords if k in low)
        return min(1.0, matches / max(1, len(self.keywords)) * 3)

    def build_context(self, task: str, db: Session, organization_id: uuid.UUID) -> dict:  # noqa: ARG002
        return {}

    def reason(self, task: str, context: dict, db: Session, organization_id: uuid.UUID) -> BrainResult:
        raise NotImplementedError

    @staticmethod
    def _counts_by_status(db: Session, organization_id: uuid.UUID) -> dict[str, int]:
        rows = db.execute(
            select(EngineeringRequest.status, func.count())
            .where(EngineeringRequest.organization_id == organization_id)
            .group_by(EngineeringRequest.status)
        ).all()
        return {status.value: int(count) for status, count in rows}


class ProductBrain(BaseBrain):
    name = "product"
    keywords = ("roadmap", "phase", "priority", "status", "progress", "blocker", "ship", "product", "next")

    def reason(self, task, context, db, organization_id) -> BrainResult:
        overview = ProductBrainService(db).overview(organization_id)
        ev = []
        for b in overview["blockers"][:3]:
            ev.append(evidence("blocker", f"{b['title']} — {b['reason']}", b.get("reference_id")))
        for p in overview["priorities"][:3]:
            ev.append(evidence("priority", f"{p['title']} — {p['rationale']}", None))
        actions = [action(p["title"], p["rationale"], self.name) for p in overview["priorities"][:3]]
        confidence = 0.8 if (overview["blockers"] or overview["delivery"]["engineering_requests_total"]) else 0.5
        return BrainResult(self.name, confidence, overview["summary"], ev, actions)


class EngineeringBrain(BaseBrain):
    name = "engineering"
    keywords = (
        "code", "implement", "feature", "refactor", "engineering", "request", "plan", "pr", "pull request",
        "impacted", "impact", "affected", "files", "build", "module", "modules", "service", "services",
        "depend", "depends", "dependency", "architecture",
    )

    def reason(self, task, context, db, organization_id) -> BrainResult:
        from app.services.brain.engineering_intelligence import EngineeringIntelligenceService

        intel = EngineeringIntelligenceService(db)
        counts = self._counts_by_status(db, organization_id)
        total = sum(counts.values())
        ev = [evidence("engineering_requests", f"{v} request(s) in '{k}'", None) for k, v in sorted(counts.items())]
        actions = []
        if counts.get("submitted"):
            actions.append(action(f"Analyze {counts['submitted']} new request(s)", "They need an AI plan to progress.", self.name))
        if counts.get("plan_ready"):
            actions.append(action(f"Approve {counts['plan_ready']} ready plan(s)", "Approval unblocks execution.", self.name))
        if counts.get("approved"):
            actions.append(action(f"Execute {counts['approved']} approved request(s)", "Generate, validate, and open draft PRs.", self.name))

        # Graph-aware engineering intelligence: architecture overview + impact.
        overview = intel.overview(organization_id)
        for dep in overview["top_dependencies"][:3]:
            ev.append(evidence("dependency", f"{dep['title']} has {dep['dependents']} dependent(s)", dep["id"]))
        impact_note = ""
        impact = intel.impact(organization_id, task)
        if impact["matches"]:
            artifacts = sum(len(v) for v in impact["affected_by_type"].values())
            impact_note = f" Impact for this query: {len(impact['matches'])} component(s) matched, {artifacts} artifact(s) likely affected."
            for entry in impact["impacted"][:4]:
                ev.append(evidence("impact", f"{entry['title']} (via {entry['via']})", entry["id"]))
            if impact["impacted"]:
                actions.append(action("Review impacted components before changing", "These components are connected to your query in the Engineering Graph.", self.name))

        review = intel.architecture_review(organization_id)
        if review["flags"]:
            top = review["flags"][0]
            ev.append(evidence("architecture", top["title"], None))

        summary = (
            (f"{total} engineering request(s): " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) if total else "No engineering requests yet.")
            + f" {overview['summary']}"
            + impact_note
        )
        confidence = 0.8 if (total or overview["total_components"]) else 0.4
        return BrainResult(self.name, confidence, summary, ev, actions)


class DebugBrain(BaseBrain):
    name = "debug"
    keywords = ("error", "fail", "failure", "bug", "crash", "root cause", "broken", "why", "exception", "logs", "debug")

    def reason(self, task, context, db, organization_id) -> BrainResult:
        ev: list[dict] = []
        failed_reqs = db.scalars(
            select(EngineeringRequest).where(
                EngineeringRequest.organization_id == organization_id,
                EngineeringRequest.status == RequestStatus.FAILED,
            )
        ).all()
        for r in failed_reqs[:5]:
            ev.append(evidence("engineering_request", f"Failed: {r.title}", str(r.id)))
        failed_val = db.scalars(
            select(ValidationRun).where(
                ValidationRun.organization_id == organization_id, ValidationRun.status == "failed"
            )
        ).all()
        for v in failed_val[:5]:
            failed_checks = [c.get("name") for c in (v.checks or []) if c.get("status") == "failed"]
            ev.append(evidence("validation", f"Validation failed: {', '.join(failed_checks) or 'see report'}", str(v.id)))
        crashed = db.scalars(
            select(WorkspaceInstance).where(
                WorkspaceInstance.organization_id == organization_id,
                WorkspaceInstance.status.in_(["failed", "crashed"]),
            )
        ).all()
        for w in crashed[:5]:
            ev.append(evidence("workspace", w.error_message or f"Sandbox {w.status}", str(w.id)))

        # Debug Intelligence: most recent diagnoses with root cause + fix.
        from app.models.debug import DebugDiagnosis

        diagnoses = db.scalars(
            select(DebugDiagnosis)
            .where(DebugDiagnosis.organization_id == organization_id)
            .order_by(DebugDiagnosis.created_at.desc())
            .limit(5)
        ).all()
        actions = []
        diag_note = ""
        for d in diagnoses:
            ev.append(evidence("diagnosis", f"{d.summary} (cause: {d.probable_cause})", str(d.failure_id)))
            if d.affected_files:
                ev.append(evidence("affected_files", ", ".join(d.affected_files[:3]), None))
        if diagnoses:
            top = diagnoses[0]
            diag_note = f" Latest diagnosis: {top.summary} Recommended fix: {top.recommended_fix}"
            actions.append(action("Apply the recommended fix", top.recommended_fix, self.name))
        elif ev:
            actions.append(action("Diagnose the latest failure", "Paste the failing logs into Debug Intelligence for a root-cause analysis.", self.name))

        count = len(ev)
        summary = (f"Detected {len(failed_reqs) + len(failed_val) + len(crashed)} active failure signal(s)." if count else "No active failures detected.") + diag_note
        confidence = 0.8 if diagnoses else (0.6 if count else 0.3)
        return BrainResult(self.name, confidence, summary, ev, actions)


class WorkspaceBrain(BaseBrain):
    name = "workspace"
    keywords = ("workspace", "sandbox", "launch", "run", "environment", "container", "port", "health", "running")

    def reason(self, task, context, db, organization_id) -> BrainResult:
        from app.services.workspace.workspace_lifecycle import WorkspaceLifecycleService

        metrics = WorkspaceLifecycleService(db).metrics(organization_id)
        by_status = metrics.get("by_status", {})
        ev = [evidence("workspaces", f"{v} sandbox(es) '{k}'", None) for k, v in sorted(by_status.items())]
        if metrics.get("average_launch_ms") is not None:
            ev.append(evidence("metrics", f"Average launch {metrics['average_launch_ms']} ms", None))
        actions = []
        unhealthy = by_status.get("crashed", 0) + by_status.get("failed", 0)
        if unhealthy:
            actions.append(action(f"Recover {unhealthy} unhealthy sandbox(es)", "Restart or delete crashed/failed workspaces.", self.name))
        running = by_status.get("running", 0)
        summary = f"{metrics.get('total', 0)} sandbox(es); {running} running, {unhealthy} unhealthy."
        return BrainResult(self.name, 0.7 if metrics.get("total") else 0.3, summary, ev, actions)


class SecurityBrain(BaseBrain):
    name = "security"
    keywords = ("security", "secret", "vulnerab", "risk", "permission", "compliance", "scan", "cve", "exposure")

    def reason(self, task, context, db, organization_id) -> BrainResult:
        risky = db.scalars(
            select(PullRequestScan).where(
                PullRequestScan.organization_id == organization_id,
                PullRequestScan.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]),
            )
        ).all()
        ev = [
            evidence("scan", f"{s.risk_level.value} risk on {s.title or ('PR #' + str(s.github_pr_number))}", str(s.id))
            for s in risky[:5]
        ]
        actions = []
        if risky:
            actions.append(action(f"Review {len(risky)} high/critical scan(s)", "Address risky changes before they merge.", self.name))
        summary = (
            f"{len(risky)} high/critical risk scan(s) need review."
            if risky
            else "No high/critical security risks detected. Secrets are never materialized."
        )
        return BrainResult(self.name, 0.75 if risky else 0.4, summary, ev, actions)


class PlanningBrain(BaseBrain):
    name = "planning"
    keywords = ("plan", "milestone", "break down", "estimate", "sequence", "roadmap", "next", "phase")

    def reason(self, task, context, db, organization_id) -> BrainResult:
        phases = ProductBrainService(db).roadmap()
        ev = [evidence("roadmap", f"Phase {p['id']}: {p['title']}", None) for p in phases[:6]]
        actions = []
        if phases:
            nxt = phases[0]
            actions.append(
                action(f"Sequence next milestone: Phase {nxt['id']}", nxt["title"] or "Break it into tasks and estimate.", self.name)
            )
        summary = (
            f"Roadmap has {len(phases)} phase(s); plan execution in dependency order."
            if phases
            else "No roadmap document found to plan against."
        )
        return BrainResult(self.name, 0.6 if phases else 0.3, summary, ev, actions)


class MemoryBrain(BaseBrain):
    name = "memory"
    keywords = ("remember", "memory", "history", "past", "previously", "decision", "learned", "before")

    def reason(self, task, context, db, organization_id) -> BrainResult:
        terms = [w for w in task.replace("?", " ").split() if len(w) > 3]
        matches = BrainMemoryService(db).search(organization_id, terms)
        ev = [evidence("memory", f"{m.kind}: {m.title}", str(m.id)) for m in matches]
        actions = []
        if not matches:
            actions.append(action("Capture this as memory", "No prior memory matched; record the outcome for next time.", self.name))
        summary = f"Recalled {len(matches)} relevant memory entry(ies)." if matches else "No relevant memory yet."
        return BrainResult(self.name, 0.6 if matches else 0.25, summary, ev, actions)


class KnowledgeBrain(BaseBrain):
    name = "knowledge"
    keywords = (
        "which", "module", "modules", "service", "services", "depend", "depends", "handle", "handles",
        "graph", "knowledge", "recently", "changed", "risk", "risks", "endpoint", "migration", "where",
        "connected", "related",
    )

    def reason(self, task, context, db, organization_id) -> BrainResult:
        retrieval = KnowledgeRetrievalService(db)
        nodes = retrieval.recall_for_question(organization_id, task)
        ev = [
            evidence(n.node_type, n.title + (" [stale]" if retrieval.is_stale(n) else ""), str(n.id))
            for n in nodes
        ]
        actions = []
        if not nodes:
            actions.append(action("Ingest knowledge", "The graph has no matching knowledge yet; run ingestion.", self.name))
        summary = (
            f"Found {len(nodes)} related knowledge node(s): "
            + ", ".join(f"{n.node_type}:{n.title}" for n in nodes[:4])
            if nodes
            else "No matching knowledge in the graph yet."
        )
        return BrainResult(self.name, 0.7 if nodes else 0.3, summary, ev, actions)


def build_brains() -> list[BaseBrain]:
    return [
        ProductBrain(),
        EngineeringBrain(),
        DebugBrain(),
        WorkspaceBrain(),
        SecurityBrain(),
        PlanningBrain(),
        MemoryBrain(),
        KnowledgeBrain(),
    ]
