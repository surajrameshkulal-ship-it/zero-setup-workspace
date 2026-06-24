from __future__ import annotations

from sqlalchemy import select

from app.core.security import verify_password
from app.models.user import User, UserRole
from app.services.auth_service import AuthService


def test_create_or_reset_admin_user_hashes_password_and_is_idempotent(api_context) -> None:
    service = AuthService(api_context.db)

    user, created = service.create_or_reset_admin_user(
        email="admin@codedna.ai",
        password="Admin@123",
    )

    assert created is True
    assert user.email == "admin@codedna.ai"
    assert user.role == UserRole.ADMIN
    assert user.is_active is True
    assert user.hashed_password != "Admin@123"
    assert verify_password("Admin@123", user.hashed_password)

    same_user, created_again = service.create_or_reset_admin_user(
        email="ADMIN@CODEDNA.AI",
        password="Updated@123",
    )

    assert created_again is False
    assert same_user.id == user.id
    assert verify_password("Updated@123", same_user.hashed_password)

    users = api_context.db.scalars(select(User).where(User.email == "admin@codedna.ai")).all()
    assert len(users) == 1
