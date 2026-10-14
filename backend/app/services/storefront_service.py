"""Connect and list commerce storefronts."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Organization, Storefront
from app.schemas.storefront import StorefrontCreateRequest, StorefrontRead


class StorefrontService:
    def list_storefronts(self, db: Session, organization: Organization) -> list[StorefrontRead]:
        rows = db.scalars(select(Storefront).where(Storefront.organization_id == organization.id).order_by(Storefront.id)).all()
        return [StorefrontRead.model_validate(row) for row in rows]

    def connect(self, db: Session, organization: Organization, payload: StorefrontCreateRequest) -> StorefrontRead:
        storefront = Storefront(
            organization_id=organization.id,
            name=payload.name.strip(),
            provider=payload.source.strip(),
            store_url=payload.store_url.strip(),
            webhook_secret=payload.webhook_secret,
            status="connected",
        )
        db.add(storefront)
        db.commit()
        db.refresh(storefront)
        return StorefrontRead.model_validate(storefront)

    def get_by_id(self, db: Session, storefront_id: int) -> Storefront | None:
        return db.get(Storefront, storefront_id)

    def get(self, db: Session, organization: Organization, storefront_id: int) -> Storefront:
        storefront = db.get(Storefront, storefront_id)
        if storefront is None or storefront.organization_id != organization.id:
            raise HTTPException(status_code=404, detail="Commerce source not found")
        return storefront
