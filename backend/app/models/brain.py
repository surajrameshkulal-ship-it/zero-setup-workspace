from __future__ import annotations
import uuid

from sqlalchemy import Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

# Note on evidence / action-suggestion value objects:
# BrainEvidence and BrainActionSuggestion from the spec are represented as
# structured JSON entries embedded on runs/steps/decisions (validated by the
# pydantic schemas) rather than separate tables. This keeps a reasoning run
# atomic and queryable in one read; they can be promoted to tables later.
#   evidence entry:  {"source": str, "detail": str, "reference": str | None}
#   action entry:    {"title": str, "rationale": str, "brain": str}


class BrainConversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brain_conversations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="Conversation")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    messages = relationship(
        "BrainMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="BrainMessage.created_at"
    )


class BrainMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brain_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brain_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "user" | "brain"
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    conversation = relationship("BrainConversation", back_populates="messages")


class BrainRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brain_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    primary_brain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    brains_consulted: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    suggested_actions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    steps = relationship(
        "BrainStep", back_populates="run", cascade="all, delete-orphan", order_by="BrainStep.order"
    )


class BrainStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brain_steps"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brain_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    brain: Mapped[str] = mapped_column(String(64), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    run = relationship("BrainRun", back_populates="steps")


class BrainMemory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brain_memory"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False, default="note")
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class BrainDecision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brain_decisions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
