from __future__ import annotations
class PRCommentFormatter:
    def format(self, report: dict) -> str:
        risk = report.get("risk", {})
        summary = report.get("summary") or "CodeDNA AI completed the pull request review."
        sections = [
            "## CodeDNA AI Review",
            "",
            f"**Risk:** {risk.get('level', 'unknown').upper()} ({risk.get('score', 0)}/100)",
            "",
            summary,
            "",
            self._metrics(report),
            self._findings("Semgrep", report.get("semgrep_findings", [])),
            self._findings("AI Review", report.get("ai_findings", [])),
            self._findings("Company Rules", report.get("company_rule_violations", [])),
            self._findings("Architecture Rules", report.get("architecture_violations", [])),
        ]
        return "\n".join(section for section in sections if section).strip()

    def _metrics(self, report: dict) -> str:
        return "\n".join(
            [
                "### Change Metrics",
                "",
                f"- Files changed: {report.get('files_changed', 0)}",
                f"- Lines added: {report.get('lines_added', 0)}",
                f"- Lines deleted: {report.get('lines_deleted', 0)}",
            ]
        )

    def _findings(self, title: str, findings: list[dict]) -> str:
        if not findings:
            return f"### {title}\n\nNo findings."
        lines = [f"### {title}", ""]
        for finding in findings[:10]:
            location = finding.get("path") or "repository"
            if finding.get("line"):
                location = f"{location}:{finding['line']}"
            lines.extend(
                [
                    f"- **{str(finding.get('severity', 'medium')).upper()}** `{location}`: {finding.get('title', 'Finding')}",
                    f"  {finding.get('description', '')}",
                ]
            )
            if finding.get("recommendation"):
                lines.append(f"  Recommendation: {finding['recommendation']}")
        if len(findings) > 10:
            lines.append(f"- {len(findings) - 10} additional findings omitted from this comment; view the dashboard for full details.")
        return "\n".join(lines)

