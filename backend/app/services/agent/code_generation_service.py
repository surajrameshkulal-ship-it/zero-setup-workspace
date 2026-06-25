from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.errors import AppError, NotFoundError
from app.models.code_generation import CodeGenerationPreview
from app.models.engineering_request import EngineeringRequest, RequestStatus
from app.services.ai_review.groq_client import GroqClient
from app.services.ai_review.ollama_client import OllamaClient
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)

VALID_CHANGE_TYPES = {"modify", "create", "delete"}


class CodeGenerationService:
    """Produces an implementation PREVIEW for an approved request.

    Preview only: never writes files, commits, pushes, branches, opens PRs, or
    deploys. The diff is illustrative and is never applied.
    """

    def __init__(self, db: Session, *, client: GroqClient | OllamaClient | None = None) -> None:
        self.db = db
        self.audit = AuditService(db)
        provider = settings.ai_provider.lower()
        if client is not None:
            self.client = client
        elif provider == "groq":
            self.client = GroqClient()
        else:
            self.client = OllamaClient()

    # -- queries ---------------------------------------------------------------

    def get_for_request(
        self, engineering_request_id: uuid.UUID, organization_id: uuid.UUID
    ) -> CodeGenerationPreview:
        preview = self.db.scalar(
            select(CodeGenerationPreview).where(
                CodeGenerationPreview.engineering_request_id == engineering_request_id,
                CodeGenerationPreview.organization_id == organization_id,
            )
        )
        if not preview:
            raise NotFoundError("Code generation preview not found")
        return preview

    # -- command ---------------------------------------------------------------

    def generate(
        self,
        *,
        engineering_request_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> CodeGenerationPreview:
        request = self._get_request(engineering_request_id, organization_id)
        if request.status != RequestStatus.APPROVED:
            raise AppError("A code generation preview can only be produced for an approved request")

        raw = self._call_ai(self._build_prompt(request))
        parsed = self._parse(raw) if raw else None
        fields = self._build_preview(request, parsed)

        preview = self.db.scalar(
            select(CodeGenerationPreview).where(
                CodeGenerationPreview.engineering_request_id == request.id
            )
        )
        if preview is None:
            preview = CodeGenerationPreview(
                organization_id=organization_id,
                engineering_request_id=request.id,
                repository_id=request.repository_id,
            )
            self.db.add(preview)

        preview.repository_id = request.repository_id
        for key, value in fields.items():
            setattr(preview, key, value)

        self.db.flush()
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="code_generation_previewed",
            target_type="engineering_request",
            target_id=str(request.id),
            metadata={
                "file_count": len(preview.affected_files),
                "ai_available": preview.ai_available,
            },
        )
        self.db.commit()
        self.db.refresh(preview)
        return preview

    # -- AI plumbing -----------------------------------------------------------

    def _call_ai(self, prompt: str) -> str | None:
        if not settings.ai_review_enabled:
            return None
        try:
            return self.client.generate(prompt)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            logger.warning("code_generation_ai_failed", extra={"error": str(exc)})
            return None

    def _build_prompt(self, request: EngineeringRequest) -> str:
        plan_lines = "\n".join(f"- {step}" for step in (request.implementation_plan or [])) or "- (none)"
        files = ", ".join(
            str(item.get("path")) for item in (request.affected_files or []) if isinstance(item, dict)
        ) or "(unknown)"
        return (
            "You are an AI engineer producing an implementation PREVIEW only. You "
            "must NOT write files, commit, push, branch, open PRs, or deploy. Return "
            "an illustrative plan and a short illustrative unified diff.\n\n"
            f"Title: {request.title}\n"
            f"Type: {request.request_type.value}\n"
            f"Description:\n{request.description}\n\n"
            f"Approved plan:\n{plan_lines}\n"
            f"Likely files: {files}\n\n"
            "Return ONLY valid JSON with keys:\n"
            '{\n'
            '  "summary": string,\n'
            '  "affected_files": [{"path": string, "change_type": "modify|create|delete", "reason": string}],\n'
            '  "diff_preview": string,\n'
            '  "implementation_tasks": [string],\n'
            '  "documentation_updates": [string],\n'
            '  "tests_to_create": [string]\n'
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

    # -- preview assembly ------------------------------------------------------

    def _build_preview(self, request: EngineeringRequest, parsed: dict[str, Any] | None) -> dict[str, Any]:
        ai_available = bool(parsed)
        parsed = parsed or {}

        affected_files = self._normalize_files(parsed.get("affected_files")) or self._fallback_files(request)
        implementation_tasks = self._as_str_list(parsed.get("implementation_tasks")) or list(
            request.implementation_plan or []
        )
        documentation_updates = self._as_str_list(parsed.get("documentation_updates")) or [
            "Update the README/changelog if user-facing behavior changes."
        ]
        tests_to_create = self._as_str_list(parsed.get("tests_to_create")) or list(request.test_plan or []) or [
            "Add unit tests covering the new or changed behavior."
        ]
        diff_preview = self._as_str(parsed.get("diff_preview")) or self._fallback_diff(affected_files)
        summary = self._as_str(parsed.get("summary")) or (
            f"Illustrative implementation preview for '{request.title}'. "
            "No code has been written; this is a preview for human review."
        )

        estimated_changes = self._estimate_changes(affected_files, diff_preview)

        return {
            "summary": summary,
            "affected_files": affected_files,
            "diff_preview": diff_preview,
            "implementation_tasks": implementation_tasks,
            "documentation_updates": documentation_updates,
            "tests_to_create": tests_to_create,
            "estimated_changes": estimated_changes,
            "ai_available": ai_available,
        }

    @staticmethod
    def _normalize_files(value: Any) -> list[dict]:
        result: list[dict] = []
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("path"):
                    change_type = str(item.get("change_type", "modify")).lower()
                    if change_type not in VALID_CHANGE_TYPES:
                        change_type = "modify"
                    result.append(
                        {
                            "path": str(item["path"]),
                            "change_type": change_type,
                            "reason": str(item.get("reason", "")),
                        }
                    )
                elif isinstance(item, str) and item.strip():
                    result.append({"path": item.strip(), "change_type": "modify", "reason": ""})
        return result

    @staticmethod
    def _fallback_files(request: EngineeringRequest) -> list[dict]:
        files: list[dict] = []
        for item in request.affected_files or []:
            if isinstance(item, dict) and item.get("path"):
                files.append(
                    {"path": str(item["path"]), "change_type": "modify", "reason": str(item.get("reason", ""))}
                )
        return files

    @staticmethod
    def _fallback_diff(affected_files: list[dict]) -> str:
        if not affected_files:
            return "# No files estimated. Preview unavailable until the plan identifies files."
        lines = ["# ILLUSTRATIVE PREVIEW — not applied to the repository", ""]
        for file in affected_files[:5]:
            lines.append(f"--- a/{file['path']}")
            lines.append(f"+++ b/{file['path']}")
            lines.append("@@ illustrative change @@")
            lines.append(f"+ # TODO: {file.get('reason') or 'implement change'}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _estimate_changes(affected_files: list[dict], diff_preview: str) -> dict:
        additions = sum(1 for line in diff_preview.splitlines() if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in diff_preview.splitlines() if line.startswith("-") and not line.startswith("---"))
        return {
            "files": len(affected_files),
            "estimated_additions": additions,
            "estimated_deletions": deletions,
            "note": "Estimates are illustrative; no code has been written.",
        }

    @staticmethod
    def _as_str(value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @staticmethod
    def _as_str_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

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
