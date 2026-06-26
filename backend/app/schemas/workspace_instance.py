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
    error_message: str | None
    stopped_at: str | None
    created_at: datetime
    updated_at: datetime


class WorkspaceInstanceLogs(ORMModel):
    id: uuid.UUID
    status: str
    logs: list
