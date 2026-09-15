"""Authentication — password hashing, JWT round-trip, and the user repository."""

from __future__ import annotations

import jwt
import pytest

from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.auth.users import get_user_repository
from app.rbac.policy import Role


def test_password_hash_roundtrip():
    hashed = hash_password("FinSolve@2024")
    assert hashed != "FinSolve@2024"
    assert verify_password("FinSolve@2024", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_roundtrip_preserves_username_and_role():
    token = create_access_token("finance.lead", Role.FINANCE)
    data = decode_access_token(token)
    assert data.username == "finance.lead"
    assert data.role == Role.FINANCE


def test_tampered_token_rejected():
    token = create_access_token("cfo", Role.C_LEVEL)
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token + "tamper")


def test_seed_repository_authenticates_demo_users():
    repo = get_user_repository()
    user = repo.authenticate("hr.lead", "FinSolve@2024")
    assert user is not None
    assert user.role == Role.HR
    assert repo.authenticate("hr.lead", "bad-password") is None
    assert repo.authenticate("ghost", "FinSolve@2024") is None
