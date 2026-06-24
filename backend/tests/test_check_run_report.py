from __future__ import annotations

from app.services.check_run_report import CHECK_RUN_OUTPUT_TITLE, CheckRunReportBuilder


def test_check_run_conclusion_fails_for_company_or_architecture_violations() -> None:
    builder = CheckRunReportBuilder()

    assert (
        builder.conclusion_for_report(
            {
                "company_rule_violations": [{"title": "No console logs"}],
                "architecture_violations": [],
                "ai": {"enabled": False},
            }
        )
        == "failure"
    )
    assert (
        builder.conclusion_for_report(
            {
                "company_rule_violations": [],
                "architecture_violations": [{"title": "Layer violation"}],
                "ai": {"enabled": True},
            }
        )
        == "failure"
    )


def test_check_run_conclusion_is_neutral_when_ai_skipped_and_no_findings() -> None:
    builder = CheckRunReportBuilder()

    conclusion = builder.conclusion_for_report(
        {
            "semgrep_findings": [],
            "ai_findings": [],
            "company_rule_violations": [],
            "architecture_violations": [],
            "ai": {"enabled": False},
        }
    )

    assert conclusion == "neutral"


def test_check_run_conclusion_succeeds_when_no_rule_violations_exist() -> None:
    builder = CheckRunReportBuilder()

    conclusion = builder.conclusion_for_report(
        {
            "semgrep_findings": [{"title": "Semgrep informational finding"}],
            "ai_findings": [],
            "company_rule_violations": [],
            "architecture_violations": [],
            "ai": {"enabled": True},
        }
    )

    assert conclusion == "success"


def test_completed_check_run_output_includes_risk_counts_and_top_violations() -> None:
    builder = CheckRunReportBuilder()

    output = builder.build_completed_output(
        {
            "risk": {"score": 62.5, "level": "high"},
            "semgrep_findings": [{"title": "Static issue"}],
            "ai_findings": [],
            "company_rule_violations": [
                {
                    "severity": "medium",
                    "path": "src/app.js",
                    "line": 12,
                    "title": "No Console Logs",
                }
            ],
            "architecture_violations": [],
        }
    )

    assert output["title"] == CHECK_RUN_OUTPUT_TITLE
    assert "Risk score: **62.5/100**" in output["summary"]
    assert "Risk level: **HIGH**" in output["summary"]
    assert "Findings count: **2**" in output["summary"]
    assert "`src/app.js:12`" in output["summary"]
    assert "No Console Logs" in output["summary"]

