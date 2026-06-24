from __future__ import annotations
from app.models.scan import RiskLevel


SEVERITY_WEIGHTS = {
    "critical": 25,
    "error": 20,
    "high": 15,
    "warning": 8,
    "medium": 8,
    "low": 3,
    "info": 1,
}


class RiskScoreEngine:
    def calculate(
        self,
        *,
        semgrep_findings: list[dict],
        ai_findings: list[dict],
        company_rule_violations: list[dict],
        architecture_violations: list[dict],
        files_changed: int,
        lines_added: int,
        lines_deleted: int,
    ) -> dict:
        all_findings = semgrep_findings + ai_findings + company_rule_violations + architecture_violations
        finding_score = sum(self._finding_weight(finding) for finding in all_findings)
        churn_score = min(15, files_changed * 1.5 + (lines_added + lines_deleted) / 120)
        architecture_bonus = min(15, len(architecture_violations) * 5)
        company_bonus = min(12, len(company_rule_violations) * 4)
        raw_score = finding_score + churn_score + architecture_bonus + company_bonus
        score = min(100, round(raw_score, 2))
        level = self._level(score)
        return {
            "score": score,
            "level": level.value,
            "breakdown": {
                "finding_score": round(finding_score, 2),
                "churn_score": round(churn_score, 2),
                "architecture_bonus": round(architecture_bonus, 2),
                "company_rule_bonus": round(company_bonus, 2),
                "finding_count": len(all_findings),
            },
        }

    def _finding_weight(self, finding: dict) -> float:
        severity = str(finding.get("severity", "medium")).lower()
        return SEVERITY_WEIGHTS.get(severity, SEVERITY_WEIGHTS["medium"])

    def _level(self, score: float) -> RiskLevel:
        if score >= 80:
            return RiskLevel.CRITICAL
        if score >= 50:
            return RiskLevel.HIGH
        if score >= 25:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

