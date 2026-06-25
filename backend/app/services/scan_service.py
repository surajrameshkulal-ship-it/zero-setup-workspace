from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import IntegrationError, NotFoundError
from app.integrations.github import GitHubIntegration
from app.models.rule import ArchitectureRule, CompanyRule
from app.models.scan import PullRequestScan, RiskLevel, ScanStatus
from app.services.ai_review.ai_review_service import AIReviewService
from app.services.architecture_checker import ArchitectureRuleChecker
from app.services.audit_service import AuditService
from app.services.check_run_report import CHECK_RUN_NAME, CheckRunReportBuilder
from app.services.comment_formatter import PRCommentFormatter
from app.services.risk_score import RiskScoreEngine
from app.services.rule_engine import CompanyRuleEngine
from app.services.semgrep_service import SemgrepService

logger = logging.getLogger(__name__)


class PullRequestScanService:
    def __init__(
        self,
        db: Session,
        *,
        github: GitHubIntegration | None = None,
        semgrep: SemgrepService | None = None,
        ai_review: AIReviewService | None = None,
    ) -> None:
        self.db = db
        self.github = github or GitHubIntegration()
        self.semgrep = semgrep or SemgrepService()
        self.ai_review = ai_review or AIReviewService()
        self.company_rules = CompanyRuleEngine()
        self.architecture_checker = ArchitectureRuleChecker()
        self.risk_score = RiskScoreEngine()
        self.comment_formatter = PRCommentFormatter()
        self.check_run_report = CheckRunReportBuilder()

    def get_for_org(self, scan_id: uuid.UUID, organization_id: uuid.UUID) -> PullRequestScan:
        scan = self.db.scalar(
            select(PullRequestScan)
            .options(joinedload(PullRequestScan.repository))
            .where(
                PullRequestScan.id == scan_id,
                PullRequestScan.organization_id == organization_id,
            )
        )
        if not scan:
            raise NotFoundError("Scan not found")
        return scan

    def list_for_org(
        self,
        organization_id: uuid.UUID,
        *,
        repository_id: uuid.UUID | None = None,
        status: ScanStatus | None = None,
        risk_level: RiskLevel | None = None,
        limit: int = 50,
    ) -> list[PullRequestScan]:
        query = (
            select(PullRequestScan)
            .options(joinedload(PullRequestScan.repository))
            .where(PullRequestScan.organization_id == organization_id)
            .order_by(PullRequestScan.created_at.desc())
            .limit(limit)
        )
        if repository_id:
            query = query.where(PullRequestScan.repository_id == repository_id)
        if status:
            query = query.where(PullRequestScan.status == status)
        if risk_level:
            query = query.where(PullRequestScan.risk_level == risk_level)

        return list(
            self.db.scalars(query)
        )

    def run(self, scan_id: uuid.UUID, *, mark_failed_on_error: bool = True) -> PullRequestScan:
        scan = self.db.scalar(select(PullRequestScan).where(PullRequestScan.id == scan_id))
        if not scan:
            raise NotFoundError("Scan not found")
        repository = scan.repository
        if not repository.github_installation:
            raise NotFoundError("Repository is not linked to a GitHub installation")

        try:
            self._mark_check_run_in_progress(scan)
            scan.status = ScanStatus.RUNNING
            scan.started_at = datetime.now(timezone.utc)
            scan.failure_reason = None
            self.db.commit()
            logger.info(
                "scan_started",
                extra={
                    "scan_id": str(scan.id),
                    "repository": repository.full_name,
                    "pr_number": scan.github_pr_number,
                    "head_sha": scan.head_sha,
                    "github_check_run_id": scan.github_check_run_id,
                },
            )

            files = self.github.get_pull_request_files(
                installation_id=repository.github_installation.installation_id,
                owner=repository.owner,
                repo=repository.name,
                pr_number=scan.github_pr_number,
                head_sha=scan.head_sha,
            )
            files_changed = len(files)
            lines_added = sum(file.additions for file in files)
            lines_deleted = sum(file.deletions for file in files)

            semgrep_findings = self.semgrep.scan_files(files)
            ai_review = self.ai_review.review_files(files)
            ai_findings = ai_review.get("findings", [])
            company_rule_violations = self.company_rules.check(files, self._company_rules(scan.organization_id))
            architecture_violations = self.architecture_checker.check(files, self._architecture_rules(scan.organization_id))
            risk = self.risk_score.calculate(
                semgrep_findings=semgrep_findings,
                ai_findings=ai_findings,
                company_rule_violations=company_rule_violations,
                architecture_violations=architecture_violations,
                files_changed=files_changed,
                lines_added=lines_added,
                lines_deleted=lines_deleted,
            )
            summary = self._summary(ai_review, risk, semgrep_findings, company_rule_violations, architecture_violations)
            report = {
                "scan_id": str(scan.id),
                "repository": repository.full_name,
                "pr_number": scan.github_pr_number,
                "head_sha": scan.head_sha,
                "base_sha": scan.base_sha,
                "files_changed": files_changed,
                "lines_added": lines_added,
                "lines_deleted": lines_deleted,
                "summary": summary,
                "risk": risk,
                "semgrep_findings": semgrep_findings,
                "ai_findings": ai_findings,
                "ai_review": ai_review.get("review", {}),
                "ai_review_markdown": ai_review.get("markdown"),
                "company_rule_violations": company_rule_violations,
                "architecture_violations": architecture_violations,
                "ai": {
                    "provider": ai_review.get("provider"),
                    "model": ai_review.get("model"),
                    "enabled": ai_review.get("enabled"),
                    "skipped": ai_review.get("skipped", False),
                    "skip_reason": ai_review.get("skip_reason"),
                },
            }
            report["github_check_run_id"] = scan.github_check_run_id

            scan.status = ScanStatus.COMPLETED
            scan.completed_at = datetime.now(timezone.utc)
            scan.files_changed = files_changed
            scan.lines_added = lines_added
            scan.lines_deleted = lines_deleted
            scan.risk_score = float(risk["score"])
            scan.risk_level = RiskLevel(risk["level"])
            scan.summary = summary
            scan.semgrep_findings = semgrep_findings
            scan.ai_findings = ai_findings
            scan.company_rule_violations = company_rule_violations
            scan.architecture_violations = architecture_violations
            scan.report = report

            self._complete_check_run(scan, report)

            comment = self.comment_formatter.format(report)
            self.github.create_pr_comment(
                installation_id=repository.github_installation.installation_id,
                owner=repository.owner,
                repo=repository.name,
                pr_number=scan.github_pr_number,
                body=comment,
            )
            AuditService(self.db).log(
                organization_id=scan.organization_id,
                action="scan.completed",
                target_type="pull_request_scan",
                target_id=str(scan.id),
                metadata={"risk_score": scan.risk_score, "risk_level": scan.risk_level.value},
            )
            self.db.commit()
            self.db.refresh(scan)
            return scan
        except Exception as exc:
            logger.exception("scan_failed", extra={"scan_id": str(scan.id)})
            self.db.rollback()
            if mark_failed_on_error:
                self.mark_failed(scan.id, str(exc))
            raise

    def mark_failed(self, scan_id: uuid.UUID, failure_reason: str) -> PullRequestScan:
        scan = self.db.scalar(select(PullRequestScan).where(PullRequestScan.id == scan_id))
        if not scan:
            raise NotFoundError("Scan not found")

        scan.status = ScanStatus.FAILED
        scan.failure_reason = failure_reason
        scan.completed_at = datetime.now(timezone.utc)
        self._fail_check_run(scan, failure_reason)
        AuditService(self.db).log(
            organization_id=scan.organization_id,
            action="scan.failed",
            target_type="pull_request_scan",
            target_id=str(scan.id),
            metadata={"error": failure_reason},
        )
        self.db.commit()
        self.db.refresh(scan)
        return scan

    def _mark_check_run_in_progress(self, scan: PullRequestScan) -> None:
        repository = scan.repository
        installation_id = repository.github_installation.installation_id
        output = self.check_run_report.build_started_output(
            pr_number=scan.github_pr_number,
            head_sha=scan.head_sha,
        )
        logger.info(
            "check_run_start_requested",
            extra={
                "scan_id": str(scan.id),
                "repository": repository.full_name,
                "pr_number": scan.github_pr_number,
                "head_sha": scan.head_sha,
                "base_sha": scan.base_sha,
                "existing_check_run_id": scan.github_check_run_id,
            },
        )

        if scan.github_check_run_id:
            self.github.update_check_run(
                installation_id=installation_id,
                owner=repository.owner,
                repo=repository.name,
                check_run_id=scan.github_check_run_id,
                status="in_progress",
                output=output,
            )
            logger.info(
                "check_run_marked_in_progress",
                extra={
                    "scan_id": str(scan.id),
                    "check_run_id": scan.github_check_run_id,
                    "repository": repository.full_name,
                    "head_sha": scan.head_sha,
                },
            )
            return

        check_run = self.github.create_check_run(
            installation_id=installation_id,
            owner=repository.owner,
            repo=repository.name,
            name=CHECK_RUN_NAME,
            head_sha=scan.head_sha,
            status="in_progress",
            output=output,
        )
        check_run_id = check_run.get("id")
        if not check_run_id:
            logger.error(
                "check_run_create_missing_id",
                extra={
                    "scan_id": str(scan.id),
                    "repository": repository.full_name,
                    "head_sha": scan.head_sha,
                    "github_response": check_run,
                },
            )
            raise IntegrationError("GitHub check run response did not include an id")

        scan.github_check_run_id = int(check_run_id)
        self.db.commit()
        self.db.refresh(scan)
        logger.info(
            "check_run_created",
            extra={
                "scan_id": str(scan.id),
                "check_run_id": scan.github_check_run_id,
                "repository": repository.full_name,
                "head_sha": scan.head_sha,
                "db_committed": True,
            },
        )

    def _complete_check_run(self, scan: PullRequestScan, report: dict) -> None:
        if not scan.github_check_run_id:
            logger.warning("check_run_complete_skipped_missing_id", extra={"scan_id": str(scan.id)})
            return

        repository = scan.repository
        conclusion = self.check_run_report.conclusion_for_report(report)
        output = self.check_run_report.build_completed_output(report)
        self.github.update_check_run(
            installation_id=repository.github_installation.installation_id,
            owner=repository.owner,
            repo=repository.name,
            check_run_id=scan.github_check_run_id,
            status="completed",
            conclusion=conclusion,
            completed_at=self._github_timestamp(),
            output=output,
        )
        logger.info(
            "check_run_completed",
            extra={
                "scan_id": str(scan.id),
                "check_run_id": scan.github_check_run_id,
                "repository": repository.full_name,
                "head_sha": scan.head_sha,
                "conclusion": conclusion,
            },
        )

    def _fail_check_run(self, scan: PullRequestScan, failure_reason: str) -> None:
        if not scan.github_check_run_id:
            return

        try:
            repository = scan.repository
            self.github.update_check_run(
                installation_id=repository.github_installation.installation_id,
                owner=repository.owner,
                repo=repository.name,
                check_run_id=scan.github_check_run_id,
                status="completed",
                conclusion="failure",
                completed_at=self._github_timestamp(),
                output=self.check_run_report.build_failed_output(failure_reason=failure_reason),
            )
            logger.info(
                "check_run_failed",
                extra={
                    "scan_id": str(scan.id),
                    "check_run_id": scan.github_check_run_id,
                    "repository": repository.full_name,
                },
            )
        except Exception:
            logger.exception(
                "check_run_failure_update_failed",
                extra={"scan_id": str(scan.id), "check_run_id": scan.github_check_run_id},
            )

    def _github_timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _company_rules(self, organization_id: uuid.UUID) -> list[CompanyRule]:
        return list(
            self.db.scalars(
                select(CompanyRule).where(
                    CompanyRule.organization_id == organization_id,
                    CompanyRule.is_active.is_(True),
                )
            )
        )

    def _architecture_rules(self, organization_id: uuid.UUID) -> list[ArchitectureRule]:
        return list(
            self.db.scalars(
                select(ArchitectureRule).where(
                    ArchitectureRule.organization_id == organization_id,
                    ArchitectureRule.is_active.is_(True),
                )
            )
        )

    def _summary(
        self,
        ai_review: dict,
        risk: dict,
        semgrep_findings: list[dict],
        company_rule_violations: list[dict],
        architecture_violations: list[dict],
    ) -> str:
        parts = [
            ai_review.get("summary") or "Review completed.",
            f"Risk level is {risk['level']} with score {risk['score']}/100.",
            f"Semgrep findings: {len(semgrep_findings)}.",
            f"Company rule violations: {len(company_rule_violations)}.",
            f"Architecture violations: {len(architecture_violations)}.",
        ]
        return " ".join(parts)
