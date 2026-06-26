from __future__ import annotations
import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class DraftPullRequestRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    engineering_request_id: uuid.UUID
    repository_id: uuid.UUID | None
    branch_name: str
    base_branch: str | None
    title: str
    body: str | None
    commit_plan: list
    labels: list
    status: str
    is_pushed: bool
    human_approval_required: bool
    github_pr_number: int | None
    github_pr_url: str | None
    # Transient: true when the branch/PR already existed and was reused (idempotent).
    already_exists: bool = False
    created_at: datetime
    updated_at: datetime
