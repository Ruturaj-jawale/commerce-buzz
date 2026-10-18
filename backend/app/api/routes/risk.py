"""Card network risk assessment, entity failure analytics, and real-time decisioning routes."""

from datetime import date
import json
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_organization
from app.db.database import get_db
from app.db.models import Organization
from app.schemas.risk import (
    EntityRiskDNA,
    FailedEntitySummary,
    RealTimeRiskEvaluationRequest,
    RealTimeRiskEvaluationResponse,
    RiskAssessmentSummary,
    StatementIngestionResponse,
    SystemLensProfile,
)
from app.services.risk_service import RiskAssessmentService
from app.services.statement_ingestor import ingest_and_record_statement

router = APIRouter()
risk_service = RiskAssessmentService()


@router.get("/api/analytics/system-lens", response_model=SystemLensProfile)
def get_system_lens(
    organization: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> SystemLensProfile:
    """Auto-detects whether the workspace should be presented through Commerce Analysis or Bank/Card Network Analysis."""
    return risk_service.detect_system_lens(db, organization)



@router.get("/api/analytics/risk-assessment", response_model=RiskAssessmentSummary)
def get_risk_assessment(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    channel: str | None = Query(default=None),
    organization: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> RiskAssessmentSummary:
    """Returns organizational risk assessment across ATM, UPI, Card Swipe, and E-commerce channels."""
    return risk_service.calculate_risk_assessment(
        db, organization, start_date=start_date, end_date=end_date, channel=channel
    )


@router.get("/api/analytics/risk-entities", response_model=list[FailedEntitySummary])
def get_risk_entities(
    limit: int = Query(default=20, ge=1, le=100),
    min_failures: int = Query(default=1, ge=0),
    channel: str | None = Query(default=None),
    organization: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> list[FailedEntitySummary]:
    """Returns leaderboard of entities, merchants, and ATMs ranked by most failed and returned transactions."""
    return risk_service.get_most_failed_entities(
        db, organization, limit=limit, min_failures=min_failures, channel=channel
    )


@router.get("/api/analytics/risk-dna/{entity_name}", response_model=EntityRiskDNA)
def get_entity_risk_dna(
    entity_name: str,
    organization: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> EntityRiskDNA:
    """Returns multi-dimensional Decline DNA and cross-rail commerce correlation for an entity."""
    return risk_service.get_entity_risk_dna(db, organization, entity_name)


@router.post("/api/risk/evaluate", response_model=RealTimeRiskEvaluationResponse)
def evaluate_realtime_risk(
    request: RealTimeRiskEvaluationRequest,
    organization: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> RealTimeRiskEvaluationResponse:
    """Real-Time Card Network Integration Middleware (Mastercard/Visa -> SaaS MCP -> Bank).

    Evaluates authorization requests in real-time, providing an instant decision
    (APPROVE, REVIEW, DECLINE) and risk advisory.
    """
    return risk_service.evaluate_realtime_risk(db, organization, request)


@router.post("/api/analytics/statements/upload", response_model=StatementIngestionResponse)
@router.post("/api/risk/statements/upload", response_model=StatementIngestionResponse)
async def upload_statement(
    file: UploadFile = File(...),
    password: str | None = Form(default=None),
    bank_preset: str | None = Form(default=None),
    custom_headers: str | None = Form(default=None),
    organization: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> StatementIngestionResponse:
    """Upload and ingest a bank or card statement (CSV, Excel, or PDF).
    Automatically sanitizes PII/PCI, parses narrations, creates normalized payments,
    and atomically reconciles debit-credit reversals.
    """
    content = await file.read()
    headers_dict = None
    if custom_headers:
        try:
            headers_dict = json.loads(custom_headers)
        except Exception:
            pass

    return ingest_and_record_statement(
        db=db,
        organization=organization,
        content=content,
        filename=file.filename or "statement.csv",
        pdf_password=password,
        bank_preset=bank_preset,
        custom_headers=headers_dict,
    )
