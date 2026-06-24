from __future__ import annotations
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class GitHubInstallUrl(BaseModel):
    url: str


class GitHubInstallationRegisterRequest(BaseModel):
    installation_id: int = Field(..., gt=0)
    account_login: str = Field(..., min_length=1, max_length=255)
    account_type: str = Field(default="Organization", min_length=1, max_length=50)
    permissions: dict = Field(default_factory=dict)


class GitHubInstallationRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    installation_id: int
    account_login: str
    account_type: str
    permissions: dict
    created_at: datetime
    updated_at: datetime


class GitHubWebhookResponse(BaseModel):
    accepted: bool
    action: str | None = None
    scan_id: uuid.UUID | None = None
    message: str

