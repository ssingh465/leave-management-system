"""Seed loader that populates the Auth Service user store at startup.

The system has no self-registration: a fixed set of identities is loaded into
the in-memory store when the service boots. Each password is BCrypt-hashed
here; the plain-text value exists only transiently to produce the hash and is
never persisted.

Default seeded accounts (username / password):
    manager1 / Manager@123    role=MANAGER
    emp1     / Employee@123   role=EMPLOYEE, reports to manager1
    emp2     / Employee@123   role=EMPLOYEE, reports to manager1
"""

from __future__ import annotations

import uuid

from passlib.context import CryptContext

from auth_service.models import User
from auth_service.store import add_user, users_store
from shared.enums import Role

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_MANAGER = ("manager1", "Manager@123")
_EMPLOYEES = [
    ("emp1", "Employee@123"),
    ("emp2", "Employee@123"),
]


def hash_password(plaintext: str) -> str:
    """Return a BCrypt hash for a plain-text password."""

    return pwd_context.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    """Check a plain-text password against a stored BCrypt hash."""

    return pwd_context.verify(plaintext, hashed)


def seed_users() -> None:
    """Load the pre-defined accounts into the store (idempotent)."""

    if users_store:
        return

    manager = User(
        user_id=str(uuid.uuid4()),
        username=_MANAGER[0],
        hashed_password=hash_password(_MANAGER[1]),
        role=Role.MANAGER,
        manager_id=None,
    )
    add_user(manager)

    for username, password in _EMPLOYEES:
        add_user(
            User(
                user_id=str(uuid.uuid4()),
                username=username,
                hashed_password=hash_password(password),
                role=Role.EMPLOYEE,
                manager_id=manager.user_id,
            )
        )
