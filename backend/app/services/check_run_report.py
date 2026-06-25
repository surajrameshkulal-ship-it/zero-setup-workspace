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
        level = str(risk.get("level", "unknown"))
        score = risk.get("score", 0)
        total_findings = self.findings_count(report)

        summary_lines: list[str] = [
            "## Summary",
            self._verdict_line(report, total_findings),
            "",
            "### Risk",
            f"{self._risk_emoji(level)} Risk score: **{score}/100**",
            f"Risk level: **{level.upper()}**",
            f"Findings count: **{total_findings}**",
            "",
            "### Findings",
        ]
        summary_lines.extend(self._findings_breakdown_lines(report))

        summary_lines.extend(["", "### Company Rules"])
        summary_lines.extend(
            self._violation_lines(
                report.get("company_rule_violations") or [],
                "No company rule violations detected.",
            )
        )

        summary_lines.extend(["", "### Architecture Notes"])
        summary_lines.extend(
            self._violation_lines(
                report.get("architecture_violations") or [],
                "No architecture violations detected.",
            )
        )

        summary_lines.extend(self.ai_review_lines(report))

        return {
            "title": CHECK_RUN_OUTPUT_TITLE,
            "summary": "\n".join(summary_lines),
        }

    def _verdict_line(self, report: dict[str, Any], total_findings: int) -> str:
        conclusion = self.conclusion_for_report(report)
        if conclusion == "failure":
            return (
                "🔴 **Changes requested** — company or architecture rules were "
                "violated. Resolve these before merging."
            )
        if conclusion == "neutral":
            return "⚪ **No issues detected** — no findings, and AI review was not run."
        if total_findings > 0:
            return (
                f"🟡 **Reviewed** — {total_findings} finding(s) to consider; "
                "no blocking rule violations."
            )
        return "✅ **Looks good** — no findings and no rule violations."

    def _risk_emoji(self, level: str) -> str:
        return {
            "low": "🟢",
            "medium": "🟡",
            "high": "🟠",
            "critical": "🔴",
        }.get(level.lower(), "⚪")

    def _findings_breakdown_lines(self, report: dict[str, Any]) -> list[str]:
        counts = [
            ("Semgrep", len(report.get("semgrep_findings") or [])),
            ("AI", len(report.get("ai_findings") or [])),
            ("Company rules", len(report.get("company_rule_violations") or [])),
            ("Architecture", len(report.get("architecture_violations") or [])),
        ]
        if sum(count for _, count in counts) == 0:
            return ["✅ No findings detected."]
        return [f"- {name}: **{count}**" for name, count in counts]

    def _violation_lines(self, violations: list[dict[str, Any]], empty_message: str) -> list[str]:
        if not violations:
            return [f"✅ {empty_message}"]
        lines: list[str] = []
        for finding in violations[:5]:
            location = finding.get("path") or "repository"
            if finding.get("line"):
                location = f"{location}:{finding['line']}"
            severity = str(finding.get("severity", "medium")).upper()
            title = finding.get("title", "Finding")
            lines.append(f"- ⚠️ **{severity}** — {title} (`{location}`)")
        remaining = len(violations) - 5
        if remaining > 0:
            lines.append(f"- …and {remaining} more.")
        return lines

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

    def ai_review_lines(self, report: dict[str, Any]) -> list[str]:
        ai = report.get("ai") or {}
        review = report.get("ai_review") or {}
        if not review:
            return ["", "### AI Review", "- AI review was not included in this scan report."]

        lines = ["", "### AI Review"]
        if ai.get("skipped"):
            lines.append(f"- {self._truncate(str(review.get('summary') or 'AI review skipped.'), 700)}")
            return lines

        section_map = [
            ("Summary", [review.get("summary")] if review.get("summary") else []),
            ("Security issues", review.get("security_issues") or []),
            ("Bug risks", review.get("bug_risks") or []),
            ("Performance concerns", review.get("performance_concerns") or []),
            ("Maintainability suggestions", review.get("maintainability_suggestions") or []),
            ("Recommended action", [review.get("recommended_action")] if review.get("recommended_action") else []),
        ]
        for title, values in section_map:
            lines.append(f"**{title}**")
            if values:
                for value in values[:3]:
                    lines.append(f"- {self._truncate(str(value), 700)}")
            else:
                lines.append("- None identified.")
        return lines

    def _truncate(self, value: str, max_chars: int) -> str:
        if len(value) <= max_chars:
            return value
        return f"{value[:max_chars]}..."
