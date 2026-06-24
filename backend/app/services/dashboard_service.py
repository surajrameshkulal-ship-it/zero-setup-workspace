from __future__ import annotations
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.models.scan import PullRequestScan, RiskLevel, ScanStatus
from app.schemas.dashboard import DashboardRecentScan, DashboardResponse, DashboardSummary


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def summary(self, organization_id: uuid.UUID) -> DashboardResponse:
        total_repositories = self.db.scalar(
            select(func.count(Repository.id)).where(Repository.organization_id == organization_id)
        ) or 0
        total_scans = self.db.scalar(
            select(func.count(PullRequestScan.id)).where(PullRequestScan.organization_id == organization_id)
        ) or 0
        completed_scans = self.db.scalar(
            select(func.count(PullRequestScan.id)).where(
                PullRequestScan.organization_id == organization_id,
                PullRequestScan.status == ScanStatus.COMPLETED,
            )
        ) or 0
        failed_scans = self.db.scalar(
            select(func.count(PullRequestScan.id)).where(
                PullRequestScan.organization_id == organization_id,
                PullRequestScan.status == ScanStatus.FAILED,
            )
        ) or 0
        high_risk_scans = self.db.scalar(
            select(func.count(PullRequestScan.id)).where(
                PullRequestScan.organization_id == organization_id,
                PullRequestScan.status == ScanStatus.COMPLETED,
                PullRequestScan.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]),
            )
        ) or 0
        average_risk_score = self.db.scalar(
            select(func.coalesce(func.avg(PullRequestScan.risk_score), 0)).where(
                PullRequestScan.organization_id == organization_id,
                PullRequestScan.status == ScanStatus.COMPLETED,
            )
        ) or 0

        recent_rows = self.db.execute(
            select(PullRequestScan, Repository.full_name)
            .join(Repository, Repository.id == PullRequestScan.repository_id)
            .where(PullRequestScan.organization_id == organization_id)
            .order_by(PullRequestScan.created_at.desc())
            .limit(10)
        ).all()

        recent_scans = [
            DashboardRecentScan(
                scan_id=str(scan.id),
                repository_id=str(scan.repository_id),
                repository=repository_full_name,
                pr_number=scan.github_pr_number,
                title=scan.title,
                status=scan.status.value,
                risk_score=scan.risk_score,
                risk_level=scan.risk_level.value if scan.risk_level else None,
                findings_count=scan.findings_count,
                created_at=scan.created_at.isoformat(),
            )
            for scan, repository_full_name in recent_rows
        ]

        return DashboardResponse(
            summary=DashboardSummary(
                total_repositories=int(total_repositories),
                total_scans=int(total_scans),
                completed_scans=int(completed_scans),
                failed_scans=int(failed_scans),
                high_risk_scans=int(high_risk_scans),
                average_risk_score=round(float(average_risk_score), 2),
            ),
            recent_scans=recent_scans,
        )
