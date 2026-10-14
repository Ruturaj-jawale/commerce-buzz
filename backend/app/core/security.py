"""Password hashing, API keys, and user session tokens."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def create_api_key() -> str:
    return f"samcp_{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str, pepper: str) -> str:
    return hmac.new(pepper.encode("utf-8"), api_key.encode("utf-8"), hashlib.sha256).hexdigest()


def create_access_token(user_id: int, organization_id: int, token_version: int = 0) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "org": organization_id,
        "tv": token_version,
        "exp": datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, int]:
    settings = get_settings()
    payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    return {
        "user_id": int(payload["sub"]),
        "organization_id": int(payload["org"]),
        "token_version": int(payload.get("tv", 0)),
    }


def verify_webhook_signature(secret: str, body: bytes, signature: str) -> bool:
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")
