"""KnowledgeIngestionService — populates the knowledge graph from CodeDNA data.

Read-only ingestion: it reads existing product signals (Repository DNA, scans,
workspaces, workspace health, brain decisions, audit logs, roadmap phases) and
the codebase layout (migrations, API endpoints, tests, service modules) and
upserts knowledge nodes + edges. It never executes code or writes to GitHub.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.brain import BrainDecision
from app.models.repository import Repository
from app.models.repository_dna import RepositoryDNA
from app.models.scan import PullRequestScan, RiskLevel
from app.models.workspace_instance import WorkspaceInstance
from app.models.workspace_launch import WorkspaceLaunch
from app.services.brain.knowledge_service import KnowledgeGraphService
from app.services.brain.product_brain import ProductBrain

logger = logging.getLogger(__name__)

_ENDPOINT_RE = re.compile(r"@router\.(get|post|put|patch|delete)\(\s*[\"']([^\"']*)[\"']", re.IGNORECASE)
MAX_TESTS = 100
MAX_ENDPOINTS = 250
MAX_AUDIT_EVENTS = 500
SERVICE_INTEGRATIONS = {"agent", "execution", "workspace"}  # service dirs that use GitHub
# Workspace statuses that mean the sandbox is not healthy.
UNHEALTHY_WORKSPACE_STATUSES = {"crashed", "failed", "error", "unhealthy", "expired"}


class KnowledgeIngestionService:
    def __init__(self, db: Session, *, graph: KnowledgeGraphService | None = None, backend_root: Path | None = None) -> None:
        self.db = db
        self.graph = graph or KnowledgeGraphService(db)
        self.backend_root = backend_root or Path(__file__).resolve().parents[3]

    def ingest(self, organization_id: uuid.UUID) -> dict:
        counts = {"nodes": 0, "edges": 0}

        def add_node(**kw):
            counts["nodes"] += 1
            return self.graph.upsert_node(organization_id=organization_id, **kw)

        def add_edge(frm, to, rel, **kw):
            self.graph.upsert_edge(
                organization_id=organization_id, from_node_id=frm.id, to_node_id=to.id, relationship_type=rel, **kw
            )
            counts["edges"] += 1

        # Integration node (GitHub) — everything that touches the repo uses it.
        github = add_node(
            node_type="integration", title="GitHub integration", source_type="integration", source_id="github",
            summary="GitHub App: read-only checkout, scans, and human-gated draft PRs.", confidence_score=0.9,
        )

        # Repositories (+ DNA summary).
        repo_nodes: dict[uuid.UUID, object] = {}
        for repo in self.db.scalars(select(Repository).where(Repository.organization_id == organization_id)):
            dna = self.db.scalar(
                select(RepositoryDNA).where(
                    RepositoryDNA.repository_id == repo.id, RepositoryDNA.organization_id == organization_id
                )
            )
            summary = (dna.architecture_summary if dna and dna.architecture_summary else f"Repository {repo.full_name}.")
            node = add_node(
                node_type="repository", title=repo.full_name, source_type="repository", source_id=str(repo.id),
                summary=summary, confidence_score=0.9,
                metadata={"languages": getattr(dna, "languages", []) if dna else []},
            )
            repo_nodes[repo.id] = node
            add_edge(node, github, "uses", confidence_score=0.7, evidence=[{"source": "platform", "detail": "Connected via GitHub App"}])

        # Workspaces -> belongs_to repository (+ health classification).
        ws_nodes: dict[uuid.UUID, object] = {}
        for ws in self.db.scalars(select(WorkspaceInstance).where(WorkspaceInstance.organization_id == organization_id)):
            healthy = (ws.status or "").lower() not in UNHEALTHY_WORKSPACE_STATUSES
            node = add_node(
                node_type="workspace", title=f"Sandbox {ws.repository_full_name or ws.repository_id}",
                source_type="workspace_instance", source_id=str(ws.id),
                summary=f"Workspace status: {ws.status} ({'healthy' if healthy else 'unhealthy'}).",
                confidence_score=0.7,
                metadata={
                    "status": ws.status, "runtime": ws.runtime, "healthy": healthy,
                    "recovery_attempts": ws.recovery_attempts,
                    "last_heartbeat_at": ws.last_heartbeat_at,
                },
            )
            ws_nodes[ws.id] = node
            repo_node = repo_nodes.get(ws.repository_id)
            if repo_node is not None:
                add_edge(node, repo_node, "belongs_to", confidence_score=0.8)
            # Unhealthy sandbox -> a risk node caused_by the workspace.
            if not healthy:
                risk = add_node(
                    node_type="risk",
                    title=f"Unhealthy sandbox: {ws.repository_full_name or ws.repository_id}",
                    source_type="workspace_health", source_id=str(ws.id),
                    summary=ws.error_message or f"Workspace is {ws.status}.", confidence_score=0.75,
                    metadata={"status": ws.status, "recovery_attempts": ws.recovery_attempts},
                )
                add_edge(risk, node, "caused_by", confidence_score=0.7,
                         evidence=[{"source": "workspace_health", "detail": f"status={ws.status}"}])
                if repo_node is not None:
                    add_edge(risk, repo_node, "belongs_to", confidence_score=0.6)

        # Workspace launch health (container health probes) -> related_to workspace.
        for launch in self.db.scalars(select(WorkspaceLaunch).where(WorkspaceLaunch.organization_id == organization_id)):
            health = launch.health_status or launch.status
            if not health:
                continue
            launch_healthy = health.lower() not in UNHEALTHY_WORKSPACE_STATUSES
            node = add_node(
                node_type="workspace",
                title=f"Launch health: {health}",
                source_type="workspace_launch", source_id=str(launch.id),
                summary=launch.health_detail or launch.failure_reason or f"Launch status {launch.status}.",
                confidence_score=0.7,
                metadata={"health_status": launch.health_status, "status": launch.status, "healthy": launch_healthy},
            )
            repo_node = repo_nodes.get(launch.repository_id)
            if repo_node is not None:
                add_edge(node, repo_node, "belongs_to", confidence_score=0.6)

        # Risky scans -> risk nodes belongs_to repository.
        for scan in self.db.scalars(
            select(PullRequestScan).where(
                PullRequestScan.organization_id == organization_id,
                PullRequestScan.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]),
            )
        ):
            node = add_node(
                node_type="risk", title=f"{scan.risk_level.value} risk: {scan.title or ('PR #' + str(scan.github_pr_number))}",
                source_type="scan", source_id=str(scan.id),
                summary=scan.summary or f"Scan flagged {scan.risk_level.value} risk.", confidence_score=0.8,
            )
            repo_node = repo_nodes.get(scan.repository_id)
            if repo_node is not None:
                add_edge(node, repo_node, "belongs_to", confidence_score=0.7)

        # Brain decisions.
        for dec in self.db.scalars(select(BrainDecision).where(BrainDecision.organization_id == organization_id)):
            add_node(
                node_type="decision", title=dec.title, source_type="brain_decision", source_id=str(dec.id),
                summary=dec.decision, confidence_score=dec.confidence or 0.5,
            )

        # Audit log activity (aggregated by action; never ingests IP/user-agent).
        self._ingest_audit_logs(organization_id, add_node, add_edge, repo_nodes, ws_nodes)

        # Roadmap phases + product blockers.
        product = ProductBrain(self.db)
        overview = product.overview(organization_id)
        for phase in overview["roadmap"]:
            add_node(
                node_type="phase", title=f"Phase {phase['id']}: {phase['title']}", source_type="roadmap",
                source_id=phase["id"], summary=phase["summary"], confidence_score=0.8,
            )
        for blocker in overview["blockers"]:
            add_node(
                node_type="blocker", title=blocker["title"], source_type="blocker",
                source_id=blocker.get("reference_id") or blocker["title"], summary=blocker["reason"],
                confidence_score=0.7, metadata={"severity": blocker["severity"], "type": blocker["type"]},
            )

        # Codebase layout (filesystem, read-only).
        self._ingest_codebase(organization_id, add_node, add_edge, github)

        self.db.commit()
        logger.info("knowledge_ingested", extra={"organization_id": str(organization_id), **counts})
        return counts

    # -- audit logs ------------------------------------------------------------

    def _ingest_audit_logs(self, organization_id, add_node, add_edge, repo_nodes, ws_nodes) -> None:
        """Aggregate audit events by action into compact knowledge nodes.

        Only the action, target, and counts are recorded — IP addresses and
        user-agents are deliberately never ingested into the graph.
        """
        rows = self.db.scalars(
            select(AuditLog)
            .where(AuditLog.organization_id == organization_id)
            .order_by(AuditLog.created_at.desc())
            .limit(MAX_AUDIT_EVENTS)
        )
        by_action: dict[str, dict] = {}
        for log in rows:
            agg = by_action.setdefault(log.action, {"count": 0, "latest": None})
            agg["count"] += 1
            if agg["latest"] is None:
                agg["latest"] = log
        for action_name, agg in by_action.items():
            latest = agg["latest"]
            node = add_node(
                node_type="audit", title=f"Activity: {action_name}",
                source_type="audit_log", source_id=action_name,
                summary=(
                    f"{agg['count']} audit event(s); latest target "
                    f"{latest.target_type or '-'}:{latest.target_id or '-'}."
                ),
                confidence_score=0.6,
                metadata={
                    "action": action_name, "count": agg["count"],
                    "target_type": latest.target_type, "target_id": latest.target_id,
                },
            )
            # Link the activity to the repository/workspace it most recently touched.
            target_node = None
            if latest.target_id:
                try:
                    target_uuid = uuid.UUID(latest.target_id)
                except (ValueError, AttributeError):
                    target_uuid = None
                if target_uuid is not None:
                    target_node = repo_nodes.get(target_uuid) or ws_nodes.get(target_uuid)
            if target_node is not None:
                add_edge(node, target_node, "related_to", confidence_score=0.5,
                         evidence=[{"source": "audit_log", "detail": action_name}])

    # -- codebase layout -------------------------------------------------------

    def _ingest_codebase(self, organization_id, add_node, add_edge, github) -> None:
        backend = self.backend_root

        # Migrations.
        versions = backend / "alembic" / "versions"
        if versions.exists():
            for path in sorted(versions.glob("*.py")):
                add_node(
                    node_type="migration", title=path.stem, source_type="migration", source_id=path.stem,
                    summary=self._docstring(path) or "Database migration.", confidence_score=0.9,
                )

        # API module + endpoints.
        api_module = add_node(
            node_type="module", title="app.api", source_type="module", source_id="app.api",
            summary="Versioned HTTP API routers.", confidence_score=0.8,
        )
        api_dir = backend / "app" / "api" / "v1"
        endpoints = 0
        if api_dir.exists():
            for path in sorted(api_dir.glob("*.py")):
                text = path.read_text(encoding="utf-8", errors="replace")
                for method, route in _ENDPOINT_RE.findall(text):
                    if endpoints >= MAX_ENDPOINTS:
                        break
                    title = f"{method.upper()} {path.stem}:{route or '/'}"
                    node = add_node(
                        node_type="endpoint", title=title, source_type="endpoint", source_id=title,
                        summary=f"Defined in app/api/v1/{path.name}.", confidence_score=0.7,
                    )
                    add_edge(node, api_module, "belongs_to", confidence_score=0.6)
                    endpoints += 1

        # Service modules (+ GitHub usage for the ones that touch the repo).
        services_dir = backend / "app" / "services"
        if services_dir.exists():
            for child in sorted(services_dir.iterdir()):
                if not child.is_dir() or child.name.startswith("_"):
                    continue
                node = add_node(
                    node_type="service", title=f"app.services.{child.name}", source_type="service",
                    source_id=f"app.services.{child.name}", summary=f"Service package: {child.name}.",
                    confidence_score=0.7,
                )
                if child.name in SERVICE_INTEGRATIONS:
                    add_edge(node, github, "depends_on", confidence_score=0.7,
                             evidence=[{"source": "codebase", "detail": f"{child.name} uses the GitHub integration"}])

        # Tests.
        tests_dir = backend / "tests"
        if tests_dir.exists():
            for i, path in enumerate(sorted(tests_dir.glob("test_*.py"))):
                if i >= MAX_TESTS:
                    break
                add_node(
                    node_type="test", title=path.stem, source_type="test", source_id=path.stem,
                    summary="Automated test module.", confidence_score=0.8,
                )

    @staticmethod
    def _docstring(path: Path) -> str | None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        m = re.search(r'"""(.+?)"""', text, re.DOTALL)
        if m:
            return m.group(1).strip().splitlines()[0][:200]
        return None
