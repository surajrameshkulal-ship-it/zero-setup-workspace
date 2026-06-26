from __future__ import annotations

from pathlib import Path

from app.models.engineering_request import EngineeringRequest, RequestPriority, RequestStatus, RequestType
from app.services.brain.product_brain import ProductBrain

PB_BASE = "/api/v1/product-brain"


def _request(api_context, *, status: RequestStatus, title: str, org=None) -> EngineeringRequest:
    req = EngineeringRequest(
        organization_id=org or api_context.organization.id,
        repository_id=api_context.repository.id if org is None else None,
        title=title,
        description="desc",
        request_type=RequestType.FEATURE,
        status=status,
        priority=RequestPriority.MEDIUM,
    )
    api_context.db.add(req)
    api_context.db.commit()
    return req


def test_overview_structure(api_context) -> None:
    overview = ProductBrain(api_context.db).overview(api_context.organization.id)
    assert set(overview) == {"roadmap", "delivery", "blockers", "priorities", "summary"}
    assert isinstance(overview["delivery"]["repositories"], int)
    assert isinstance(overview["summary"], str) and overview["summary"]
    assert overview["priorities"]  # always at least the idle recommendation


def test_roadmap_parsed_from_docs(api_context) -> None:
    phases = ProductBrain(api_context.db).roadmap()
    # The repo ships docs/zero-setup-workspace-roadmap.md with Phase 11.x items.
    assert any(p["id"].startswith("11") for p in phases)
    assert all({"id", "title", "summary"} <= set(p) for p in phases)


def test_roadmap_tolerates_missing_docs(api_context, tmp_path) -> None:
    brain = ProductBrain(api_context.db, docs_root=tmp_path / "nope")
    assert brain.roadmap() == []


def test_failed_request_becomes_blocker(api_context) -> None:
    _request(api_context, status=RequestStatus.FAILED, title="Broken feature")
    overview = ProductBrain(api_context.db).overview(api_context.organization.id)
    titles = [b["title"] for b in overview["blockers"]]
    assert "Broken feature" in titles
    assert any(b["type"] == "engineering_request" and b["severity"] == "high" for b in overview["blockers"])


def test_approved_request_becomes_priority(api_context) -> None:
    _request(api_context, status=RequestStatus.APPROVED, title="Ready to ship")
    overview = ProductBrain(api_context.db).overview(api_context.organization.id)
    assert any(p["category"] == "execute" for p in overview["priorities"])


def test_blockers_outrank_when_present(api_context) -> None:
    _request(api_context, status=RequestStatus.FAILED, title="Broken")
    _request(api_context, status=RequestStatus.APPROVED, title="Ready")
    overview = ProductBrain(api_context.db).overview(api_context.organization.id)
    assert overview["priorities"][0]["category"] == "blockers"


def test_org_isolation(api_context) -> None:
    # A request in another org must not appear in this org's overview.
    _request(api_context, status=RequestStatus.FAILED, title="Other org bug", org=api_context.other_organization.id)
    overview = ProductBrain(api_context.db).overview(api_context.organization.id)
    assert "Other org bug" not in [b["title"] for b in overview["blockers"]]
    assert overview["delivery"]["engineering_requests_total"] == 0


def test_api_overview(api_context) -> None:
    _request(api_context, status=RequestStatus.PLAN_READY, title="Plan ready item")
    resp = api_context.client.get(f"{PB_BASE}/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert "roadmap" in body and "priorities" in body
    assert any(p["category"] == "review" for p in body["priorities"])
