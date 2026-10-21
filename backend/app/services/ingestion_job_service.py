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

    def claim_next(self, db: Session, import_batch_id: int | None = None) -> IngestionJob | None:
        lease_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=get_settings().ingestion_worker_lease_seconds)
        stmt = (
            select(IngestionJob)
            .where(
                or_(
                    IngestionJob.status == "queued",
                    (IngestionJob.status == "processing")
                    & (
                        IngestionJob.claimed_at.is_(None)
                        | (IngestionJob.claimed_at < lease_cutoff)
                    ),
                ),
                or_(
                    IngestionJob.attempts.is_(None),
                    IngestionJob.attempts < get_settings().ingestion_worker_max_attempts,
                ),
            )
            .order_by(IngestionJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if import_batch_id is not None:
            stmt = stmt.where(IngestionJob.import_batch_id == import_batch_id)

        job = db.scalar(stmt)
        if job is None:
            return None
        job.status = "processing"
        job.claimed_at = datetime.now(UTC).replace(tzinfo=None)
        job.attempts = (job.attempts or 0) + 1
        db.commit()
        db.refresh(job)
        return job

    def process_next(self, db: Session, import_batch_id: int | None = None) -> bool:
        job = self.claim_next(db, import_batch_id=import_batch_id)
        if job is None:
            return False
        job_id = job.id
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
            db.rollback()
            refreshed = db.get(IngestionJob, job_id)
            if refreshed is not None:
                refreshed.status = "queued" if (refreshed.attempts or 0) < get_settings().ingestion_worker_max_attempts else "failed"
                refreshed.error_message = str(exc)[:500]
                refreshed.error_code = "INGESTION_FAILED"
                refreshed.processed_at = datetime.now(UTC).replace(tzinfo=None) if refreshed.status == "failed" else None
                refreshed.claimed_at = None
        db.commit()
        return True

    def drain_batch(self, db: Session, batch_id: int, max_jobs: int = 500) -> int:
        """Process queued ingestion jobs for a specific import batch synchronously."""
        processed = 0
        for _ in range(max_jobs):
            if not self.process_next(db, import_batch_id=batch_id):
                break
            processed += 1
        return processed
