from __future__ import annotations
"""initial schema

Revision ID: 202606230001
Revises:
Create Date: 2026-06-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202606230001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


user_role = postgresql.ENUM("admin", "member", "viewer", name="user_role", create_type=False)
company_rule_type = postgresql.ENUM("required_text", "forbidden_text", "regex", "file_path", name="company_rule_type", create_type=False)
severity = postgresql.ENUM("info", "low", "medium", "high", "critical", name="severity", create_type=False)
scan_status = postgresql.ENUM("queued", "running", "completed", "failed", name="scan_status", create_type=False)
risk_level = postgresql.ENUM("low", "medium", "high", "critical", name="risk_level", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    user_role.create(bind, checkfirst=True)
    company_rule_type.create(bind, checkfirst=True)
    severity.create(bind, checkfirst=True)
    scan_status.create(bind, checkfirst=True)
    risk_level.create(bind, checkfirst=True)

    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    op.create_table(
        "users",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_organization_id", "users", ["organization_id"], unique=False)

    op.create_table(
        "github_installations",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("account_login", sa.String(length=255), nullable=False),
        sa.Column("account_type", sa.String(length=50), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "installation_id", name="uq_org_github_installation"),
    )
    op.create_index("ix_github_installations_installation_id", "github_installations", ["installation_id"], unique=True)
    op.create_index("ix_github_installations_organization_id", "github_installations", ["organization_id"], unique=False)

    op.create_table(
        "company_rules",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rule_type", company_rule_type, nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("severity", severity, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_company_rules_organization_id", "company_rules", ["organization_id"], unique=False)

    op.create_table(
        "architecture_rules",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_path_pattern", sa.Text(), nullable=False),
        sa.Column("forbidden_import_pattern", sa.Text(), nullable=False),
        sa.Column("severity", severity, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_architecture_rules_organization_id", "architecture_rules", ["organization_id"], unique=False)

    op.create_table(
        "admin_settings",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "key", name="uq_org_setting_key"),
    )
    op.create_index("ix_admin_settings_organization_id", "admin_settings", ["organization_id"], unique=False)

    op.create_table(
        "repositories",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("github_installation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("github_repository_id", sa.BigInteger(), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=511), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["github_installation_id"], ["github_installations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "full_name", name="uq_org_repository_full_name"),
        sa.UniqueConstraint("organization_id", "github_repository_id", name="uq_org_github_repository"),
    )
    op.create_index("ix_repositories_github_installation_id", "repositories", ["github_installation_id"], unique=False)
    op.create_index("ix_repositories_github_repository_id", "repositories", ["github_repository_id"], unique=False)
    op.create_index("ix_repositories_organization_id", "repositories", ["organization_id"], unique=False)

    op.create_table(
        "pull_request_scans",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("github_pr_number", sa.Integer(), nullable=False),
        sa.Column("github_pr_url", sa.String(length=1024), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("head_sha", sa.String(length=64), nullable=False),
        sa.Column("base_sha", sa.String(length=64), nullable=True),
        sa.Column("status", scan_status, nullable=False),
        sa.Column("trigger", sa.String(length=40), nullable=False),
        sa.Column("files_changed", sa.Integer(), nullable=False),
        sa.Column("lines_added", sa.Integer(), nullable=False),
        sa.Column("lines_deleted", sa.Integer(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("risk_level", risk_level, nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("semgrep_findings", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("ai_findings", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("company_rule_violations", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("architecture_violations", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("report", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pull_request_scans_github_pr_number", "pull_request_scans", ["github_pr_number"], unique=False)
    op.create_index("ix_pull_request_scans_head_sha", "pull_request_scans", ["head_sha"], unique=False)
    op.create_index("ix_pull_request_scans_organization_id", "pull_request_scans", ["organization_id"], unique=False)
    op.create_index("ix_pull_request_scans_repository_id", "pull_request_scans", ["repository_id"], unique=False)
    op.create_index("ix_pull_request_scans_status", "pull_request_scans", ["status"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("target_type", sa.String(length=120), nullable=True),
        sa.Column("target_id", sa.String(length=120), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"], unique=False)
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_logs_organization_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_pull_request_scans_status", table_name="pull_request_scans")
    op.drop_index("ix_pull_request_scans_repository_id", table_name="pull_request_scans")
    op.drop_index("ix_pull_request_scans_organization_id", table_name="pull_request_scans")
    op.drop_index("ix_pull_request_scans_head_sha", table_name="pull_request_scans")
    op.drop_index("ix_pull_request_scans_github_pr_number", table_name="pull_request_scans")
    op.drop_table("pull_request_scans")
    op.drop_index("ix_repositories_organization_id", table_name="repositories")
    op.drop_index("ix_repositories_github_repository_id", table_name="repositories")
    op.drop_index("ix_repositories_github_installation_id", table_name="repositories")
    op.drop_table("repositories")
    op.drop_index("ix_admin_settings_organization_id", table_name="admin_settings")
    op.drop_table("admin_settings")
    op.drop_index("ix_architecture_rules_organization_id", table_name="architecture_rules")
    op.drop_table("architecture_rules")
    op.drop_index("ix_company_rules_organization_id", table_name="company_rules")
    op.drop_table("company_rules")
    op.drop_index("ix_github_installations_organization_id", table_name="github_installations")
    op.drop_index("ix_github_installations_installation_id", table_name="github_installations")
    op.drop_table("github_installations")
    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")
    risk_level.drop(op.get_bind(), checkfirst=True)
    scan_status.drop(op.get_bind(), checkfirst=True)
    severity.drop(op.get_bind(), checkfirst=True)
    company_rule_type.drop(op.get_bind(), checkfirst=True)
    user_role.drop(op.get_bind(), checkfirst=True)
