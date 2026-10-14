"""Organization bootstrap, login, session management, and API-key rotation."""

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.dependencies import SESSION_COOKIE, get_current_organization, get_current_user
from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import Organization, User
from app.schemas.auth import ApiKeyCreated, ApiKeyRotateRequest, BootstrapRequest, BootstrapResponse, LoginRequest, MeResponse, OrganizationRead, RegisterRequest, RegisterResponse, SessionResponse, UserRead
from app.services.auth_service import AuthService

router = APIRouter()


def _set_session_cookie(response: Response, access_token: str) -> None:
    settings = get_settings()
    is_prod = settings.app_env == "production"
    response.set_cookie(
        SESSION_COOKIE,
        access_token,
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,
        samesite="none" if is_prod else "lax",
        secure=is_prod,
        path="/",
    )


def _require_bootstrap_token(header_token: str | None) -> None:
    settings = get_settings()
    expected = settings.bootstrap_token
    if settings.app_env == "production" or expected:
        if not expected or not header_token or not secrets.compare_digest(expected, header_token):
            raise HTTPException(status_code=403, detail="Bootstrap is restricted")


@router.post("/bootstrap", response_model=BootstrapResponse, status_code=201)
def bootstrap(
    payload: BootstrapRequest,
    x_bootstrap_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> BootstrapResponse:
    """Create an organization and return its one-time initial API key."""
    _require_bootstrap_token(x_bootstrap_token)
    return AuthService().bootstrap_organization(db, payload)


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(
    payload: RegisterRequest,
    response: Response,
    x_bootstrap_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> RegisterResponse:
    """Self-service signup: creates an organization with an owner account and signs it in."""
    if not get_settings().allow_registration:
        _require_bootstrap_token(x_bootstrap_token)
    created = AuthService().register(db, payload)
    _set_session_cookie(response, created.access_token)
    return created


@router.post("/login", response_model=SessionResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> SessionResponse:
    session = AuthService().login(db, payload)
    _set_session_cookie(response, session.access_token)
    return session


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeResponse:
    membership = next((membership for membership in user.memberships), None)
    if membership is None:
        raise HTTPException(status_code=403, detail="User has no organization")
    organization = db.get(Organization, membership.organization_id)
    if organization is None:
        raise HTTPException(status_code=401, detail="Organization no longer exists")
    return MeResponse(user=UserRead.model_validate(user), organization=OrganizationRead.model_validate(organization))


@router.post("/logout", status_code=204)
def logout(response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    AuthService().logout(db, user)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.post("/api-keys/rotate", response_model=ApiKeyCreated)
def rotate_api_key(
    payload: ApiKeyRotateRequest,
    organization: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
) -> ApiKeyCreated:
    """Revoke active machine keys and return one new key exactly once."""
    return AuthService().rotate_api_key(db, organization, payload.name)
