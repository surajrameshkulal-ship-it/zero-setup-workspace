from __future__ import annotations
from fastapi import APIRouter

from app.api.v1 import (
    admin,
    audit,
    auth,
    dashboard,
    engineering_requests,
    github,
    health,
    organizations,
    product_brain,
    repositories,
    rules,
    scans,
    workspaces,
)


api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(github.router)
api_router.include_router(repositories.router)
api_router.include_router(scans.router)
api_router.include_router(health.router)
api_router.include_router(dashboard.router)
api_router.include_router(rules.router)
api_router.include_router(engineering_requests.router)
api_router.include_router(admin.router)
api_router.include_router(audit.router)
api_router.include_router(workspaces.router)
api_router.include_router(product_brain.router)
