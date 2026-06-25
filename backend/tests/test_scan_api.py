from __future__ import annotations


def test_scan_list_filters_and_hides_other_organizations(api_context) -> None:
    response = api_context.client.get("/api/v1/scans")

    assert response.status_code == 200
    payload = response.json()
    assert {item["id"] for item in payload} == {
        str(api_context.completed_scan.id),
        str(api_context.failed_scan.id),
    }
    assert all("organization_id" not in item for item in payload)

    completed = next(item for item in payload if item["id"] == str(api_context.completed_scan.id))
    assert completed["repository_id"] == str(api_context.repository.id)
    assert completed["repository_full_name"] == "acme/payments-api"
    assert completed["github_pr_number"] == 12
    assert completed["status"] == "completed"
    assert completed["risk_score"] == 72.5
    assert completed["risk_level"] == "high"
    assert completed["findings_count"] == 2

    filtered = api_context.client.get(
        "/api/v1/scans",
        params={
            "repository_id": str(api_context.repository.id),
            "status": "completed",
            "risk_level": "high",
        },
    )

    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()] == [str(api_context.completed_scan.id)]

    other_repository_filter = api_context.client.get(
        "/api/v1/scans",
        params={"repository_id": str(api_context.other_repository.id)},
    )

    assert other_repository_filter.status_code == 200
    assert other_repository_filter.json() == []


def test_scan_detail_is_scoped_to_current_organization(api_context) -> None:
    response = api_context.client.get(f"/api/v1/scans/{api_context.completed_scan.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(api_context.completed_scan.id)
    assert payload["repository_full_name"] == "acme/payments-api"
    assert payload["findings_count"] == 2
    assert payload["company_rule_violations"] == [{"title": "No console.log", "severity": "medium"}]
    assert payload["architecture_violations"] == [{"title": "No UI to DB import", "severity": "high"}]
    assert payload["github_check_run_id"] == 12345
    assert payload["ai_review"]["summary"] == "Review found logging concerns."
    assert payload["ai_review_markdown"] == "### Summary\n- Review found logging concerns."

    forbidden = api_context.client.get(f"/api/v1/scans/{api_context.other_scan.id}")

    assert forbidden.status_code == 404


def test_repository_scan_history_is_scoped_to_current_organization(api_context) -> None:
    response = api_context.client.get(f"/api/v1/repositories/{api_context.repository.id}/scans")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == [
        str(api_context.failed_scan.id),
        str(api_context.completed_scan.id),
    ]

    forbidden = api_context.client.get(f"/api/v1/repositories/{api_context.other_repository.id}/scans")

    assert forbidden.status_code == 404


def test_dashboard_summary_uses_current_organization_only(api_context) -> None:
    response = api_context.client.get("/api/v1/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "total_repositories": 1,
        "total_scans": 2,
        "completed_scans": 1,
        "failed_scans": 1,
        "high_risk_scans": 1,
        "average_risk_score": 72.5,
    }
    assert [scan["scan_id"] for scan in payload["recent_scans"]] == [
        str(api_context.failed_scan.id),
        str(api_context.completed_scan.id),
    ]
    assert payload["recent_scans"][1]["findings_count"] == 2
