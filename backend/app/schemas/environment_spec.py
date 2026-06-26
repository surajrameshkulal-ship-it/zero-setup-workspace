from __future__ import annotations
import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class EnvironmentSpecRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    repository_id: uuid.UUID
    repository_full_name: str | None
    primary_language: str | None
    runtime_name: str | None
    runtime_version: str | None
    package_manager: str | None
    framework: str | None
    install_command: str | None
    dev_command: str | None
    prod_command: str | None
    build_command: str | None
    test_command: str | None
    lint_command: str | None
    health_check_command: str | None
    databases: list
    caches: list
    queues: list
    external_services: list
    app_ports: list
    service_ports: list
    health_check_endpoint: str | None
    env_vars: list
    missing_env_example: bool
    container_strategy: str
    workspace_requirements: dict
    safety: dict
    confidence_score: float
    assumptions: list
    missing_information: list
    warnings: list
    created_at: datetime
    updated_at: datetime
