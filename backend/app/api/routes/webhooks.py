"""Verified webhook ingestion for commerce providers.

Provider-facing endpoints authenticate per-storefront via HMAC signature
instead of organization credentials. Webhooks must be verified per AGENTS.md.
"""

import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import Organization
from app.schemas.analytics import CommerceEventIngest, IngestionJobRead
from app.services.ingestion_job_service import IngestionJobService
from app.services.storefront_service import StorefrontService

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _extract_signature(header_value: str | None) -> str | None:
    if not header_value:
        return None
    value = header_value.strip()
    if value.lower().startswith("sha256="):
        return value.split("=", 1)[1].strip()
    return value


@router.post(
    "/sources/{storefront_id}",
    response_model=IngestionJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_source_webhook(storefront_id: int, request: Request, db: Session = Depends(get_db)) -> IngestionJobRead:
    body = await request.body()
    if len(body) > get_settings().max_ingestion_payload_bytes:
        raise HTTPException(status_code=413, detail="Webhook payload exceeds size limit")

    storefront = StorefrontService().get_by_id(db, storefront_id)
    if storefront is None or not storefront.webhook_secret:
        raise HTTPException(status_code=404, detail="Webhook source not found")

    signature = _extract_signature(request.headers.get("x-signature"))
    expected = hmac.new(storefront.webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if signature is None or not hmac.compare_digest(signature.lower(), expected):
        raise HTTPException(status_code=401, detail="Webhook signature verification failed")

    try:
        payload = CommerceEventIngest.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    organization = db.get(Organization, storefront.organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Webhook source not found")

    return IngestionJobService().enqueue(db, organization, storefront.id, payload)
