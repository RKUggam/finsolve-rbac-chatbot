"""Auth-related Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.rbac.policy import Role


class User(BaseModel):
    """An authenticated principal."""

    username: str
    full_name: str
    role: Role
    disabled: bool = False


class UserInDB(User):
    """User record as stored, including the bcrypt password hash."""

    hashed_password: str


class Token(BaseModel):
    """OAuth2-style bearer token response."""

    access_token: str
    token_type: str = "bearer"
    role: Role
    full_name: str


class TokenData(BaseModel):
    """Decoded JWT claims we care about."""

    username: str
    role: Role


class LoginRequest(BaseModel):
    """JSON login payload (used by the web UI / API clients)."""

    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
