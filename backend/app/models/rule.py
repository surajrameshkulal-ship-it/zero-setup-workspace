from __future__ import annotations
import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Severity(str, enum.Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CompanyRuleType(str, enum.Enum):
    REQUIRED_TEXT = "required_text"
    FORBIDDEN_TEXT = "forbidden_text"
    REGEX = "regex"
    FILE_PATH = "file_path"


class CompanyRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "company_rules"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rule_type: Mapped[CompanyRuleType] = mapped_column(
        Enum(CompanyRuleType, name="company_rule_type", values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
    )
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, name="severity", values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
        default=Severity.MEDIUM,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    organization = relationship("Organization", back_populates="company_rules")


class ArchitectureRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "architecture_rules"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_path_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    forbidden_import_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, name="severity", values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
        default=Severity.HIGH,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    organization = relationship("Organization", back_populates="architecture_rules")
