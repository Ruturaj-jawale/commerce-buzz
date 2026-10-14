"""Create and verify organization API keys and user sessions."""

import re
from datetime import UTC, datetime

import jwt
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_api_key,
    decode_access_token,
    hash_api_key,
    hash_password,
    verify_password,
)
from app.db.models import ApiKey, Membership, Organization, User
from app.schemas.auth import (
    ApiKeyCreated,
    BootstrapRequest,
    BootstrapResponse,
    LoginRequest,
    OrganizationRead,
    RegisterRequest,
    RegisterResponse,
    SessionResponse,
)
from app.services.audit_service import AuditService


class AuthService:
    @staticmethod
    def _create_organization_with_key(db: Session, name: str, slug: str) -> tuple[Organization, ApiKey, str]:
        organization = Organization(name=name, slug=slug)
        db.add(organization)
        db.flush()
        api_key = create_api_key()
        row = ApiKey(
            organization_id=organization.id,
            name="Initial API key",
            key_hash=hash_api_key(api_key, get_settings().api_key_pepper or get_settings().secret_key),
            key_prefix=api_key[:12],
        )
        db.add(row)
        return organization, row, api_key

    def bootstrap_organization(self, db: Session, payload: BootstrapRequest) -> BootstrapResponse:
        if db.scalar(select(Organization).where(Organization.slug == payload.organization_slug)):
            raise HTTPException(status_code=409, detail="Organization slug is already in use")
        if payload.email and db.scalar(select(User).where(User.email == payload.email.lower())):
            raise HTTPException(status_code=409, detail="Email is already in use")
        organization, row, api_key = self._create_organization_with_key(
            db, payload.organization_name.strip(), payload.organization_slug
        )
        if payload.email and payload.password:
            user = User(email=payload.email.lower(), password_hash=hash_password(payload.password))
            db.add(user)
            db.flush()
            db.add(Membership(user_id=user.id, organization_id=organization.id, role="owner"))
        db.commit()
        db.refresh(organization)
        db.refresh(row)
        AuditService().record(db, "organization.bootstrap", f"organization:{organization.id}", organization, actor="bootstrap")
        return BootstrapResponse(
            organization=OrganizationRead.model_validate(organization),
            api_key=ApiKeyCreated(id=row.id, name=row.name, key=api_key, prefix=row.key_prefix),
        )

    def register(self, db: Session, payload: RegisterRequest) -> RegisterResponse:
        """Self-service signup: create an organization, its owner user, and a live session."""
        email = payload.email.lower().strip()
        if db.scalar(select(User).where(User.email == email)):
            raise HTTPException(status_code=409, detail="Email is already in use")
        organization, row, api_key = self._create_organization_with_key(
            db, payload.organization_name.strip(), self._available_slug(db, payload.organization_name)
        )
        user = User(email=email, password_hash=hash_password(payload.password))
        db.add(user)
        db.flush()
        db.add(Membership(user_id=user.id, organization_id=organization.id, role="owner"))
        db.commit()
        db.refresh(organization)
        db.refresh(row)
        AuditService().record(db, "organization.register", f"organization:{organization.id}", organization, actor=email)
        return RegisterResponse(
            access_token=create_access_token(user.id, organization.id, user.token_version),
            organization=OrganizationRead.model_validate(organization),
            email=email,
            api_key=ApiKeyCreated(id=row.id, name=row.name, key=api_key, prefix=row.key_prefix),
        )

    @staticmethod
    def _available_slug(db: Session, organization_name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", organization_name.lower()).strip("-")[:40] or "org"
        slug = base
        counter = 2
        while db.scalar(select(Organization).where(Organization.slug == slug)):
            slug = f"{base}-{counter}"
            counter += 1
        return slug

    def organization_for_key(self, db: Session, api_key: str) -> Organization:
        key = db.scalar(
            select(ApiKey).where(
                ApiKey.key_hash == hash_api_key(api_key, get_settings().api_key_pepper or get_settings().secret_key),
                ApiKey.revoked_at.is_(None),
            )
        )
        if key is None:
            raise HTTPException(status_code=401, detail="Invalid or revoked API key")
        organization = db.get(Organization, key.organization_id)
        if organization is None:
            raise HTTPException(status_code=401, detail="API key organization no longer exists")
        return organization

    def _membership_for_token(self, db: Session, token: str) -> Membership:
        try:
            claims = decode_access_token(token)
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail="Invalid or expired session") from exc
        user = db.get(User, claims["user_id"])
        if user is None or user.token_version != claims["token_version"]:
            raise HTTPException(status_code=401, detail="Session has been revoked")
        membership = db.scalar(
            select(Membership).where(
                Membership.user_id == claims["user_id"],
                Membership.organization_id == claims["organization_id"],
            )
        )
        if membership is None:
            raise HTTPException(status_code=401, detail="Session is not authorized for this organization")
        return membership

    def organization_for_token(self, db: Session, token: str) -> Organization:
        membership = self._membership_for_token(db, token)
        organization = db.get(Organization, membership.organization_id)
        if organization is None:
            raise HTTPException(status_code=401, detail="Organization no longer exists")
        return organization

    def user_for_token(self, db: Session, token: str) -> User:
        membership = self._membership_for_token(db, token)
        user = db.get(User, membership.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="User no longer exists")
        return user

    def logout(self, db: Session, user: User) -> None:
        user.token_version += 1
        db.commit()
        AuditService().record(db, "user.logout", f"user:{user.id}", None, actor=user.email)

    def login(self, db: Session, payload: LoginRequest) -> SessionResponse:
        user = db.scalar(select(User).where(User.email == payload.email.lower()))
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        membership = db.scalar(select(Membership).where(Membership.user_id == user.id).order_by(Membership.id))
        if membership is None:
            raise HTTPException(status_code=403, detail="User has no organization")
        organization = db.get(Organization, membership.organization_id)
        if organization is None:
            raise HTTPException(status_code=401, detail="Organization no longer exists")
        AuditService().record(db, "user.login", f"user:{user.id}", organization, actor=user.email)
        return SessionResponse(
            access_token=create_access_token(user.id, organization.id, user.token_version),
            organization=OrganizationRead.model_validate(organization),
            email=user.email,
        )

    def rotate_api_key(self, db: Session, organization: Organization, name: str) -> ApiKeyCreated:
        active_keys = db.scalars(
            select(ApiKey).where(ApiKey.organization_id == organization.id, ApiKey.revoked_at.is_(None))
        ).all()
        for key in active_keys:
            key.revoked_at = datetime.now(UTC).replace(tzinfo=None)
        api_key = create_api_key()
        row = ApiKey(
            organization_id=organization.id,
            name=name,
            key_hash=hash_api_key(api_key, get_settings().api_key_pepper or get_settings().secret_key),
            key_prefix=api_key[:12],
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        AuditService().record(db, "api_key.rotate", f"api_key:{row.id}", organization, actor=row.key_prefix)
        return ApiKeyCreated(id=row.id, name=row.name, key=api_key, prefix=row.key_prefix)
