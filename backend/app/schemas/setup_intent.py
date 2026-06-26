from __future__ import annotations
import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class SetupIntentRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    repository_id: uuid.UUID
    repository_full_name: str | None
    languages: list
    frameworks: list
    package_manager: str | None
    runtime_version: str | None
    install_command: str | None
    dev_command: str | None
    prod_command: str | None
    test_command: str | None
    build_command: str | None
    lint_command: str | None
    env_vars: list
    ports: list
    databases: list
    caches: list
    queues: list
    external_services: list
    docker: dict
    cicd_provider: str | None
    health_check_endpoint: str | None
    confidence_score: float
    sources_analyzed: list
    notes: list
    evidence: list = []
    created_at: datetime
    updated_at: datetime
