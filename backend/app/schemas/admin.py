from __future__ import annotations
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AdminSettingUpsert(BaseModel):
    key: str = Field(..., min_length=2, max_length=120, pattern=r"^[a-zA-Z0-9_.-]+$")
    value: dict = Field(default_factory=dict)


class AdminSettingRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    key: str
    value: dict
    created_at: datetime
    updated_at: datetime

