from __future__ import annotations
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models.rule import ArchitectureRule, CompanyRule
from app.models.user import User
from app.schemas.rule import (
    ArchitectureRuleCreate,
    ArchitectureRuleRead,
    ArchitectureRuleUpdate,
    CompanyRuleCreate,
    CompanyRuleRead,
    CompanyRuleUpdate,
)
from app.services.rule_management_service import RuleManagementService


router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("/company", response_model=list[CompanyRuleRead])
def list_company_rules(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CompanyRule]:
    return RuleManagementService(db).list_company_rules(current_user.organization_id)


@router.post("/company", response_model=CompanyRuleRead, status_code=201)
def create_company_rule(
    payload: CompanyRuleCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CompanyRule:
    return RuleManagementService(db).create_company_rule(current_user.organization_id, current_user.id, payload)


@router.patch("/company/{rule_id}", response_model=CompanyRuleRead)
def update_company_rule(
    rule_id: uuid.UUID,
    payload: CompanyRuleUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CompanyRule:
    return RuleManagementService(db).update_company_rule(
        current_user.organization_id,
        rule_id,
        current_user.id,
        payload,
    )


@router.get("/architecture", response_model=list[ArchitectureRuleRead])
def list_architecture_rules(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ArchitectureRule]:
    return RuleManagementService(db).list_architecture_rules(current_user.organization_id)


@router.post("/architecture", response_model=ArchitectureRuleRead, status_code=201)
def create_architecture_rule(
    payload: ArchitectureRuleCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ArchitectureRule:
    return RuleManagementService(db).create_architecture_rule(current_user.organization_id, current_user.id, payload)


@router.patch("/architecture/{rule_id}", response_model=ArchitectureRuleRead)
def update_architecture_rule(
    rule_id: uuid.UUID,
    payload: ArchitectureRuleUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ArchitectureRule:
    return RuleManagementService(db).update_architecture_rule(
        current_user.organization_id,
        rule_id,
        current_user.id,
        payload,
    )

