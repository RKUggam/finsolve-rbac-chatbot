"""In-memory user repository seeded from `users_seed.json`.

For a production deployment, swap `UserRepository` for one backed by a real
identity provider (Azure AD / Entra ID, a database, etc.). The rest of the
application only depends on the small `get_user` / `authenticate` surface, so
that replacement is isolated to this file.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.auth.models import UserInDB
from app.auth.security import hash_password, verify_password
from app.logging_config import get_logger
from app.rbac.policy import Role

logger = get_logger(__name__)

_SEED_PATH = Path(__file__).parent / "users_seed.json"


class UserRepository:
    """Simple username -> UserInDB store."""

    def __init__(self, users: dict[str, UserInDB]) -> None:
        self._users = users

    @classmethod
    def from_seed(cls, seed_path: Path = _SEED_PATH) -> UserRepository:
        """Build a repository by hashing the plaintext passwords in the seed file."""
        raw = json.loads(seed_path.read_text(encoding="utf-8"))
        users: dict[str, UserInDB] = {}
        for entry in raw.get("users", []):
            users[entry["username"]] = UserInDB(
                username=entry["username"],
                full_name=entry["full_name"],
                role=Role(entry["role"]),
                hashed_password=hash_password(entry["password"]),
            )
        logger.info("user_repository_loaded", count=len(users))
        return cls(users)

    def get_user(self, username: str) -> UserInDB | None:
        return self._users.get(username)

    def authenticate(self, username: str, password: str) -> UserInDB | None:
        """Return the user iff credentials are valid and the account is enabled."""
        user = self.get_user(username)
        if user is None or user.disabled:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user


@lru_cache
def get_user_repository() -> UserRepository:
    """Return a cached UserRepository singleton."""
    return UserRepository.from_seed()
