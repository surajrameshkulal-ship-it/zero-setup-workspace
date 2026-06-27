"""SuperBrainOrchestrator and its collaborators (Phase 12.0 — Super Brain core).

A read-only, evidence-based reasoning core that routes a question to the brains
that can handle it, builds each brain's context, collects evidence-bearing
reasoning, and synthesizes a single answer with a confidence score and suggested
(advisory) next actions. Everything is persisted as an auditable run; nothing is
executed (safe by default), and all output is secret-redacted.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.brain import BrainConversation, BrainMessage, BrainRun, BrainStep
from app.models.repository import Repository
from app.services.audit_service import AuditService
from app.services.brain.brains import build_brains
from app.services.brain.memory_service import BrainMemoryService
from app.services.brain.product_brain import ProductBrain as ProductBrainService
from app.services.brain.safety_guard import BrainSafetyGuard
from app.services.brain.types import BrainResult

logger = logging.getLogger(__name__)

MAX_BRAINS_PER_RUN = 4
MAX_EVIDENCE = 25
MAX_ACTIONS = 10


# -- registry + router --------------------------------------------------------


class BrainRegistry:
    def __init__(self, brains=None) -> None:
        self._brains = {b.name: b for b in (brains or build_brains())}

    def all(self) -> list:
        return list(self._brains.values())

    def get(self, name: str):
        return self._brains.get(name)


class BrainRouter:
    """Selects which brains should answer, ranked by relevance."""

    def __init__(self, registry: BrainRegistry) -> None:
        self.registry = registry

    def route(self, task: str) -> list[tuple[object, float]]:
        scored = [(b, b.can_handle(task)) for b in self.registry.all()]
        relevant = [(b, s) for b, s in scored if s > 0]
        relevant.sort(key=lambda bs: bs[1], reverse=True)
        if not relevant:
            # Always answer something: fall back to Product + Planning brains.
            relevant = [(b, 0.4) for b in self.registry.all() if b.name in ("product", "planning")]
        return relevant[:MAX_BRAINS_PER_RUN]


# -- context builder ----------------------------------------------------------


class BrainContextBuilder:
    """Builds the shared, read-only situational context for a run."""

    def build(self, db: Session, organization_id: uuid.UUID) -> dict:
        product = ProductBrainService(db)
        overview = product.overview(organization_id)
        repositories = db.scalar(
            select(Repository).where(Repository.organization_id == organization_id)
        )
        return {
            "summary": overview["summary"],
            "delivery": overview["delivery"],
            "blockers": overview["blockers"],
            "priorities": overview["priorities"],
            "roadmap_phase_count": len(overview["roadmap"]),
            "has_repositories": repositories is not None,
        }


# -- reasoning ----------------------------------------------------------------


class BrainReasoningService:
    """Turns structured brain results into a natural-language answer.

    Deterministic by default; if an AI completer is provided it is used to write
    the narrative, falling back to the deterministic synthesis on any error.
    """

    def __init__(self, *, ai_completer=None) -> None:
        self.ai_completer = ai_completer

    def narrate(self, question: str, results: list[BrainResult]) -> str:
        if self.ai_completer is not None:
            try:
                prompt = self._prompt(question, results)
                out = self.ai_completer(prompt)
                if out and out.strip():
                    return out.strip()
            except Exception:  # noqa: BLE001 - never fail the run on AI errors
                logger.warning("brain_reasoning_ai_failed", extra={"question": question[:80]})
        return self._deterministic(question, results)

    @staticmethod
    def _deterministic(question: str, results: list[BrainResult]) -> str:
        if not results:
            return "I could not find relevant signals to answer that yet."
        lead = results[0].summary
        others = [r.summary for r in results[1:] if r.summary]
        body = " ".join(others)
        return f"{lead} {body}".strip()

    @staticmethod
    def _prompt(question: str, results: list[BrainResult]) -> str:
        lines = [f"Question: {question}", "", "Brain findings:"]
        for r in results:
            lines.append(f"- [{r.brain} | confidence {r.confidence:.2f}] {r.summary}")
        lines.append("")
        lines.append("Write a concise, evidence-grounded answer for an engineering founder. Do not invent facts.")
        return "\n".join(lines)


# -- synthesizer --------------------------------------------------------------


class BrainResponseSynthesizer:
    def synthesize(self, results: list[BrainResult]) -> dict:
        if not results:
            return {"confidence": 0.0, "evidence": [], "suggested_actions": [], "primary_brain": None}
        ranked = sorted(results, key=lambda r: r.confidence, reverse=True)
        evidence: list[dict] = []
        actions: list[dict] = []
        seen_ev: set[str] = set()
        seen_act: set[str] = set()
        for r in ranked:
            for e in r.evidence:
                key = f"{e.get('source')}|{e.get('detail')}"
                if key not in seen_ev:
                    seen_ev.add(key)
                    evidence.append(e)
            for a in r.suggested_actions:
                if a.get("title") not in seen_act:
                    seen_act.add(a.get("title"))
                    actions.append(a)
        # Confidence: primary weighted with a small boost when brains corroborate.
        primary = ranked[0]
        corroboration = min(0.15, 0.05 * (len(ranked) - 1))
        confidence = round(min(1.0, primary.confidence + corroboration), 2)
        return {
            "confidence": confidence,
            "evidence": evidence[:MAX_EVIDENCE],
            "suggested_actions": actions[:MAX_ACTIONS],
            "primary_brain": primary.brain,
        }


# -- orchestrator -------------------------------------------------------------


class SuperBrainOrchestrator:
    def __init__(
        self,
        db: Session,
        *,
        registry: BrainRegistry | None = None,
        reasoning: BrainReasoningService | None = None,
        guard: BrainSafetyGuard | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or BrainRegistry()
        self.router = BrainRouter(self.registry)
        self.context_builder = BrainContextBuilder()
        self.reasoning = reasoning or BrainReasoningService()
        self.synthesizer = BrainResponseSynthesizer()
        self.guard = guard or BrainSafetyGuard()
        self.memory = BrainMemoryService(db, guard=self.guard)
        self.audit = AuditService(db)

    def ask(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        question: str,
        conversation_id: uuid.UUID | None = None,
    ) -> BrainRun:
        question = (self.guard.redact(question) or "").strip()
        if not question:
            from app.core.errors import AppError

            raise AppError("A question is required.")

        conversation = self._ensure_conversation(organization_id, actor_user_id, conversation_id, question)
        self.db.add(
            BrainMessage(conversation_id=conversation.id, role="user", content=question)
        )

        run = BrainRun(
            organization_id=organization_id,
            conversation_id=conversation.id,
            question=question,
            status="running",
            created_by_user_id=actor_user_id,
        )
        self.db.add(run)
        self.db.flush()

        context = self.context_builder.build(self.db, organization_id)
        routed = self.router.route(question)

        results: list[BrainResult] = []
        for order, (brain, score) in enumerate(routed):
            try:
                brain_ctx = brain.build_context(question, self.db, organization_id)
                result = brain.reason(question, {**context, **brain_ctx}, self.db, organization_id)
            except Exception as exc:  # noqa: BLE001 - a failing brain must not break the run
                logger.warning("brain_reason_failed", extra={"brain": brain.name, "error": str(exc)[:200]})
                result = BrainResult(brain.name, 0.0, f"{brain.name} brain could not produce a result.", [], [])
            # Safety: redact everything a brain produced before it is stored.
            result.summary = self.guard.redact(result.summary) or ""
            result.evidence = self.guard.sanitize(result.evidence)
            result.suggested_actions = self.guard.sanitize(result.suggested_actions)
            results.append(result)
            self.db.add(
                BrainStep(
                    run_id=run.id,
                    brain=brain.name,
                    order=order,
                    status="completed",
                    summary=result.summary,
                    confidence=result.confidence,
                    evidence=result.evidence,
                )
            )

        synthesis = self.synthesizer.synthesize(results)
        answer = self.guard.redact(self.reasoning.narrate(question, results)) or ""

        run.status = "completed"
        run.primary_brain = synthesis["primary_brain"]
        run.brains_consulted = [b.name for b, _ in routed]
        run.confidence_score = synthesis["confidence"]
        run.answer = answer
        run.evidence = synthesis["evidence"]
        run.suggested_actions = synthesis["suggested_actions"]
        self.db.add(
            BrainMessage(conversation_id=conversation.id, role="brain", content=answer, run_id=run.id)
        )

        # Record the run's recommendation as an auditable decision.
        if synthesis["suggested_actions"]:
            top = synthesis["suggested_actions"][0]
            self.memory.record_decision(
                organization_id=organization_id,
                title=top["title"],
                decision=answer,
                rationale=top.get("rationale"),
                confidence=synthesis["confidence"],
                evidence=synthesis["evidence"],
                run_id=run.id,
            )

        self.audit.log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="brain_ask",
            target_type="brain_run",
            target_id=str(run.id),
            metadata={"primary_brain": run.primary_brain, "confidence": run.confidence_score},
        )
        self.db.commit()
        self.db.refresh(run)
        return run

    # -- queries ---------------------------------------------------------------

    def get_run(self, run_id: uuid.UUID, organization_id: uuid.UUID) -> BrainRun:
        from app.core.errors import NotFoundError

        run = self.db.scalar(
            select(BrainRun).where(BrainRun.id == run_id, BrainRun.organization_id == organization_id)
        )
        if not run:
            raise NotFoundError("Brain run not found")
        return run

    def list_conversations(self, organization_id: uuid.UUID, *, limit: int = 50) -> list[BrainConversation]:
        return list(
            self.db.scalars(
                select(BrainConversation)
                .where(BrainConversation.organization_id == organization_id)
                .order_by(BrainConversation.updated_at.desc())
                .limit(limit)
            )
        )

    def get_conversation(self, conversation_id: uuid.UUID, organization_id: uuid.UUID) -> BrainConversation:
        from app.core.errors import NotFoundError

        convo = self.db.scalar(
            select(BrainConversation).where(
                BrainConversation.id == conversation_id, BrainConversation.organization_id == organization_id
            )
        )
        if not convo:
            raise NotFoundError("Conversation not found")
        return convo

    # -- helpers ---------------------------------------------------------------

    def _ensure_conversation(
        self, organization_id, actor_user_id, conversation_id, question
    ) -> BrainConversation:
        if conversation_id is not None:
            return self.get_conversation(conversation_id, organization_id)
        convo = BrainConversation(
            organization_id=organization_id,
            title=question[:120],
            created_by_user_id=actor_user_id,
        )
        self.db.add(convo)
        self.db.flush()
        return convo
