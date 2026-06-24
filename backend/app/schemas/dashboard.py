from __future__ import annotations
from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_repositories: int
    total_scans: int
    completed_scans: int
    failed_scans: int
    high_risk_scans: int
    average_risk_score: float


class DashboardRecentScan(BaseModel):
    scan_id: str
    repository_id: str
    repository: str
    pr_number: int
    title: str | None
    status: str
    risk_score: float | None
    risk_level: str | None
    findings_count: int
    created_at: str


class DashboardResponse(BaseModel):
    summary: DashboardSummary
    recent_scans: list[DashboardRecentScan]
