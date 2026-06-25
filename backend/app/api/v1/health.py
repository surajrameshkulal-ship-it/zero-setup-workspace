from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.health import HealthRead
from app.services.health_service import HealthCheckService

router = APIRouter(prefix="/health", tags=["health"])


def get_health_check_service(db: Session = Depends(get_db)) -> HealthCheckService:
    return HealthCheckService(db)


@router.get("", response_model=HealthRead)
def health(service: HealthCheckService = Depends(get_health_check_service)) -> dict:
    return service.check()
