from __future__ import annotations
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.scan import RiskLevel, ScanStatus
from app.schemas.common import ORMModel


class ManualScanRequest(BaseModel):
    github_pr_number: int = Field(..., gt=0)
    head_sha: str = Field(..., min_length=7, max_length=64)
    base_sha: str | None = Field(default=None, min_length=7, max_length=64)
    title: str | None = Field(default=None, max_length=512)
    github_pr_url: str | None = Field(default=None, max_length=1024)


class ScanRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    repository_id: uuid.UUID
    github_pr_number: int
    github_pr_url: str | None
    title: str | None
    head_sha: str
    base_sha: str | None
    github_check_run_id: int | None
    status: ScanStatus
    trigger: str
    files_changed: int
    lines_added: int
    lines_deleted: int
    risk_score: float | None
    risk_level: RiskLevel | None
    summary: str | None
    failure_reason: str | None
    semgrep_findings: list
    ai_findings: list
    company_rule_violations: list
    architecture_violations: list
    report: dict
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ScanListItem(ORMModel):
    id: uuid.UUID
    repository_id: uuid.UUID
    repository_full_name: str | None
    github_pr_number: int
    github_pr_url: str | None
    title: str | None
    status: ScanStatus
    risk_score: float | None
    risk_level: RiskLevel | None
    findings_count: int
    created_at: datetime
    completed_at: datetime | None


class ScanDetail(ScanRead):
    repository_full_name: str | None
    findings_count: int
    ai_review: dict | None
    ai_review_markdown: str | None


class ScanQueuedResponse(BaseModel):
    scan_id: uuid.UUID
    status: ScanStatus
