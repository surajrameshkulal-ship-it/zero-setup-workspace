"""DebugIntelligenceService (Phase 12.3 — Debug Intelligence & Diagnosis).

Diagnoses failures like a senior engineer: classify a failure log, find the
probable root cause, the affected files/services, and the related Engineering
Graph nodes, with severity, confidence, evidence, and a recommended fix.

Read-only and safe by default: it never edits code, runs anything, or writes to
GitHub. Raw logs and all derived text are secret-redacted. Self-healing
execution is a separate, human-gated phase (12.5).
"""

from __future__ import annotations

import uuid
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.debug import DebugDiagnosis, DebugFailure
from app.models.validation_run import ValidationRun
from app.models.workspace_instance import WorkspaceInstance
from app.services.brain.failure_parsers import classify, parse
from app.services.brain.knowledge_service import KnowledgeGraphService
from app.services.brain.safety_guard import BrainSafetyGuard

_CAUSE = {
    "test_failure": "An assertion or behavior changed in the code under test.",
    "build_failure": "A type or compilation error is breaking the build.",
    "lint_failure": "Code style / lint rules are violated.",
    "runtime_error": "An unhandled exception occurred at runtime.",
    "dependency_error": "A required module or package is missing or not installed.",
    "configuration_error": "A required configuration value or environment variable is missing or invalid.",
    "migration_error": "A database migration conflict or an out-of-date schema.",
    "webhook_error": "A webhook payload or signature could not be verified or processed.",
    "ai_provider_error": "The AI provider rejected the request (auth, rate limit, or model).",
    "workspace_failure": "The sandbox failed to start or become ready.",
}
_SEVERITY = {
    "build_failure": "high", "migration_error": "high", "runtime_error": "high", "test_failure": "high",
    "workspace_failure": "high", "dependency_error": "high", "ai_provider_error": "medium",
    "webhook_error": "medium", "configuration_error": "medium", "lint_failure": "low",
}


class DebugIntelligenceService:
    def __init__(self, db: Session, *, guard: BrainSafetyGuard | None = None, graph: KnowledgeGraphService | None = None) -> None:
        self.db = db
        self.guard = guard or BrainSafetyGuard()
        self.graph = graph or KnowledgeGraphService(db)

    # -- diagnose --------------------------------------------------------------

    def diagnose(
        self,
        *,
        organization_id: uuid.UUID,
        logs: str,
        source: str = "manual",
        source_ref: str | None = None,
        persist: bool = True,
    ) -> DebugDiagnosis:
        raw = self.guard.redact(logs or "") or ""
        ftype = classify(raw, source_hint=source)
        parsed = parse(raw, ftype)
        parsed = self.guard.sanitize(parsed)

        affected_files = parsed["affected_files"]
        affected_services = self._affected_services(affected_files)
        graph_nodes = self._related_graph_nodes(organization_id, affected_files, parsed["error_message"])
        severity = _SEVERITY.get(ftype, "medium")
        confidence = self._confidence(parsed, graph_nodes)
        probable_cause = _CAUSE.get(ftype, "Unclassified failure.")
        recommended_fix = self._recommended_fix(ftype, parsed)
        summary = self._summary(ftype, parsed, affected_services)
        evidence = self._evidence(parsed, graph_nodes)

        failure = DebugFailure(
            organization_id=organization_id,
            failure_type=ftype,
            source=source,
            source_ref=source_ref,
            title=parsed["title"],
            raw_log=raw[:20000],
            signature=parsed["signature"],
            affected_files=affected_files,
            affected_services=affected_services,
            severity=severity,
        )
        diagnosis = DebugDiagnosis(
            organization_id=organization_id,
            failure=failure,
            summary=summary,
            probable_cause=probable_cause,
            affected_files=affected_files,
            affected_services=affected_services,
            related_graph_nodes=graph_nodes,
            severity=severity,
            confidence_score=confidence,
            evidence=evidence,
            recommended_fix=recommended_fix,
        )
        if persist:
            self.db.add(failure)
            self.db.add(diagnosis)
            self.db.commit()
            self.db.refresh(diagnosis)
        return diagnosis

    # -- queries ---------------------------------------------------------------

    def list_failures(self, organization_id: uuid.UUID, *, failure_type: str | None = None, limit: int = 100) -> list[DebugFailure]:
        stmt = select(DebugFailure).where(DebugFailure.organization_id == organization_id)
        if failure_type:
            stmt = stmt.where(DebugFailure.failure_type == failure_type)
        return list(self.db.scalars(stmt.order_by(DebugFailure.created_at.desc()).limit(limit)))

    def get_failure(self, failure_id: uuid.UUID, organization_id: uuid.UUID) -> DebugFailure:
        failure = self.db.scalar(
            select(DebugFailure).where(
                DebugFailure.id == failure_id, DebugFailure.organization_id == organization_id
            )
        )
        if not failure:
            raise NotFoundError("Failure not found")
        return failure

    def patterns(self, organization_id: uuid.UUID) -> list[dict]:
        failures = self.list_failures(organization_id, limit=1000)
        groups: dict[str, dict] = {}
        for f in failures:
            g = groups.setdefault(
                f.signature,
                {"signature": f.signature, "failure_type": f.failure_type, "count": 0,
                 "example_title": f.title, "last_seen": None, "affected_files": f.affected_files},
            )
            g["count"] += 1
            ts = f.created_at.replace(tzinfo=timezone.utc).isoformat() if f.created_at and f.created_at.tzinfo is None else (f.created_at.isoformat() if f.created_at else None)
            if g["last_seen"] is None or (ts and ts > g["last_seen"]):
                g["last_seen"] = ts
        return sorted(groups.values(), key=lambda g: g["count"], reverse=True)

    # -- ingest existing system failures --------------------------------------

    def ingest_failures(self, organization_id: uuid.UUID) -> dict:
        ingested = 0
        existing_refs = {
            (f.source, f.source_ref)
            for f in self.db.scalars(
                select(DebugFailure).where(DebugFailure.organization_id == organization_id)
            )
            if f.source_ref
        }
        # Failed validation runs.
        for run in self.db.scalars(
            select(ValidationRun).where(
                ValidationRun.organization_id == organization_id, ValidationRun.status == "failed"
            )
        ):
            if ("validation", str(run.id)) in existing_refs:
                continue
            failed = [c for c in (run.checks or []) if c.get("status") == "failed"]
            log = "\n".join(f"{c.get('name')}: {c.get('details', '')}" for c in failed) or "Validation failed."
            self.diagnose(organization_id=organization_id, logs=log, source="validation", source_ref=str(run.id))
            ingested += 1
        # Failed / crashed workspaces.
        for ws in self.db.scalars(
            select(WorkspaceInstance).where(
                WorkspaceInstance.organization_id == organization_id,
                WorkspaceInstance.status.in_(["failed", "crashed"]),
            )
        ):
            if ("workspace", str(ws.id)) in existing_refs:
                continue
            log = ws.error_message or f"Workspace {ws.status}."
            self.diagnose(organization_id=organization_id, logs=log, source="workspace", source_ref=str(ws.id))
            ingested += 1
        return {"ingested": ingested}

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _affected_services(files: list[str]) -> list[str]:
        services: list[str] = []
        for path in files:
            p = path.replace("\\", "/")
            if "/app/services/" in p or p.startswith("app/services/"):
                name = p.split("app/services/")[-1].split("/")[0]
                services.append(f"service:{name}")
            elif "app/api" in p:
                services.append("api")
            elif "app/workers" in p:
                services.append("worker")
            elif "app/models" in p:
                services.append("model")
            elif p.startswith("frontend/") or "/frontend/" in p:
                services.append("frontend")
            elif "alembic/" in p:
                services.append("migrations")
        return list(dict.fromkeys(services))

    def _related_graph_nodes(self, organization_id: uuid.UUID, files: list[str], error: str) -> list[dict]:
        terms: list[str] = []
        for f in files:
            base = f.split("/")[-1].rsplit(".", 1)[0]
            terms.append(base)
            parts = [seg for seg in f.split("/") if seg not in ("app", "src", "")]
            terms.extend(parts[:2])
        terms.extend([w for w in (error or "").split() if len(w) > 4][:5])
        nodes = self.graph.recall(organization_id, terms) if terms else []
        return [{"id": str(n.id), "node_type": n.node_type, "title": n.title} for n in nodes[:6]]

    @staticmethod
    def _confidence(parsed: dict, graph_nodes: list) -> float:
        score = 0.4
        if parsed["affected_files"]:
            score += 0.2
        if parsed["error_message"]:
            score += 0.2
        if parsed["frames"] or parsed["failing_tests"]:
            score += 0.1
        if graph_nodes:
            score += 0.1
        return round(min(score, 0.95), 2)

    @staticmethod
    def _recommended_fix(ftype: str, parsed: dict) -> str:
        primary = parsed.get("primary_file") or (parsed["affected_files"][0] if parsed["affected_files"] else "the reported file")
        error = parsed.get("error_message") or ""
        fixes = {
            "test_failure": f"Inspect {primary} and reconcile the assertion with current behavior; update the code or the test.",
            "build_failure": f"Resolve the type/compile error in {primary}: {error}.",
            "lint_failure": "Run the linter/formatter and fix the reported rule violations.",
            "dependency_error": f"Install or declare the missing dependency referenced in the error: {error}.",
            "configuration_error": f"Set the missing configuration/environment value: {error}.",
            "migration_error": "Reconcile the migration head; use create_type=False for existing enums and run `alembic upgrade head`.",
            "webhook_error": "Verify the webhook secret and payload signature, then check the route handler.",
            "ai_provider_error": "Check the API key/quota and the selected model in AI provider settings.",
            "workspace_failure": f"Check the start command and readiness probe and review sandbox logs: {error}.",
            "runtime_error": f"Trace the exception from {primary} and add handling for: {error}.",
        }
        return fixes.get(ftype, f"Investigate {primary}: {error}.").strip()

    @staticmethod
    def _summary(ftype: str, parsed: dict, services: list[str]) -> str:
        label = ftype.replace("_", " ")
        where = f" in {parsed['primary_file']}" if parsed.get("primary_file") else ""
        svc = f" Affected: {', '.join(services)}." if services else ""
        msg = f" {parsed['error_message']}" if parsed.get("error_message") else ""
        return f"Detected a {label}{where}.{msg}{svc}".strip()

    @staticmethod
    def _evidence(parsed: dict, graph_nodes: list) -> list[dict]:
        ev: list[dict] = []
        if parsed.get("error_message"):
            ev.append({"source": "log", "detail": parsed["error_message"], "reference": None})
        for t in parsed.get("failing_tests", [])[:5]:
            ev.append({"source": "test", "detail": f"Failing: {t}", "reference": None})
        for fr in parsed.get("frames", [])[:5]:
            ev.append({"source": "stack", "detail": f"{fr['file']}:{fr['line']} in {fr['func']}", "reference": None})
        for n in graph_nodes:
            ev.append({"source": "graph", "detail": f"{n['node_type']}: {n['title']}", "reference": n["id"]})
        return ev
