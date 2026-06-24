from __future__ import annotations

import argparse
import os

from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal
from app.services.auth_service import AuthService


DEFAULT_EMAIL = "admin@codedna.ai"
DEFAULT_PASSWORD = "Admin@123"
DEFAULT_FULL_NAME = "CodeDNA Admin"
DEFAULT_ORGANIZATION_NAME = "CodeDNA AI"
DEFAULT_ORGANIZATION_SLUG = "codedna-ai"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or reset a CodeDNA AI admin user.")
    parser.add_argument("--email", default=os.getenv("ADMIN_EMAIL", DEFAULT_EMAIL))
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD", DEFAULT_PASSWORD))
    parser.add_argument("--full-name", default=os.getenv("ADMIN_FULL_NAME", DEFAULT_FULL_NAME))
    parser.add_argument("--organization-name", default=os.getenv("ADMIN_ORGANIZATION_NAME", DEFAULT_ORGANIZATION_NAME))
    parser.add_argument("--organization-slug", default=os.getenv("ADMIN_ORGANIZATION_SLUG", DEFAULT_ORGANIZATION_SLUG))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db = SessionLocal()
    try:
        user, created = AuthService(db).create_or_reset_admin_user(
            email=args.email,
            password=args.password,
            full_name=args.full_name,
            organization_name=args.organization_name,
            organization_slug=args.organization_slug,
        )
        action = "created" if created else "reset"
        print(f"Admin user {action}: {user.email}")
        print(f"Organization ID: {user.organization_id}")
        print(f"User ID: {user.id}")
        return 0
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
