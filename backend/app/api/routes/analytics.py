"""First-party analytics HTTP routes."""

import csv
import io

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_organization
from app.db.database import get_db
from app.db.models import Organization
from datetime import date

from app.schemas.analytics import (
    AnalyticsEventRead,
    AnalyticsSummary,
    CommerceEventIngest,
    CustomerMetrics,
    IngestionJobRead,
    PaymentMetrics,
    ProductMetric,
    RecoveryMetrics,
    RefundSummary,
    TransactionPage,
)
from app.schemas.payments import RevenueAtRisk
from app.services.analytics_service import AnalyticsService
from app.services.ingestion_job_service import IngestionJobService

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
_service = AnalyticsService()
_jobs = IngestionJobService()


@router.get("/summary", response_model=AnalyticsSummary)
def analytics_summary(start_date: date | None = None, end_date: date | None = None, organization: Organization = Depends(get_current_organization), db: Session = Depends(get_db)) -> AnalyticsSummary:
    return _service.summary(db, organization, start_date, end_date)


@router.get("/top-products", response_model=list[ProductMetric])
def top_products(start_date: date | None = None, end_date: date | None = None, limit: int = 10, organization: Organization = Depends(get_current_organization), db: Session = Depends(get_db)) -> list[ProductMetric]:
    return _service.top_products(db, organization, start_date, end_date, min(max(limit, 1), 100))


@router.get("/customer-metrics", response_model=CustomerMetrics)
def customer_metrics(start_date: date | None = None, end_date: date | None = None, organization: Organization = Depends(get_current_organization), db: Session = Depends(get_db)) -> CustomerMetrics:
    return _service.customer_metrics(db, organization, start_date, end_date)


@router.get("/refund-summary", response_model=RefundSummary)
def refund_summary(start_date: date | None = None, end_date: date | None = None, organization: Organization = Depends(get_current_organization), db: Session = Depends(get_db)) -> RefundSummary:
    return _service.refund_summary(db, organization, start_date, end_date)


@router.get("/payment-metrics", response_model=PaymentMetrics)
def payment_metrics(start_date: date | None = None, end_date: date | None = None, organization: Organization = Depends(get_current_organization), db: Session = Depends(get_db)) -> PaymentMetrics:
    return _service.payment_metrics(db, organization, start_date, end_date)


@router.get("/payment-recovery", response_model=RecoveryMetrics)
def payment_recovery(start_date: date | None = None, end_date: date | None = None, organization: Organization = Depends(get_current_organization), db: Session = Depends(get_db)) -> RecoveryMetrics:
    return _service.payment_recovery(db, organization, start_date, end_date)


@router.get("/revenue-at-risk", response_model=RevenueAtRisk)
def revenue_at_risk(organization: Organization = Depends(get_current_organization), db: Session = Depends(get_db)) -> RevenueAtRisk:
    return _service._payments.revenue_at_risk(db, organization)


@router.get("/events", response_model=list[AnalyticsEventRead])
def analytics_events(organization: Organization = Depends(get_current_organization), db: Session = Depends(get_db)) -> list[AnalyticsEventRead]:
    return _service.list_events(db, organization)


@router.get("/transactions", response_model=TransactionPage)
def transactions(
    query: str | None = None, status: str | None = None, currency: str | None = None, source: str | None = None,
    page: int = 1, page_size: int = 25, organization: Organization = Depends(get_current_organization), db: Session = Depends(get_db),
) -> TransactionPage:
    return _service.transactions(db, organization, query, status, currency, source, page, page_size)


@router.get("/transactions/export")
def export_transactions(
    query: str | None = None, status: str | None = None, currency: str | None = None, source: str | None = None,
    organization: Organization = Depends(get_current_organization), db: Session = Depends(get_db),
) -> Response:
    rows = _service.transactions(db, organization, query, status, currency, source, 1, 100).items
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Transaction ID", "Order ID", "Date & Time", "Customer", "Source", "Payment Method", "Amount", "Currency", "Status"])
    for row in rows:
        writer.writerow([row.id, row.order_id or "", row.occurred_at.isoformat(), row.customer_id or "", row.source, row.payment_method or "", row.amount, row.currency, row.status])
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=transactions.csv"})


@router.post("/sources/{storefront_id}/events", response_model=AnalyticsEventRead)
def ingest_event(
    storefront_id: int,
    payload: CommerceEventIngest,
    organization: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> AnalyticsEventRead:
    return _service.ingest(db, organization, storefront_id, payload)


@router.post("/sources/{storefront_id}/ingestion-jobs", response_model=IngestionJobRead, status_code=202)
def queue_event(
    storefront_id: int,
    payload: CommerceEventIngest,
    organization: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> IngestionJobRead:
    """Queue ingestion for the independently deployed worker instead of processing in the API request."""
    return _jobs.enqueue(db, organization, storefront_id, payload)


@router.get("/ingestion-jobs/{job_id}", response_model=IngestionJobRead)
def get_ingestion_job(
    job_id: int,
    organization: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> IngestionJobRead:
    return _jobs.get(db, organization, job_id)


@router.post("/sources/{storefront_id}/sample-purchase", response_model=AnalyticsEventRead)
def sample_purchase(storefront_id: int, organization: Organization = Depends(get_current_organization), db: Session = Depends(get_db)) -> AnalyticsEventRead:
    return _service.ingest_sample_purchase(db, organization, storefront_id)
