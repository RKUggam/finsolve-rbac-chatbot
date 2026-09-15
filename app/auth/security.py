"""Password hashing and JWT issuance / verification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext

from app.auth.models import TokenData
from app.config import get_settings
from app.rbac.policy import Role

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return a bcrypt hash for a plaintext password."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    return _pwd_context.verify(plain, hashed)


def create_access_token(username: str, role: Role) -> str:
    """Mint a signed JWT for the given principal."""
    settings = get_settings()
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": username,
        "role": role.value,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenData:
    """Decode and validate a JWT. Raises jwt.PyJWTError on any problem."""
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    username = payload.get("sub")
    role_value = payload.get("role")
    if not username or not role_value:
        raise jwt.InvalidTokenError("Token missing required claims")
    return TokenData(username=username, role=Role(role_value))
