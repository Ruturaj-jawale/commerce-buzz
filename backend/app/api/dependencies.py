"""Request-scoped organization authentication via API key or user session."""

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Organization, User
from app.services.auth_service import AuthService

SESSION_COOKIE = "session"


def get_current_organization(
    request: Request,
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Organization:
    if x_api_key:
        return AuthService().organization_for_key(db, x_api_key)
    token = _session_token(request, authorization)
    if token:
        return AuthService().organization_for_token(db, token)
    raise HTTPException(status_code=401, detail="Authentication required")


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = _session_token(request, authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return AuthService().user_for_token(db, token)


def _session_token(request: Request, authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return request.cookies.get(SESSION_COOKIE)
