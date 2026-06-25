from __future__ import annotations

import re

from app.models.execution_plan import ExecutionSafetyStatus

# Paths that must NEVER be modified by the agent. Any match => BLOCKED.
FORBIDDEN_PATH_PATTERNS: tuple[str, ...] = (
    r"(^|/)\.env($|\.|/)",
    r"(^|/)secrets?($|/)",
    r"\.pem$",
    r"\.key$",
    r"(^|/)id_rsa",
    r"(^|/)credentials?($|\.|/)",
    r"(^|/)\.git/",
    r"(^|/)\.github/workflows/",  # CI/CD / deploy config
    r"\.p12$",
    r"\.pfx$",
)

# Secret-bearing indicators. Any match => BLOCKED (secret detection).
SECRET_PATTERNS: tuple[str, ...] = (
    r"(^|/)\.env",
    r"secret",
    r"credential",
    r"private[_-]?key",
)

# Security/auth-sensitive areas. Any match => at least NEEDS_APPROVAL.
PROTECTED_FILE_PATTERNS: tuple[str, ...] = (
    r"security",
    r"auth",
    r"login",
    r"logout",
    r"password",
    r"(^|/)jwt",
    r"oauth",
    r"session",
    r"permission",
    r"middleware",
    r"(^|/)config\.py$",
    r"(^|/)settings\.py$",
    r"dockerfile",
    r"docker-compose",
    r"(^|/)alembic/",
    r"(^|/)migrations?/",
)

DEFAULT_MAX_FILES = 25


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    lowered = path.lower()
    return any(re.search(pattern, lowered) for pattern in patterns)


class ExecutionSafetyEngine:
    """Pure, deterministic safety classification for a proposed change set.

    Produces one of: safe | needs_approval | blocked. It evaluates metadata only
    (file paths, counts, branch) and never inspects or writes source code.
    """

    def __init__(self, *, max_files: int = DEFAULT_MAX_FILES) -> None:
        self.max_files = max_files

    def validate(
        self,
        *,
        estimated_files: list[str],
        branch_name: str | None,
        default_branch: str | None,
        repository_linked: bool,
    ) -> dict:
        findings: list[dict] = []
        protected_files: list[str] = []
        forbidden_files: list[str] = []

        for raw in estimated_files:
            path = str(raw)
            if _matches_any(path, FORBIDDEN_PATH_PATTERNS) or _matches_any(path, SECRET_PATTERNS):
                forbidden_files.append(path)
                findings.append(
                    {
                        "level": "block",
                        "category": "forbidden_path",
                        "path": path,
                        "message": f"'{path}' is a secret/protected path the agent may never modify.",
                    }
                )
            elif _matches_any(path, PROTECTED_FILE_PATTERNS):
                protected_files.append(path)
                findings.append(
                    {
                        "level": "approval",
                        "category": "security_sensitive",
                        "path": path,
                        "message": f"'{path}' is security/infrastructure-sensitive and requires explicit approval.",
                    }
                )

        # File-count guardrail.
        if len(estimated_files) > self.max_files:
            findings.append(
                {
                    "level": "approval",
                    "category": "max_files",
                    "message": (
                        f"Change touches {len(estimated_files)} files, above the "
                        f"safe limit of {self.max_files}; requires approval."
                    ),
                }
            )

        # Branch safety.
        normalized_branch = (branch_name or "").strip().lower()
        if branch_name is not None:
            if not normalized_branch.startswith("codedna/ai/"):
                findings.append(
                    {
                        "level": "block",
                        "category": "branch_safety",
                        "message": "Working branch must be an isolated 'codedna/ai/...' branch.",
                    }
                )
            elif default_branch and normalized_branch == default_branch.strip().lower():
                findings.append(
                    {
                        "level": "block",
                        "category": "branch_safety",
                        "message": "Working branch must never equal the default branch.",
                    }
                )

        # Repository linkage.
        if not repository_linked:
            findings.append(
                {
                    "level": "approval",
                    "category": "repository_state",
                    "message": "Repository is not linked to a GitHub installation; requires approval.",
                }
            )

        levels = {finding["level"] for finding in findings}
        if "block" in levels:
            status = ExecutionSafetyStatus.BLOCKED
        elif "approval" in levels:
            status = ExecutionSafetyStatus.NEEDS_APPROVAL
        else:
            status = ExecutionSafetyStatus.SAFE

        return {
            "status": status,
            "findings": findings,
            "protected_files": protected_files,
            "forbidden_files": forbidden_files,
            "max_files": self.max_files,
            "file_count": len(estimated_files),
        }
