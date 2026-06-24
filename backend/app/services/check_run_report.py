from __future__ import annotations

from typing import Any


CHECK_RUN_NAME = "CodeDNA AI"
CHECK_RUN_OUTPUT_TITLE = "CodeDNA AI Scan Report"


class CheckRunReportBuilder:
    def build_started_output(self, *, pr_number: int, head_sha: str) -> dict[str, str]:
        return {
            "title": CHECK_RUN_OUTPUT_TITLE,
            "summary": (
                f"CodeDNA AI scan is in progress for PR #{pr_number} "
                f"at `{head_sha[:12]}`."
            ),
        }

    def conclusion_for_report(self, report: dict[str, Any]) -> str:
        company_violations = report.get("company_rule_violations") or []
        architecture_violations = report.get("architecture_violations") or []
        if company_violations or architecture_violations:
            return "failure"

        total_findings = self.findings_count(report)
        ai_enabled = bool((report.get("ai") or {}).get("enabled"))
        if not ai_enabled and total_findings == 0:
            return "neutral"

        return "success"

    def build_completed_output(self, report: dict[str, Any]) -> dict[str, str]:
        risk = report.get("risk") or {}
        top_violations = self.top_violations(report)
        summary_lines = [
            f"Risk score: **{risk.get('score', 0)}/100**",
            f"Risk level: **{str(risk.get('level', 'unknown')).upper()}**",
            f"Findings count: **{self.findings_count(report)}**",
            "",
            "### Top Violations",
        ]
        if top_violations:
            for finding in top_violations:
                location = finding.get("path") or "repository"
                if finding.get("line"):
                    location = f"{location}:{finding['line']}"
                summary_lines.append(
                    f"- **{str(finding.get('severity', 'medium')).upper()}** `{location}`: "
                    f"{finding.get('title', 'Finding')}"
                )
        else:
            summary_lines.append("- No company or architecture rule violations detected.")

        return {
            "title": CHECK_RUN_OUTPUT_TITLE,
            "summary": "\n".join(summary_lines),
        }

    def build_failed_output(self, *, failure_reason: str) -> dict[str, str]:
        return {
            "title": "CodeDNA AI Scan Failed",
            "summary": f"The scan failed before producing a complete report.\n\nError: {failure_reason[:4000]}",
        }

    def findings_count(self, report: dict[str, Any]) -> int:
        return sum(
            len(report.get(key) or [])
            for key in (
                "semgrep_findings",
                "ai_findings",
                "company_rule_violations",
                "architecture_violations",
            )
        )

    def top_violations(self, report: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
        violations = (report.get("company_rule_violations") or []) + (report.get("architecture_violations") or [])
        return violations[:limit]
