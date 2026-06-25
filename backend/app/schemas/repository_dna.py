from __future__ import annotations
import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class RepositoryDNARead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    repository_id: uuid.UUID
    repository_full_name: str | None
    languages: list
    frameworks: list
    package_managers: list
    databases: list
    queues: list
    testing_tools: list
    build_tools: list
    cicd: list
    docker: dict
    security_tools: list
    important_files: list
    architecture_summary: str | None
    dependency_summary: dict
    repository_health: dict
    risk_notes: list
    created_at: datetime
    updated_at: datetime
