"""Durable database queue for commerce ingestion work."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import IngestionJob, Organization
from app.core.config import get_settings
from app.schemas.analytics import CommerceEventIngest, IngestionJobRead
from app.services.analytics_service import AnalyticsService
from app.services.storefront_service import StorefrontService


class IngestionJobService:
    def __init__(self) -> None:
        self._sources = StorefrontService()
        self._analytics = AnalyticsService(self._sources)

    def enqueue(
        self,
        db: Session,
        organization: Organization,
        storefront_id: int,
        payload: CommerceEventIngest,
        import_batch_id: int | None = None,
        source_row: int | None = None,
    ) -> IngestionJobRead:
        self._sources.get(db, organization, storefront_id)
        job = IngestionJob(
            organization_id=organization.id,
            storefront_id=storefront_id,
            payload_json=payload.model_dump_json(),
            import_batch_id=import_batch_id,
            source_row=source_row,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return IngestionJobRead.model_validate(job)

    def get(self, db: Session, organization: Organization, job_id: int) -> IngestionJobRead:
        job = db.get(IngestionJob, job_id)
        if job is None or job.organization_id != organization.id:
            raise HTTPException(status_code=404, detail="Ingestion job not found")
        return IngestionJobRead.model_validate(job)

    def claim_next(self, db: Session) -> IngestionJob | None:
        # PostgreSQL locks one candidate so independently deployed workers do not process it twice.
        job = db.scalar(
            select(IngestionJob)
            .where(or_(IngestionJob.status == "queued", (IngestionJob.status == "processing") & (IngestionJob.claimed_at < datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=get_settings().ingestion_worker_lease_seconds))), IngestionJob.attempts < get_settings().ingestion_worker_max_attempts)
            .order_by(IngestionJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        job.status = "processing"
        job.claimed_at = datetime.now(UTC).replace(tzinfo=None)
        job.attempts += 1
        db.commit()
        db.refresh(job)
        return job

    def process_next(self, db: Session) -> bool:
        job = self.claim_next(db)
        if job is None:
            return False
        try:
            organization = db.get(Organization, job.organization_id)
            if organization is None:
                raise RuntimeError("Organization no longer exists")
            payload = CommerceEventIngest.model_validate_json(job.payload_json)
            event = self._analytics.ingest(db, organization, job.storefront_id, payload)
            job.status = "completed"
            job.event_id = event.id
            job.error_message = None
            job.processed_at = datetime.now(UTC).replace(tzinfo=None)
            job.claimed_at = None
        except Exception as exc:
            job.status = "queued" if job.attempts < get_settings().ingestion_worker_max_attempts else "failed"
            job.error_message = "Ingestion failed. Retry later or contact support."
            job.error_code = "INGESTION_FAILED"
            job.processed_at = datetime.now(UTC).replace(tzinfo=None) if job.status == "failed" else None
            job.claimed_at = None
        db.commit()
        return True
