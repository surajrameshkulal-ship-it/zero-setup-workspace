from __future__ import annotations
import logging
import uuid

from fastapi import Depends, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.models.organization import Organization
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/login")


def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    payload = decode_access_token(token)
    subject = payload.get("sub")
    if not subject:
        raise AuthenticationError("Token subject is missing")
    try:
        user_id = uuid.UUID(str(subject))
    except ValueError as exc:
        raise AuthenticationError("Token subject is invalid") from exc
    user = db.scalar(select(User).where(User.id == user_id))
    if not user or not user.is_active:
        raise AuthenticationError("User is inactive or no longer exists")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "security_check_failed",
            extra={
                "security_check": "require_admin",
                "user_id": str(current_user.id),
                "organization_id": str(current_user.organization_id),
                "role": current_user.role.value,
            },
        )
        raise PermissionDeniedError("Admin privileges are required")
    logger.info(
        "security_check_passed",
        extra={
            "security_check": "require_admin",
            "user_id": str(current_user.id),
            "organization_id": str(current_user.organization_id),
            "role": current_user.role.value,
        },
    )
    return current_user


def get_current_organization(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Organization:
    organization = db.get(Organization, current_user.organization_id)
    if not organization or not organization.is_active:
        raise AuthenticationError("Organization is inactive or no longer exists")
    return organization
