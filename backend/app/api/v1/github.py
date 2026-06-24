from __future__ import annotations
import json

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models.user import User
from app.schemas.github import (
    GitHubInstallationRead,
    GitHubInstallationRegisterRequest,
    GitHubInstallUrl,
    GitHubWebhookResponse,
)
from app.services.github_service import GitHubService
from app.services.webhook_service import GitHubWebhookService


router = APIRouter(prefix="/github", tags=["github"])


@router.get("/install-url", response_model=GitHubInstallUrl)
def install_url(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> GitHubInstallUrl:
    return GitHubInstallUrl(url=GitHubService(db).install_url())


@router.get("/installations", response_model=list[GitHubInstallationRead])
def list_installations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list:
    return GitHubService(db).list_installations(current_user.organization_id)


@router.post("/installations", response_model=GitHubInstallationRead, status_code=201)
def register_installation(
    payload: GitHubInstallationRegisterRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return GitHubService(db).register_installation(
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )


@router.post("/webhooks", response_model=GitHubWebhookResponse, include_in_schema=False)
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> GitHubWebhookResponse:
    body = await request.body()
    service = GitHubWebhookService(db)
    service.verify(body, x_hub_signature_256)
    payload = json.loads(body.decode("utf-8") or "{}")
    return service.handle(event=x_github_event, payload=payload)

