from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import AppError, NotFoundError
from app.models.engineering_request import EngineeringRequest, RequestStatus
from app.models.execution_plan import ExecutionComplexity, ExecutionPlan, ExecutionSafetyStatus
from app.models.scan import RiskLevel
from app.services.audit_service import AuditService
from app.services.execution.github_workspace_manager import GitHubWorkspaceManager
from app.services.execution.repository_context_service import RepositoryContextService
from app.services.execution.safety_engine import ExecutionSafetyEngine

logger = logging.getLogger(__name__)

_DURATION_BY_COMPLEXITY = {
    ExecutionComplexity.LOW: "~1-2 hours",
    ExecutionComplexity.MEDIUM: "~0.5-1 day",
    ExecutionComplexity.HIGH: "~1-3 days",
}

DEPENDENCY_MANIFESTS = {
    "pyproject.toml",
    "requirements.txt",
    "pipfile",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "go.mod",
    "cargo.toml",
    "pom.xml",
    "build.gradle",
}


class ExecutionPlanService:
    """Produces planning-only execution metadata for an approved request.

    Never writes code, commits, pushes, merges, or deploys.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.context_service = RepositoryContextService(db)
        self.workspace = GitHubWorkspaceManager()
        self.safety_engine = ExecutionSafetyEngine()

    # -- queries ---------------------------------------------------------------

    def get_for_request(
        self, engineering_request_id: uuid.UUID, organization_id: uuid.UUID
    ) -> ExecutionPlan:
        plan = self.db.scalar(
            select(ExecutionPlan).where(
                ExecutionPlan.engineering_request_id == engineering_request_id,
                ExecutionPlan.organization_id == organization_id,
            )
        )
        if not plan:
            raise NotFoundError("Execution plan not found")
        return plan

    # -- command ---------------------------------------------------------------

    def generate(
        self,
        *,
        engineering_request_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> ExecutionPlan:
        request = self._get_request(engineering_request_id, organization_id)
        if request.status != RequestStatus.APPROVED:
            raise AppError("An execution plan can only be generated for an approved request")

        repository = request.repository

        context = self.context_service.build(organization_id=organization_id, repository=repository)
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="repository_context_loaded",
            target_type="engineering_request",
            target_id=str(request.id),
            metadata={"repository_id": str(repository.id) if repository else None},
        )

        branch_name = self.workspace.create_branch_name(request)
        repo_state = self.workspace.validate_repository_state(repository, branch_name=branch_name)
        context["workspace"] = {"branch_name": branch_name, "state": repo_state}

        estimated_files = self._estimated_files(request)
        safety = self.safety_engine.validate(
            estimated_files=estimated_files,
            branch_name=branch_name,
            default_branch=repo_state["default_branch"],
            repository_linked=repo_state["repository_linked"],
        )
        safety_status: ExecutionSafetyStatus = safety["status"]

        tasks = self._build_tasks(request)
        complexity = self._complexity(estimated_files, tasks, request.risk_level, safety_status)
        dependency_analysis = self._dependency_analysis(estimated_files)

        plan = self.db.scalar(
            select(ExecutionPlan).where(ExecutionPlan.engineering_request_id == request.id)
        )
        if plan is None:
            plan = ExecutionPlan(
                organization_id=organization_id,
                engineering_request_id=request.id,
                repository_id=repository.id if repository else None,
            )
            self.db.add(plan)

        plan.repository_id = repository.id if repository else None
        plan.tasks = tasks
        plan.estimated_files = estimated_files
        plan.dependency_analysis = dependency_analysis
        plan.complexity = complexity.value
        plan.estimated_duration = _DURATION_BY_COMPLEXITY[complexity]
        plan.rollback_strategy = self._rollback_strategy(branch_name)
        plan.validation_checklist = self._validation_checklist()
        plan.repository_context = context
        plan.safety_status = safety_status.value
        plan.safety_findings = safety["findings"]
        plan.branch_name = branch_name

        self.db.flush()

        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="execution_plan_generated",
            target_type="engineering_request",
            target_id=str(request.id),
            metadata={
                "safety_status": safety_status.value,
                "file_count": len(estimated_files),
                "complexity": complexity.value,
            },
        )

        if safety_status == ExecutionSafetyStatus.BLOCKED:
            self.audit.log(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="execution_blocked",
                target_type="engineering_request",
                target_id=str(request.id),
                metadata={"finding_count": len(safety["findings"])},
            )
        else:
            self.audit.log(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="execution_ready",
                target_type="engineering_request",
                target_id=str(request.id),
                metadata={"safety_status": safety_status.value},
            )

        self.db.commit()
        self.db.refresh(plan)
        return plan

    # -- helpers ---------------------------------------------------------------

    def _get_request(
        self, engineering_request_id: uuid.UUID, organization_id: uuid.UUID
    ) -> EngineeringRequest:
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

    @staticmethod
    def _estimated_files(request: EngineeringRequest) -> list[str]:
        files: list[str] = []
        for item in request.affected_files or []:
            if isinstance(item, dict) and item.get("path"):
                files.append(str(item["path"]))
            elif isinstance(item, str) and item.strip():
                files.append(item.strip())
        return files

    @staticmethod
    def _build_tasks(request: EngineeringRequest) -> list[dict]:
        steps = list(request.implementation_plan or [])
        if not steps:
            steps = [
                "Confirm the requirement and acceptance criteria.",
                "Implement the change on an isolated branch.",
                "Add or update automated tests.",
                "Open a pull request for human review.",
            ]
        return [{"order": index + 1, "title": str(step)} for index, step in enumerate(steps)]

    @staticmethod
    def _complexity(
        estimated_files: list[str],
        tasks: list[dict],
        risk_level: RiskLevel | None,
        safety_status: ExecutionSafetyStatus,
    ) -> ExecutionComplexity:
        score = len(estimated_files) + len(tasks)
        if score <= 3:
            complexity = ExecutionComplexity.LOW
        elif score <= 8:
            complexity = ExecutionComplexity.MEDIUM
        else:
            complexity = ExecutionComplexity.HIGH

        if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) or safety_status == ExecutionSafetyStatus.BLOCKED:
            complexity = ExecutionComplexity.HIGH
        return complexity

    @staticmethod
    def _dependency_analysis(estimated_files: list[str]) -> dict:
        matched = [path for path in estimated_files if path.split("/")[-1].lower() in DEPENDENCY_MANIFESTS]
        return {
            "touches_dependencies": bool(matched),
            "dependency_files": matched,
            "note": (
                "Estimated change modifies a dependency manifest; review for supply-chain impact."
                if matched
                else "No dependency manifest changes detected in the estimated files."
            ),
        }

    @staticmethod
    def _rollback_strategy(branch_name: str) -> list[str]:
        return [
            "All work happens on an isolated branch; nothing is merged or deployed automatically.",
            f"Discard the branch '{branch_name}' to abandon the change entirely.",
            "Close the (later) draft pull request to roll back proposed work.",
            "No database migrations are applied without a separate, explicit human action.",
        ]

    @staticmethod
    def _validation_checklist() -> list[str]:
        return [
            "Run the backend test suite: python -m pytest",
            "Run the frontend build: npm run build",
            "Re-run the CodeDNA scan on the pull request",
            "Human review and approval of the complete diff",
            "Confirm no protected or forbidden files were modified",
        ]
