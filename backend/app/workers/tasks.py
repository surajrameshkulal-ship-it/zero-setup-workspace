from __future__ import annotations
import uuid

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.services.scan_service import PullRequestScanService


@celery_app.task(name="scan.run_pr_scan", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def run_pr_scan(scan_id: str) -> str:
    scan_uuid = uuid.UUID(scan_id)
    db = SessionLocal()
    try:
        PullRequestScanService(db).run(scan_uuid)
        return scan_id
    finally:
        db.close()

