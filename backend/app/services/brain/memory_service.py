"""BrainMemoryService — the Super Brain's knowledge store (CRUD + search).

V1 stores explicit memory entries (notes, decisions, summaries) org-scoped, with
simple keyword search the brains use to recall prior context. Secret-looking
content is redacted on write by the safety guard.
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.brain import BrainDecision, BrainMemory
from app.services.brain.safety_guard import BrainSafetyGuard


class BrainMemoryService:
    def __init__(self, db: Session, *, guard: BrainSafetyGuard | None = None) -> None:
        self.db = db
        self.guard = guard or BrainSafetyGuard()

    # -- memory ---------------------------------------------------------------

    def create(
        self,
        *,
        organization_id: uuid.UUID,
        kind: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        source: str | None = None,
        refs: list | None = None,
        created_by_user_id: uuid.UUID | None = None,
    ) -> BrainMemory:
        entry = BrainMemory(
            organization_id=organization_id,
            kind=kind or "note",
            title=self.guard.redact(title) or title,
            content=self.guard.redact(content) or "",
            tags=tags or [],
            source=source,
            refs=refs or [],
            created_by_user_id=created_by_user_id,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def get(self, memory_id: uuid.UUID, organization_id: uuid.UUID) -> BrainMemory:
        entry = self.db.scalar(
            select(BrainMemory).where(BrainMemory.id == memory_id, BrainMemory.organization_id == organization_id)
        )
        if not entry:
            raise NotFoundError("Memory entry not found")
        return entry

    def list(
        self, organization_id: uuid.UUID, *, query: str | None = None, kind: str | None = None, limit: int = 100
    ) -> list[BrainMemory]:
        stmt = select(BrainMemory).where(BrainMemory.organization_id == organization_id)
        if kind:
            stmt = stmt.where(BrainMemory.kind == kind)
        if query:
            like = f"%{query.lower()}%"
            stmt = stmt.where(
                or_(func_lower(BrainMemory.title).like(like), func_lower(BrainMemory.content).like(like))
            )
        stmt = stmt.order_by(BrainMemory.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt))

    def search(self, organization_id: uuid.UUID, terms: list[str], *, limit: int = 5) -> list[BrainMemory]:
        """Lightweight recall: rank entries by how many terms appear."""
        entries = self.list(organization_id, limit=500)
        scored: list[tuple[int, BrainMemory]] = []
        lowered = [t.lower() for t in terms if t]
        for e in entries:
            blob = f"{e.title} {e.content} {' '.join(e.tags or [])}".lower()
            score = sum(1 for t in lowered if t in blob)
            if score:
                scored.append((score, e))
        scored.sort(key=lambda s: s[0], reverse=True)
        return [e for _, e in scored[:limit]]

    # -- decisions ------------------------------------------------------------

    def record_decision(
        self,
        *,
        organization_id: uuid.UUID,
        title: str,
        decision: str,
        rationale: str | None,
        confidence: float,
        evidence: list | None,
        run_id: uuid.UUID | None = None,
    ) -> BrainDecision:
        row = BrainDecision(
            organization_id=organization_id,
            run_id=run_id,
            title=self.guard.redact(title) or title,
            decision=self.guard.redact(decision) or "",
            rationale=self.guard.redact(rationale),
            confidence=confidence,
            evidence=self.guard.sanitize(evidence or []),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def list_decisions(self, organization_id: uuid.UUID, *, limit: int = 100) -> list[BrainDecision]:
        return list(
            self.db.scalars(
                select(BrainDecision)
                .where(BrainDecision.organization_id == organization_id)
                .order_by(BrainDecision.created_at.desc())
                .limit(limit)
            )
        )


def func_lower(column):
    from sqlalchemy import func

    return func.lower(column)
