from __future__ import annotations
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class RepositoryConnectRequest(BaseModel):
    installation_id: int = Field(..., gt=0)
    github_repository_id: int = Field(..., gt=0)
    owner: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    default_branch: str = Field(default="main", min_length=1, max_length=255)


class RepositoryUpdate(BaseModel):
    is_active: bool | None = None
    default_branch: str | None = Field(default=None, min_length=1, max_length=255)


class RepositoryRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    github_installation_id: uuid.UUID | None
    github_repository_id: int
    owner: str
    name: str
    full_name: str
    default_branch: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

