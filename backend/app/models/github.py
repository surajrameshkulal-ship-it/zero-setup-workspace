from __future__ import annotations
import uuid

from sqlalchemy import BigInteger, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class GitHubInstallation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "github_installations"
    __table_args__ = (UniqueConstraint("organization_id", "installation_id", name="uq_org_github_installation"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    installation_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    account_login: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(50), nullable=False, default="Organization")
    permissions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    organization = relationship("Organization", back_populates="github_installations")
    repositories = relationship("Repository", back_populates="github_installation")
