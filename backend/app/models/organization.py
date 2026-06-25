from __future__ import annotations
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    repositories = relationship("Repository", back_populates="organization", cascade="all, delete-orphan")
    github_installations = relationship(
        "GitHubInstallation",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    company_rules = relationship("CompanyRule", back_populates="organization", cascade="all, delete-orphan")
    architecture_rules = relationship("ArchitectureRule", back_populates="organization", cascade="all, delete-orphan")
    scans = relationship("PullRequestScan", back_populates="organization", cascade="all, delete-orphan")
    engineering_requests = relationship(
        "EngineeringRequest",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    execution_plans = relationship(
        "ExecutionPlan",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    repository_dna = relationship(
        "RepositoryDNA",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    audit_logs = relationship("AuditLog", back_populates="organization", cascade="all, delete-orphan")
    settings = relationship("AdminSetting", back_populates="organization", cascade="all, delete-orphan")

