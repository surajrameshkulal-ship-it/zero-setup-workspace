from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError, AppError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.auth import AuthResponse, SignupRequest
from app.services.audit_service import AuditService


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_or_reset_admin_user(
        self,
        *,
        email: str,
        password: str,
        full_name: str = "CodeDNA Admin",
        organization_name: str = "CodeDNA AI",
        organization_slug: str = "codedna-ai",
    ) -> tuple[User, bool]:
        normalized_email = email.lower()
        normalized_slug = organization_slug.lower()

        user = self.db.scalar(select(User).where(User.email == normalized_email))
        if user:
            user.full_name = user.full_name or full_name
            user.hashed_password = hash_password(password)
            user.role = UserRole.ADMIN
            user.is_active = True
            if user.organization and not user.organization.is_active:
                user.organization.is_active = True
            created = False
            action = "admin_user.reset"
        else:
            organization = self.db.scalar(select(Organization).where(Organization.slug == normalized_slug))
            if not organization:
                organization = Organization(name=organization_name, slug=normalized_slug, is_active=True)
                self.db.add(organization)
                self.db.flush()
            elif not organization.is_active:
                organization.is_active = True

            user = User(
                organization_id=organization.id,
                email=normalized_email,
                full_name=full_name,
                hashed_password=hash_password(password),
                role=UserRole.ADMIN,
                is_active=True,
            )
            self.db.add(user)
            self.db.flush()
            created = True
            action = "admin_user.created"

        AuditService(self.db).log(
            organization_id=user.organization_id,
            actor_user_id=None,
            action=action,
            target_type="user",
            target_id=str(user.id),
            metadata={"email": normalized_email, "role": UserRole.ADMIN.value},
        )
        self.db.commit()
        self.db.refresh(user)
        return user, created

    def signup(self, payload: SignupRequest) -> AuthResponse:
        email = payload.email.lower()
        slug = payload.organization_slug.lower()

        existing_user = self.db.scalar(select(User).where(User.email == email))
        if existing_user:
            raise AppError("A user with this email already exists", code="email_taken")

        existing_org = self.db.scalar(select(Organization).where(Organization.slug == slug))
        if existing_org:
            raise AppError("An organization with this slug already exists", code="organization_slug_taken")

        organization = Organization(name=payload.organization_name, slug=slug)
        self.db.add(organization)
        self.db.flush()

        user = User(
            organization_id=organization.id,
            email=email,
            full_name=payload.full_name,
            hashed_password=hash_password(payload.password),
            role=UserRole.ADMIN,
        )
        self.db.add(user)
        self.db.flush()

        AuditService(self.db).log(
            organization_id=organization.id,
            actor_user_id=user.id,
            action="organization.signup",
            target_type="organization",
            target_id=str(organization.id),
        )
        self.db.commit()
        self.db.refresh(user)

        return AuthResponse(
            access_token=create_access_token(str(user.id), {"org_id": str(user.organization_id), "role": user.role.value}),
            user=user,
        )

    def authenticate(self, email: str, password: str) -> User:
        user = self.db.scalar(select(User).where(User.email == email.lower()))
        if not user or not verify_password(password, user.hashed_password) or not user.is_active:
            raise AuthenticationError("Invalid email or password")
        return user

    def token_for_user(self, user: User) -> AuthResponse:
        token = create_access_token(str(user.id), {"org_id": str(user.organization_id), "role": user.role.value})
        return AuthResponse(access_token=token, user=user)
