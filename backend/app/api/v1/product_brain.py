from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.product_brain import ProductBrainOverview
from app.services.brain.product_brain import ProductBrain

router = APIRouter(prefix="/product-brain", tags=["product-brain"])


@router.get("/overview", response_model=ProductBrainOverview)
def product_brain_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Read-only product intelligence: roadmap, delivery state, blockers, priorities."""
    return ProductBrain(db).overview(current_user.organization_id)
