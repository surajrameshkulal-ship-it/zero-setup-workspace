from __future__ import annotations
import uuid
from datetime import datetime

from app.schemas.common import ORMModel


class WorkspaceInstanceRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    repository_id: uuid.UUID
    repository_full_name: str | None
    scan_id: uuid.UUID | None
    environment_spec_id: uuid.UUID | None
    blueprint_id: uuid.UUID | None
    provision_id: uuid.UUID | None
    status: str
    runtime: str | None
    workspace_path: str | None
    install_command: str | None
    runtime_command: str | None
    preview_url: str | None
    exposed_ports: list
    logs: list
    events: list
    error_message: str | None
    last_heartbeat_at: str | None
    running_at: str | None
    cancel_requested: bool
    recovery_attempts: int
    cpu_limit: float | None
    memory_limit_mb: int | None
    execution_timeout_seconds: int
    install_duration_ms: int | None
    startup_duration_ms: int | None
    launch_duration_ms: int | None
    stopped_at: str | None
    created_at: datetime
    updated_at: datetime


class WorkspaceInstanceLogs(ORMModel):
    id: uuid.UUID
    status: str
    logs: list
    events: list


class WorkspaceMetrics(ORMModel):
    total: int
    by_status: dict
    average_launch_ms: float | None
    average_install_ms: float | None
    average_startup_ms: float | None
    launched: int
    failure_reasons: list
