from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings
from app.models.engineering_request import EngineeringRequest, RequestType
from app.models.repository import Repository
from app.models.scan import PullRequestScan, RiskLevel
from app.services.ai_review.groq_client import GroqClient
from app.services.ai_review.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

# Hard safety rules. The AI Engineering Agent only ever produces a *plan*; it can
# never perform these actions. These are always attached to every plan.
FORBIDDEN_CHANGES: list[str] = [
    "Modifying secrets, credentials, API tokens, or .env files",
    "Pushing or committing directly to the default/main branch",
    "Deploying to any environment",
    "Changing authentication or other security-sensitive code without explicit high-risk approval",
    "Merging the pull request — every change requires human review and approval",
]

# Keywords that mark a request/area as security-sensitive.
SECURITY_KEYWORDS: tuple[str, ...] = (
    "auth",
    "authentication",
    "authorization",
    "login",
    "logout",
    "password",
    "secret",
    "token",
    "credential",
    "jwt",
    "oauth",
    "session",
    "security",
    "permission",
    "crypto",
    "encrypt",
    "private key",
    "webhook secret",
)

_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


class EngineeringPlanningService:
    """Generates a structured, safety-bounded implementation plan for a request.

    The plan is advisory only. Nothing here merges, pushes, or deploys.
    """

    def __init__(self, *, client: GroqClient | OllamaClient | None = None) -> None:
        provider = settings.ai_provider.lower()
        if client is not None:
            self.client = client
        elif provider == "groq":
            self.client = GroqClient()
        else:
            self.client = OllamaClient()
        self.provider = provider

    # -- public API ------------------------------------------------------------

    def generate_plan(
        self,
        *,
        request: EngineeringRequest,
        repository: Repository | None,
        recent_scans: list[PullRequestScan] | None = None,
        repository_dna: object | None = None,
    ) -> dict[str, Any]:
        prompt = self._build_prompt(request, repository, recent_scans or [], repository_dna)
        raw = self._call_ai(prompt)
        parsed = self._parse(raw) if raw else None
        return self._merge_with_safety(request, repository, parsed)

    # -- AI plumbing -----------------------------------------------------------

    def _call_ai(self, prompt: str) -> str | None:
        """Return raw model output, or None when AI is unavailable/disabled.

        Never raises: planning must degrade gracefully to a deterministic plan.
        """
        if not settings.ai_review_enabled:
            logger.info("engineering_plan_ai_disabled")
            return None
        try:
            return self.client.generate(prompt)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            logger.warning("engineering_plan_ai_failed", extra={"error": str(exc)})
            return None

    def _build_prompt(
        self,
        request: EngineeringRequest,
        repository: Repository | None,
        recent_scans: list[PullRequestScan],
        repository_dna: object | None = None,
    ) -> str:
        repo_line = (
            f"Repository: {repository.full_name} (default branch: {repository.default_branch})"
            if repository
            else "Repository: not specified"
        )
        scan_lines = "\n".join(
            f"- PR #{scan.github_pr_number}: {scan.title or 'untitled'} "
            f"(risk={scan.risk_level.value if scan.risk_level else 'n/a'})"
            for scan in recent_scans[:5]
        ) or "- No recent scans available."

        dna_line = self._dna_summary(repository_dna)

        return (
            "You are an AI engineering planner. You ONLY produce a plan. You must "
            "never deploy, merge, push to main, or modify secrets. Every change must "
            "go through a human-reviewed GitHub pull request.\n\n"
            f"Request title: {request.title}\n"
            f"Request type: {request.request_type.value}\n"
            f"Description:\n{request.description}\n\n"
            f"{repo_line}\n"
            f"Repository DNA: {dna_line}\n"
            f"Recent scans:\n{scan_lines}\n\n"
            "Return ONLY valid JSON with these keys:\n"
            '{\n'
            '  "summary": string,\n'
            '  "request_type": one of '
            '["bug","feature","refactor","docs","security","performance","other"],\n'
            '  "affected_files": [{"path": string, "reason": string}],\n'
            '  "implementation_plan": [string, ...],\n'
            '  "test_plan": [string, ...],\n'
            '  "risk_level": one of ["low","medium","high","critical"],\n'
            '  "allowed_changes": [string, ...],\n'
            '  "forbidden_changes": [string, ...],\n'
            '  "safety_notes": [string, ...]\n'
            '}\n'
        )

    @staticmethod
    def _dna_summary(repository_dna: object | None) -> str:
        if repository_dna is None:
            return "not available."
        languages = getattr(repository_dna, "languages", None) or []
        frameworks = getattr(repository_dna, "frameworks", None) or []
        parts = []
        if languages:
            parts.append("languages: " + ", ".join(map(str, languages)))
        if frameworks:
            parts.append("frameworks: " + ", ".join(map(str, frameworks)))
        return ("; ".join(parts) + ".") if parts else "available (no language/framework signals yet)."

    def _parse(self, raw: str | None) -> dict[str, Any] | None:
        if not raw:
            return None
        text = raw.strip()
        # Strip ```json ... ``` fences if present.
        if text.startswith("```"):
            text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            logger.warning("engineering_plan_parse_failed")
            return None
        return data if isinstance(data, dict) else None

    # -- safety merge ----------------------------------------------------------

    def _merge_with_safety(
        self,
        request: EngineeringRequest,
        repository: Repository | None,
        parsed: dict[str, Any] | None,
    ) -> dict[str, Any]:
        parsed = parsed or {}

        summary = self._as_str(parsed.get("summary")) or self._fallback_summary(request, repository)
        affected_files = self._normalize_affected_files(parsed.get("affected_files"))
        implementation_plan = self._as_str_list(parsed.get("implementation_plan")) or self._fallback_plan(request)
        test_plan = self._as_str_list(parsed.get("test_plan")) or self._fallback_tests(request)

        risk_level = self._coerce_risk(parsed.get("risk_level"))

        allowed = self._as_str_list(parsed.get("allowed_changes")) or self._default_allowed(request)
        notes = self._as_str_list(parsed.get("safety_notes"))

        # Enforce: security-sensitive work is at least high risk and clearly warned.
        if self._detect_security_sensitive(request, affected_files):
            risk_level = self._max_risk(risk_level, RiskLevel.HIGH)
            notes.append(
                "HIGH-RISK: This request appears to touch authentication or "
                "security-sensitive code. It requires explicit high-risk human "
                "approval before any change is implemented."
            )

        safety_notes = {
            "allowed": allowed,
            "forbidden": list(FORBIDDEN_CHANGES),
            "notes": notes,
            "human_approval_required": True,
            "ai_available": bool(parsed),
        }

        return {
            "ai_summary": summary,
            "affected_files": affected_files,
            "implementation_plan": implementation_plan,
            "test_plan": test_plan,
            "risk_level": risk_level,
            "safety_notes": safety_notes,
        }

    def _detect_security_sensitive(
        self, request: EngineeringRequest, affected_files: list[dict[str, Any]]
    ) -> bool:
        haystack = " ".join(
            [
                request.title or "",
                request.description or "",
                request.request_type.value,
                " ".join(str(item.get("path", "")) for item in affected_files),
            ]
        ).lower()
        if request.request_type == RequestType.SECURITY:
            return True
        return any(keyword in haystack for keyword in SECURITY_KEYWORDS)

    # -- helpers ---------------------------------------------------------------

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

    @staticmethod
    def _normalize_affected_files(value: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and item.get("path"):
                    result.append({"path": str(item["path"]), "reason": str(item.get("reason", ""))})
                elif isinstance(item, str) and item.strip():
                    result.append({"path": item.strip(), "reason": ""})
        return result

    @staticmethod
    def _coerce_risk(value: Any) -> RiskLevel:
        if isinstance(value, RiskLevel):
            return value
        if isinstance(value, str):
            try:
                return RiskLevel(value.strip().lower())
            except ValueError:
                pass
        return RiskLevel.MEDIUM

    @staticmethod
    def _max_risk(current: RiskLevel, floor: RiskLevel) -> RiskLevel:
        return current if _RISK_ORDER[current] >= _RISK_ORDER[floor] else floor

    @staticmethod
    def _fallback_summary(request: EngineeringRequest, repository: Repository | None) -> str:
        where = f" in {repository.full_name}" if repository else ""
        return (
            f"Automated analysis was unavailable, so this is a baseline plan for "
            f"'{request.title}'{where}. A human should refine it before approval."
        )

    @staticmethod
    def _fallback_plan(request: EngineeringRequest) -> list[str]:
        return [
            "Reproduce and confirm the reported behavior or requirement.",
            "Identify the smallest set of files that must change.",
            "Implement the change on a feature branch (never on main).",
            "Add or update automated tests covering the change.",
            "Open a pull request and request human review.",
        ]

    @staticmethod
    def _fallback_tests(request: EngineeringRequest) -> list[str]:
        return [
            "Add unit tests for the new or changed behavior.",
            "Run the existing backend test suite (pytest) and frontend build.",
            "Verify no regressions in the scan pipeline.",
        ]

    @staticmethod
    def _default_allowed(request: EngineeringRequest) -> list[str]:
        return [
            "Application source code relevant to the request, on a feature branch",
            "Automated tests covering the change",
            "Documentation related to the change",
        ]
