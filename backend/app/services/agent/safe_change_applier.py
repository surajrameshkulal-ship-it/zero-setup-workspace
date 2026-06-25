"""Safe Change Applier (Phase 10, Step 4).

Applies a structured code change plan into an isolated SecureWorkspaceManager
workspace ONLY. It never commits, pushes, opens PRs, deploys, or touches the
real repository — every write is constrained to the workspace and is reversible
via a rollback snapshot.

Supported structured operations (per file):
    create_file, replace_file, insert_after, insert_before, replace_block,
    delete_file
Unsupported operations are skipped and reported (never guessed at).
"""

from __future__ import annotations

import base64
import difflib
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.errors import AppError
from app.services.audit_service import AuditService
from app.services.workspace.secure_workspace_manager import (
    SecureWorkspaceManager,
    WorkspaceHandle,
)

logger = logging.getLogger(__name__)

SUPPORTED_OPERATIONS = {
    "create_file",
    "replace_file",
    "insert_after",
    "insert_before",
    "replace_block",
    "delete_file",
}


@dataclass
class ApplyResult:
    files_changed: list[str]
    patch_preview: str
    applied_operations: list[dict]
    skipped_operations: list[dict]
    safety_warnings: list[str]
    rollback_snapshot: dict
    dry_run: bool

    def as_dict(self) -> dict:
        return {
            "files_changed": self.files_changed,
            "patch_preview": self.patch_preview,
            "applied_operations": self.applied_operations,
            "skipped_operations": self.skipped_operations,
            "safety_warnings": self.safety_warnings,
            # rollback_snapshot is returned but kept opaque (base64 payloads).
            "rollback_snapshot": self.rollback_snapshot,
            "dry_run": self.dry_run,
        }


class SafeChangeApplier:
    def __init__(
        self,
        *,
        workspace_manager: SecureWorkspaceManager,
        handle: WorkspaceHandle,
        db=None,
        max_files: int | None = None,
        max_diff_bytes: int | None = None,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.handle = handle
        self.audit = AuditService(db) if db is not None else None
        self.max_files = max_files or settings.change_apply_max_files
        self.max_diff_bytes = max_diff_bytes or settings.change_apply_max_diff_kb * 1024

    # -- public API ------------------------------------------------------------

    def apply(
        self,
        plan: Any,
        *,
        dry_run: bool = True,
        organization_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> ApplyResult:
        changes = plan.changes if hasattr(plan, "changes") else plan
        if not isinstance(changes, list):
            raise AppError("Change plan must provide a list of changes.")

        self._audit(organization_id, actor_user_id, "change_apply_started", {"dry_run": dry_run})
        try:
            # Workspace branch must be a safe, isolated branch (never main/protected).
            if not self.handle.branch_name or not self.workspace_manager.validate_branch_name(
                self.handle.branch_name, self.handle.base_branch
            ):
                raise AppError(
                    "Refusing to apply changes: workspace is not on an isolated "
                    "'codedna/ai/...' branch (protected-branch mutation blocked)."
                )

            plans, applied_ops, skipped_ops, warnings = self._compute(changes)

            if len(plans) > self.max_files:
                raise AppError(f"Change touches {len(plans)} files, above the limit of {self.max_files}.")

            diff_bytes = sum(p["new_bytes"] for p in plans.values())
            if diff_bytes > self.max_diff_bytes:
                raise AppError(
                    f"Change diff is {diff_bytes} bytes, above the limit of {self.max_diff_bytes} bytes."
                )

            patch_preview = self._patch_preview(plans)
            files_changed = [rel for rel, p in plans.items() if p["changed"]]

            rollback_snapshot: dict = {}
            if not dry_run:
                rollback_snapshot = self._write(plans)

            result = ApplyResult(
                files_changed=files_changed,
                patch_preview=patch_preview,
                applied_operations=applied_ops,
                skipped_operations=skipped_ops,
                safety_warnings=warnings,
                rollback_snapshot=rollback_snapshot,
                dry_run=dry_run,
            )
            self._audit(
                organization_id,
                actor_user_id,
                "change_apply_completed",
                {
                    "dry_run": dry_run,
                    "files_changed": files_changed,
                    "applied": len(applied_ops),
                    "skipped": len(skipped_ops),
                },
            )
            logger.info(
                "change_apply_completed",
                extra={"dry_run": dry_run, "files_changed": len(files_changed)},
            )
            return result
        except Exception as exc:  # noqa: BLE001
            logger.warning("change_apply_failed", extra={"error": str(exc)[:500]})
            self._audit(organization_id, actor_user_id, "change_apply_failed", {"error": str(exc)[:300]})
            raise

    def rollback(
        self,
        rollback_snapshot: dict,
        *,
        organization_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> list[str]:
        restored: list[str] = []
        for rel, record in rollback_snapshot.items():
            abs_path = self.workspace_manager.resolve_path(self.handle, rel)
            if record.get("existed"):
                data = base64.b64decode(record["content_b64"])
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_bytes(data)
            else:
                if abs_path.exists():
                    abs_path.unlink()
            restored.append(rel)
        self._audit(
            organization_id, actor_user_id, "change_apply_rolled_back", {"restored": restored}
        )
        logger.info("change_apply_rolled_back", extra={"restored": len(restored)})
        return restored

    # -- computation -----------------------------------------------------------

    def _compute(self, changes: list[dict]) -> tuple[dict, list[dict], list[dict], list[str]]:
        plans: dict[str, dict] = {}
        applied_ops: list[dict] = []
        skipped_ops: list[dict] = []
        warnings: list[str] = []

        for change in changes:
            rel = str(change.get("path", "")).strip()
            if not rel:
                skipped_ops.append({"path": "", "reason": "missing path"})
                continue
            # Hard safety: traversal/absolute/forbidden paths raise immediately.
            abs_path = self.workspace_manager.resolve_path(self.handle, rel)

            if rel not in plans:
                existed = abs_path.exists()
                original = abs_path.read_bytes() if existed else None
                content = original.decode("utf-8", errors="replace") if original is not None else None
                plans[rel] = {
                    "abs_path": abs_path,
                    "existed": existed,
                    "original": original,
                    "content": content,
                    "deleted": False,
                    "touched": False,
                    "changed": False,
                    "new_bytes": 0,
                }
            state = plans[rel]

            for op in change.get("operations", []):
                op_type = str(op.get("type", "")).lower()
                if op_type not in SUPPORTED_OPERATIONS:
                    skipped_ops.append({"path": rel, "type": op_type, "reason": "unsupported operation"})
                    warnings.append(f"Unsupported operation '{op_type}' on {rel} was skipped.")
                    continue
                ok, message = self._apply_op(state, op_type, op)
                if ok:
                    applied_ops.append({"path": rel, "type": op_type})
                else:
                    skipped_ops.append({"path": rel, "type": op_type, "reason": message})
                    warnings.append(f"{op_type} on {rel} skipped: {message}")

        # Finalize each file: compute changed flag + new byte size.
        for rel, state in plans.items():
            if state["deleted"]:
                state["changed"] = state["existed"]
                state["new_bytes"] = 0
            else:
                new = state["content"]
                if new is None:
                    state["changed"] = False
                    state["new_bytes"] = 0
                else:
                    new_bytes = new.encode("utf-8")
                    state["new_bytes"] = len(new_bytes)
                    state["changed"] = (state["original"] is None) or (new_bytes != state["original"])
        return plans, applied_ops, skipped_ops, warnings

    def _apply_op(self, state: dict, op_type: str, op: dict) -> tuple[bool, str]:
        content = op.get("content", "")
        target = op.get("target", "")

        if op_type == "create_file":
            state["content"] = content
            state["deleted"] = False
            state["touched"] = True
            return True, ""
        if op_type == "replace_file":
            state["content"] = content
            state["deleted"] = False
            state["touched"] = True
            return True, ""
        if op_type == "delete_file":
            state["deleted"] = True
            state["touched"] = True
            return True, ""

        # The remaining ops need existing text content.
        if state["content"] is None or state["deleted"]:
            return False, "target file does not exist"
        body = state["content"]
        if not target or target not in body:
            return False, "anchor/target text not found"

        idx = body.find(target)
        if op_type == "insert_after":
            cut = idx + len(target)
            state["content"] = body[:cut] + content + body[cut:]
        elif op_type == "insert_before":
            state["content"] = body[:idx] + content + body[idx:]
        elif op_type == "replace_block":
            state["content"] = body[:idx] + content + body[idx + len(target):]
        else:  # pragma: no cover - guarded by SUPPORTED_OPERATIONS
            return False, "unsupported operation"
        state["touched"] = True
        return True, ""

    def _patch_preview(self, plans: dict) -> str:
        chunks: list[str] = []
        for rel, state in plans.items():
            if not state["changed"]:
                continue
            old_text = state["original"].decode("utf-8", errors="replace") if state["original"] else ""
            old = old_text.splitlines(keepends=True)
            new = [] if state["deleted"] else (state["content"] or "").splitlines(keepends=True)
            diff = difflib.unified_diff(
                old,
                new,
                fromfile=f"a/{rel}" if state["existed"] else "/dev/null",
                tofile=f"b/{rel}" if not state["deleted"] else "/dev/null",
            )
            chunks.append("".join(diff))
        return "\n".join(c for c in chunks if c.strip())

    def _write(self, plans: dict) -> dict:
        rollback: dict = {}
        for rel, state in plans.items():
            if not state["changed"]:
                continue
            abs_path: Path = state["abs_path"]
            rollback[rel] = {
                "existed": state["existed"],
                "content_b64": base64.b64encode(state["original"]).decode("ascii") if state["original"] is not None else None,
            }
            if state["deleted"]:
                if abs_path.exists():
                    abs_path.unlink()
            else:
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_text(state["content"], encoding="utf-8")
        return rollback

    # -- audit -----------------------------------------------------------------

    def _audit(
        self,
        organization_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
        action: str,
        metadata: dict,
    ) -> None:
        if self.audit is None or organization_id is None:
            return
        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type="workspace",
            target_id=self.handle.workspace_id,
            metadata=metadata,
        )
