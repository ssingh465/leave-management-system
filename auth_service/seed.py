"""Seed loader that populates the Auth Service user store at startup.

The system has no self-registration: a fixed set of identities (defined once
in :mod:`shared.seed_config`) is loaded into the in-memory store when the
service boots. Each password is BCrypt-hashed here; the plain-text value
exists only transiently to produce the hash and is never persisted.

Default seeded accounts (username / password):
    manager1 / Manager@123    role=MANAGER
    emp1     / Employee@123   role=EMPLOYEE, reports to manager1
    emp2     / Employee@123   role=EMPLOYEE, reports to manager1
"""

from __future__ import annotations

from passlib.context import CryptContext

from auth_service.models import User
from auth_service.store import add_user, users_store
from shared.seed_config import SEED_USERS

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plaintext: str) -> str:
    """Return a BCrypt hash for a plain-text password."""

    return pwd_context.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    """Check a plain-text password against a stored BCrypt hash."""

    return pwd_context.verify(plaintext, hashed)


def seed_users() -> None:
    """Load the pre-defined accounts into the store (idempotent).

    User ids come from :mod:`shared.seed_config` so they match the
    ``employee_id`` and ``reporting_manager_id`` values used by the other
    services.
    """

    if users_store:
        return

    for seed_user in SEED_USERS:
        add_user(
            User(
                user_id=seed_user.user_id,
                username=seed_user.username,
                hashed_password=hash_password(seed_user.password),
                role=seed_user.role,
                manager_id=seed_user.manager_id,
            )
        )
