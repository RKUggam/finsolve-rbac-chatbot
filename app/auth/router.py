"""Authentication endpoints: login, logout, and current-user lookup."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth.dependencies import get_current_user
from app.auth.models import LoginRequest, Token, User
from app.auth.security import create_access_token
from app.auth.users import UserRepository, get_user_repository
from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(
    payload: LoginRequest,
    response: Response,
    repo: UserRepository = Depends(get_user_repository),
) -> Token:
    """Validate credentials, set a session cookie, and return a bearer token."""
    user = repo.authenticate(payload.username, payload.password)
    if user is None:
        logger.warning("login_failed", username=payload.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    token = create_access_token(user.username, user.role)
    settings = get_settings()
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )
    logger.info("login_success", username=user.username, role=user.role.value)
    return Token(access_token=token, role=user.role, full_name=user.full_name)


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    """Clear the session cookie."""
    response.delete_cookie("access_token")
    return {"detail": "logged out"}


@router.get("/me", response_model=User)
def me(current_user: User = Depends(get_current_user)) -> User:
    """Return the currently authenticated user (used by the UI on load)."""
    return current_user
