"""AI Code Generation Engine (Phase 10, Step 3).

Generates a STRUCTURED change plan from an approved engineering request using
the configured AI provider (via the AI Provider Router). It consumes the
engineering request, Repository DNA, the Repository Materializer snapshot, and
the execution plan.

It does NOT execute changes, modify repository files, commit, push, or open
PRs. The output is structured data describing what *would* change — never
free-form text and never applied.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.errors import AppError, NotFoundError
from app.models.engineering_request import EngineeringRequest, RequestStatus
from app.models.execution_plan import ExecutionPlan
from app.models.repository_dna import RepositoryDNA
from app.models.rule import ArchitectureRule, CompanyRule, CompanyRuleType
from app.services.ai.provider_router import AIProviderRouter
from app.services.audit_service import AuditService
from app.services.execution.safety_engine import ExecutionSafetyEngine
from app.services.repository_dna_service import RepositoryDNAService

logger = logging.getLogger(__name__)

VALID_OPERATIONS = {"create", "modify", "delete"}

EXT_LANGUAGE = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".sql": "SQL",
    ".sh": "Shell",
    ".md": "Markdown",
}


@dataclass
class CodeChangePlan:
    engineering_request_id: str
    files_to_modify: list[str]
    files_to_create: list[str]
    files_to_delete: list[str]
    changes: list[dict]
    tests_to_add: list[str]
    documentation_updates: list[str]
    estimated_lines_changed: int
    confidence_score: float
    ai_available: bool
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "engineering_request_id": self.engineering_request_id,
            "files_to_modify": self.files_to_modify,
            "files_to_create": self.files_to_create,
            "files_to_delete": self.files_to_delete,
            "changes": self.changes,
            "tests_to_add": self.tests_to_add,
            "documentation_updates": self.documentation_updates,
            "estimated_lines_changed": self.estimated_lines_changed,
            "confidence_score": self.confidence_score,
            "ai_available": self.ai_available,
            "notes": self.notes,
        }


class CodeGenerationEngine:
    def __init__(self, db: Session, *, router: AIProviderRouter | None = None) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.router = router or AIProviderRouter()
        self.safety_engine = ExecutionSafetyEngine()

    # -- command ---------------------------------------------------------------

    def generate(
        self,
        *,
        engineering_request_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        materialization: Any | None = None,
    ) -> CodeChangePlan:
        request = self._require_request(engineering_request_id, organization_id)
        logger.info(
            "code_generation_started",
            extra={"engineering_request_id": str(request.id), "ai_provider": settings.ai_provider},
        )
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="code_generation_started",
            target_type="engineering_request",
            target_id=str(request.id),
            metadata={},
        )

        try:
            self._validate_preconditions(request, materialization)

            dna = RepositoryDNAService(self.db).get_optional(request.repository_id, organization_id) if request.repository_id else None
            execution_plan = self.db.scalar(
                select(ExecutionPlan).where(ExecutionPlan.engineering_request_id == request.id)
            )

            raw = self._call_ai(self._build_prompt(request, dna, materialization, execution_plan))
            parsed = self._parse(raw) if raw else None
            plan = self._build_plan(request, parsed, execution_plan)

            # Post-generation safety validation against the proposed change set.
            self._validate_change_set(request, organization_id, plan, materialization)

            logger.info(
                "code_generation_completed",
                extra={
                    "engineering_request_id": str(request.id),
                    "file_count": len(plan.changes),
                    "ai_available": plan.ai_available,
                    "confidence_score": plan.confidence_score,
                },
            )
            self.audit.log(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="code_generation_completed",
                target_type="engineering_request",
                target_id=str(request.id),
                metadata={"file_count": len(plan.changes), "ai_available": plan.ai_available},
            )
            return plan
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "code_generation_failed",
                extra={"engineering_request_id": str(request.id), "error": str(exc)[:500]},
            )
            self.audit.log(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="code_generation_failed",
                target_type="engineering_request",
                target_id=str(request.id),
                metadata={"error": str(exc)[:300]},
            )
            raise

    # -- preconditions ---------------------------------------------------------

    def _validate_preconditions(self, request: EngineeringRequest, materialization: Any | None) -> None:
        if request.status != RequestStatus.APPROVED:
            raise AppError("Code generation requires an approved engineering request.")
        if materialization is None or not getattr(materialization, "materialized", False):
            raise AppError("Code generation requires a materialized repository.")
        workspace_path = getattr(materialization, "workspace_path", None)
        if not workspace_path or not os.path.isdir(workspace_path):
            raise AppError("Code generation requires a valid workspace.")

    def _validate_change_set(
        self,
        request: EngineeringRequest,
        organization_id: uuid.UUID,
        plan: CodeChangePlan,
        materialization: Any | None,
    ) -> None:
        all_paths = plan.files_to_modify + plan.files_to_create + plan.files_to_delete
        all_contents = self._collect_contents(plan)

        # Protected / secret files may never be targeted.
        safety = self.safety_engine.validate(
            estimated_files=all_paths,
            branch_name=getattr(materialization, "target_branch", None),
            default_branch=getattr(materialization, "default_branch", None),
            repository_linked=True,
        )
        if safety["forbidden_files"] or safety["protected_files"]:
            offending = safety["forbidden_files"] + safety["protected_files"]
            raise AppError(f"Generation rejected: protected files requested ({', '.join(offending)}).")

        # Company rules.
        violation = self._company_violation(organization_id, all_paths, all_contents)
        if violation:
            raise AppError(f"Generation rejected: company rule prohibits the change ({violation}).")

        # Architecture rules.
        violation = self._architecture_violation(organization_id, plan, all_contents)
        if violation:
            raise AppError(f"Generation rejected: architecture rule prohibits the change ({violation}).")

    # -- AI plumbing -----------------------------------------------------------

    def _call_ai(self, prompt: str) -> str | None:
        """Return raw model output, None to trigger deterministic fallback.

        Provider-unavailable / unknown-provider errors propagate (clear error).
        """
        if not settings.ai_review_enabled:
            return None
        return self.router.generate(prompt)

    def _build_prompt(
        self,
        request: EngineeringRequest,
        dna: RepositoryDNA | None,
        materialization: Any | None,
        execution_plan: ExecutionPlan | None,
    ) -> str:
        languages = []
        if dna is not None:
            languages = list(dna.languages or [])
        elif materialization is not None:
            languages = list(getattr(materialization, "language_hints", []) or [])
        plan_tasks = "\n".join(f"- {t.get('title', '')}" for t in (execution_plan.tasks if execution_plan else []))
        return (
            "You are an AI software engineer. Produce a STRUCTURED change plan as "
            "JSON only. Do NOT write to disk, commit, push, or open PRs.\n\n"
            f"Request: {request.title}\nType: {request.request_type.value}\n"
            f"Description:\n{request.description}\n\n"
            f"Languages: {', '.join(languages) or 'unknown'}\n"
            f"Plan tasks:\n{plan_tasks or '- (none)'}\n\n"
            "Return ONLY valid JSON:\n"
            '{\n'
            '  "changes": [\n'
            '    {"path": str, "operation": "create|modify|delete", "language": str,\n'
            '     "operations": [{"type": str, "target": str, "content": str, "explanation": str}],\n'
            '     "explanation": str}\n'
            '  ],\n'
            '  "tests_to_add": [str],\n'
            '  "documentation_updates": [str],\n'
            '  "estimated_lines_changed": int,\n'
            '  "confidence_score": number\n'
            '}\n'
        )

    def _parse(self, raw: str | None) -> dict[str, Any] | None:
        if not raw:
            return None
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    # -- plan assembly ---------------------------------------------------------

    def _build_plan(
        self,
        request: EngineeringRequest,
        parsed: dict[str, Any] | None,
        execution_plan: ExecutionPlan | None,
    ) -> CodeChangePlan:
        ai_available = bool(parsed)
        notes: list[str] = []
        if parsed:
            changes = self._normalize_changes(parsed.get("changes"))
            tests = self._as_str_list(parsed.get("tests_to_add"))
            docs = self._as_str_list(parsed.get("documentation_updates"))
            estimated = parsed.get("estimated_lines_changed")
            confidence = parsed.get("confidence_score")
        else:
            changes = self._fallback_changes(request, execution_plan)
            tests = list(request.test_plan or []) or ["Add tests covering the change."]
            docs = ["Update documentation if user-facing behavior changes."]
            estimated = None
            confidence = None
            notes.append("AI output unavailable; produced a deterministic fallback plan for human review.")

        files_to_modify = [c["path"] for c in changes if c["operation"] == "modify"]
        files_to_create = [c["path"] for c in changes if c["operation"] == "create"]
        files_to_delete = [c["path"] for c in changes if c["operation"] == "delete"]

        if not isinstance(estimated, int) or estimated < 0:
            estimated = self._estimate_lines(changes)
        confidence = self._normalize_confidence(confidence, ai_available)

        return CodeChangePlan(
            engineering_request_id=str(request.id),
            files_to_modify=files_to_modify,
            files_to_create=files_to_create,
            files_to_delete=files_to_delete,
            changes=changes,
            tests_to_add=tests,
            documentation_updates=docs,
            estimated_lines_changed=estimated,
            confidence_score=confidence,
            ai_available=ai_available,
            notes=notes,
        )

    def _normalize_changes(self, value: Any) -> list[dict]:
        result: list[dict] = []
        if not isinstance(value, list):
            return result
        for item in value:
            if not isinstance(item, dict) or not item.get("path"):
                continue
            operation = str(item.get("operation", "modify")).lower()
            if operation not in VALID_OPERATIONS:
                operation = "modify"
            path = str(item["path"])
            ops = item.get("operations")
            operations = []
            if isinstance(ops, list):
                for op in ops:
                    if isinstance(op, dict):
                        operations.append(
                            {
                                "type": str(op.get("type", "edit")),
                                "target": str(op.get("target", "")),
                                "content": str(op.get("content", "")),
                                "explanation": str(op.get("explanation", "")),
                            }
                        )
            if not operations:
                operations = [{"type": operation, "target": "", "content": "", "explanation": ""}]
            result.append(
                {
                    "path": path,
                    "operation": operation,
                    "language": str(item.get("language") or self._language_for(path)),
                    "operations": operations,
                    "explanation": str(item.get("explanation", "")),
                }
            )
        return result

    def _fallback_changes(self, request: EngineeringRequest, execution_plan: ExecutionPlan | None) -> list[dict]:
        paths: list[str] = []
        if execution_plan and execution_plan.estimated_files:
            paths = [str(p) for p in execution_plan.estimated_files]
        if not paths:
            for item in request.affected_files or []:
                if isinstance(item, dict) and item.get("path"):
                    paths.append(str(item["path"]))
        changes = []
        for path in paths:
            changes.append(
                {
                    "path": path,
                    "operation": "modify",
                    "language": self._language_for(path),
                    "operations": [
                        {"type": "modify", "target": "", "content": "", "explanation": "Apply the approved plan."}
                    ],
                    "explanation": "Derived from the approved execution plan (no AI output available).",
                }
            )
        return changes

    # -- rule checks -----------------------------------------------------------

    def _company_violation(self, organization_id: uuid.UUID, paths: list[str], contents: list[str]) -> str | None:
        rules = self.db.scalars(
            select(CompanyRule).where(
                CompanyRule.organization_id == organization_id,
                CompanyRule.is_active.is_(True),
            )
        ).all()
        for rule in rules:
            pattern = rule.pattern or ""
            if rule.rule_type == CompanyRuleType.FILE_PATH:
                if any(self._path_matches(p, pattern) for p in paths):
                    return rule.name
            elif rule.rule_type == CompanyRuleType.FORBIDDEN_TEXT:
                if pattern and any(pattern.lower() in c.lower() for c in contents):
                    return rule.name
            elif rule.rule_type == CompanyRuleType.REGEX:
                try:
                    if pattern and any(re.search(pattern, c) for c in contents):
                        return rule.name
                except re.error:
                    continue
            # REQUIRED_TEXT cannot be reliably enforced on a plan; skipped.
        return None

    def _architecture_violation(self, organization_id: uuid.UUID, plan: CodeChangePlan, contents: list[str]) -> str | None:
        rules = self.db.scalars(
            select(ArchitectureRule).where(
                ArchitectureRule.organization_id == organization_id,
                ArchitectureRule.is_active.is_(True),
            )
        ).all()
        targeted = plan.files_to_modify + plan.files_to_create
        for rule in rules:
            source_pattern = rule.source_path_pattern or ""
            forbidden = rule.forbidden_import_pattern or ""
            if not source_pattern or not forbidden:
                continue
            if not any(self._path_matches(p, source_pattern) for p in targeted):
                continue
            try:
                if any(re.search(forbidden, c) for c in contents):
                    return rule.name
            except re.error:
                continue
        return None

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _path_matches(path: str, pattern: str) -> bool:
        normalized = pattern.replace("**/", "*/").replace("**", "*")
        return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, normalized) or pattern.strip("*/") in path

    @staticmethod
    def _collect_contents(plan: CodeChangePlan) -> list[str]:
        contents: list[str] = []
        for change in plan.changes:
            contents.append(change.get("explanation", ""))
            for op in change.get("operations", []):
                contents.append(op.get("content", ""))
                contents.append(op.get("explanation", ""))
        return [c for c in contents if c]

    @staticmethod
    def _language_for(path: str) -> str:
        return EXT_LANGUAGE.get(os.path.splitext(path)[1].lower(), "unknown")

    @staticmethod
    def _estimate_lines(changes: list[dict]) -> int:
        total = 0
        for change in changes:
            for op in change.get("operations", []):
                content = op.get("content", "")
                total += len(content.splitlines()) if content else 5
        return total or len(changes) * 5

    @staticmethod
    def _normalize_confidence(value: Any, ai_available: bool) -> float:
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        return 0.6 if ai_available else 0.3

    @staticmethod
    def _as_str_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _require_request(self, engineering_request_id: uuid.UUID, organization_id: uuid.UUID) -> EngineeringRequest:
        request = self.db.scalar(
            select(EngineeringRequest)
            .options(joinedload(EngineeringRequest.repository))
            .where(
                EngineeringRequest.id == engineering_request_id,
                EngineeringRequest.organization_id == organization_id,
            )
        )
        if not request:
            raise NotFoundError("Engineering request not found")
        return request
