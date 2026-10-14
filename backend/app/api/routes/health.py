"""Health HTTP routes."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.db.database import SessionLocal
from app.schemas.health import HealthResponse
from app.services.health_service import HealthService

router = APIRouter(tags=["health"])
_health_service = HealthService()


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    payload = _health_service.get_status()
    return HealthResponse(status=payload["status"])


@router.get("/ready", response_model=HealthResponse)
def get_readiness() -> HealthResponse:
    """Cloud readiness probe: traffic reaches this process only when the database is reachable."""
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    finally:
        db.close()
    return HealthResponse(status="ok")
