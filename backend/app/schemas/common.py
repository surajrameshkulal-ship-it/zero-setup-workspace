from __future__ import annotations
from pydantic import BaseModel, ConfigDict


class APIMessage(BaseModel):
    message: str


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

