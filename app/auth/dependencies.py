"""FastAPI dependencies for extracting and validating the current user.

Tokens are accepted from either an `Authorization: Bearer <jwt>` header (API
clients) or an `access_token` cookie (the server-rendered web UI). This lets the
same endpoints serve both without duplicating auth logic.
"""

from __future__ import annotations

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, status

from app.auth.models import User
from app.auth.security import decode_access_token
from app.auth.users import UserRepository, get_user_repository

_UNAUTHORISED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def _extract_token(authorization: str | None, cookie_token: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    if cookie_token:
        return cookie_token
    raise _UNAUTHORISED


def get_current_user(
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
    repo: UserRepository = Depends(get_user_repository),
) -> User:
    """Resolve, validate, and return the authenticated user."""
    token = _extract_token(authorization, access_token)
    try:
        token_data = decode_access_token(token)
    except jwt.PyJWTError as exc:  # expired, bad signature, malformed, ...
        raise _UNAUTHORISED from exc

    user = repo.get_user(token_data.username)
    if user is None or user.disabled:
        raise _UNAUTHORISED
    return User(username=user.username, full_name=user.full_name, role=user.role)
