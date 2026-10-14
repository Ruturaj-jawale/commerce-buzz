"""Storefront HTTP routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_organization
from app.db.models import Organization
from app.db.database import get_db
from app.schemas.storefront import StorefrontCreateRequest, StorefrontRead
from app.services.storefront_service import StorefrontService

router = APIRouter(prefix="/api/commerce-sources", tags=["commerce-sources"])
_service = StorefrontService()


@router.get("", response_model=list[StorefrontRead])
def list_storefronts(organization: Organization = Depends(get_current_organization), db: Session = Depends(get_db)) -> list[StorefrontRead]:
    return _service.list_storefronts(db, organization)


@router.post("", response_model=StorefrontRead)
def connect_storefront(payload: StorefrontCreateRequest, organization: Organization = Depends(get_current_organization), db: Session = Depends(get_db)) -> StorefrontRead:
    return _service.connect(db, organization, payload)
