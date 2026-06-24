from __future__ import annotations
import uuid
import re
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.rule import CompanyRuleType, Severity
from app.schemas.common import ORMModel


class CompanyRuleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: str = Field(..., min_length=2, max_length=5000)
    rule_type: CompanyRuleType
    pattern: str = Field(..., min_length=1, max_length=5000)
    severity: Severity = Severity.MEDIUM

    @model_validator(mode="after")
    def validate_regex_pattern(self):
        if self.rule_type == CompanyRuleType.REGEX:
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(f"Invalid regex pattern: {exc}") from exc
        return self


class CompanyRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, min_length=2, max_length=5000)
    pattern: str | None = Field(default=None, min_length=1, max_length=5000)
    severity: Severity | None = None
    is_active: bool | None = None


class CompanyRuleRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str
    rule_type: CompanyRuleType
    pattern: str
    severity: Severity
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ArchitectureRuleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: str = Field(..., min_length=2, max_length=5000)
    source_path_pattern: str = Field(..., min_length=1, max_length=5000)
    forbidden_import_pattern: str = Field(..., min_length=1, max_length=5000)
    severity: Severity = Severity.HIGH

    @model_validator(mode="after")
    def validate_forbidden_import_regex(self):
        try:
            re.compile(self.forbidden_import_pattern)
        except re.error as exc:
            raise ValueError(f"Invalid forbidden import regex: {exc}") from exc
        return self


class ArchitectureRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, min_length=2, max_length=5000)
    source_path_pattern: str | None = Field(default=None, min_length=1, max_length=5000)
    forbidden_import_pattern: str | None = Field(default=None, min_length=1, max_length=5000)
    severity: Severity | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_forbidden_import_regex(self):
        if self.forbidden_import_pattern:
            try:
                re.compile(self.forbidden_import_pattern)
            except re.error as exc:
                raise ValueError(f"Invalid forbidden import regex: {exc}") from exc
        return self


class ArchitectureRuleRead(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str
    source_path_pattern: str
    forbidden_import_pattern: str
    severity: Severity
    is_active: bool
    created_at: datetime
    updated_at: datetime
