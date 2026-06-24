from __future__ import annotations
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.rule import ArchitectureRule, CompanyRule
from app.schemas.rule import (
    ArchitectureRuleCreate,
    ArchitectureRuleUpdate,
    CompanyRuleCreate,
    CompanyRuleUpdate,
)
from app.services.audit_service import AuditService


class RuleManagementService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_company_rules(self, organization_id: uuid.UUID) -> list[CompanyRule]:
        return list(self.db.scalars(select(CompanyRule).where(CompanyRule.organization_id == organization_id)))

    def create_company_rule(
        self,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        payload: CompanyRuleCreate,
    ) -> CompanyRule:
        rule = CompanyRule(organization_id=organization_id, **payload.model_dump())
        self.db.add(rule)
        self.db.flush()
        AuditService(self.db).log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="company_rule.created",
            target_type="company_rule",
            target_id=str(rule.id),
            metadata={"name": rule.name},
        )
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def update_company_rule(
        self,
        organization_id: uuid.UUID,
        rule_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        payload: CompanyRuleUpdate,
    ) -> CompanyRule:
        rule = self.db.scalar(
            select(CompanyRule).where(CompanyRule.id == rule_id, CompanyRule.organization_id == organization_id)
        )
        if not rule:
            raise NotFoundError("Company rule not found")
        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(rule, field, value)
        AuditService(self.db).log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="company_rule.updated",
            target_type="company_rule",
            target_id=str(rule.id),
            metadata=updates,
        )
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def list_architecture_rules(self, organization_id: uuid.UUID) -> list[ArchitectureRule]:
        return list(self.db.scalars(select(ArchitectureRule).where(ArchitectureRule.organization_id == organization_id)))

    def create_architecture_rule(
        self,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        payload: ArchitectureRuleCreate,
    ) -> ArchitectureRule:
        rule = ArchitectureRule(organization_id=organization_id, **payload.model_dump())
        self.db.add(rule)
        self.db.flush()
        AuditService(self.db).log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="architecture_rule.created",
            target_type="architecture_rule",
            target_id=str(rule.id),
            metadata={"name": rule.name},
        )
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def update_architecture_rule(
        self,
        organization_id: uuid.UUID,
        rule_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        payload: ArchitectureRuleUpdate,
    ) -> ArchitectureRule:
        rule = self.db.scalar(
            select(ArchitectureRule).where(
                ArchitectureRule.id == rule_id,
                ArchitectureRule.organization_id == organization_id,
            )
        )
        if not rule:
            raise NotFoundError("Architecture rule not found")
        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(rule, field, value)
        AuditService(self.db).log(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="architecture_rule.updated",
            target_type="architecture_rule",
            target_id=str(rule.id),
            metadata=updates,
        )
        self.db.commit()
        self.db.refresh(rule)
        return rule

