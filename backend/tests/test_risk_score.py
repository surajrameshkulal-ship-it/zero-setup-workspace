from __future__ import annotations
from app.services.risk_score import RiskScoreEngine


def test_risk_score_weights_findings_and_churn() -> None:
    result = RiskScoreEngine().calculate(
        semgrep_findings=[{"severity": "high"}],
        ai_findings=[{"severity": "medium"}],
        company_rule_violations=[{"severity": "low"}],
        architecture_violations=[{"severity": "critical"}],
        files_changed=3,
        lines_added=120,
        lines_deleted=30,
    )

    assert result["score"] > 50
    assert result["level"] == "high"
    assert result["breakdown"]["finding_count"] == 4


def test_risk_score_caps_at_100() -> None:
    result = RiskScoreEngine().calculate(
        semgrep_findings=[{"severity": "critical"} for _ in range(10)],
        ai_findings=[],
        company_rule_violations=[],
        architecture_violations=[],
        files_changed=1,
        lines_added=1,
        lines_deleted=1,
    )

    assert result["score"] == 100
    assert result["level"] == "critical"

