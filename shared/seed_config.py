"""Single source of truth for the system's pre-defined identities.

The platform has no self-registration: a small, fixed set of users is loaded
into the Auth Service at startup, and the Leave Balance Service initialises
balance records for those same users. Because the stores live in separate
services that never share a database, every service must agree on the exact
``user_id`` values. This module pins those IDs (and the seed credentials) so
that a JWT ``sub`` minted by the Auth Service lines up with the
``employee_id`` on a balance record and the ``reporting_manager_id`` on a
leave request across service boundaries.

The UUIDs here are intentionally static and human-readable. They are NOT
secrets; the passwords are development-only seed values documented in the
README.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from shared.enums import Role

# Fixed identity UUIDs. Static (not generated) so all services agree on IDs.
MANAGER1_ID = "00000000-0000-0000-0000-000000000001"
EMP1_ID = "00000000-0000-0000-0000-000000000002"
EMP2_ID = "00000000-0000-0000-0000-000000000003"


@dataclass(frozen=True)
class SeedUser:
    """A pre-defined account shared across services.

    ``password`` is the plain-text development credential; it is hashed by the
    Auth Service at seed time and never persisted in clear text.
    ``manager_id`` is set for employees and ``None`` for managers.
    """

    user_id: str
    username: str
    password: str
    role: Role
    manager_id: Optional[str] = None


SEED_USERS: list[SeedUser] = [
    SeedUser(
        user_id=MANAGER1_ID,
        username="manager1",
        password="Manager@123",
        role=Role.MANAGER,
        manager_id=None,
    ),
    SeedUser(
        user_id=EMP1_ID,
        username="emp1",
        password="Employee@123",
        role=Role.EMPLOYEE,
        manager_id=MANAGER1_ID,
    ),
    SeedUser(
        user_id=EMP2_ID,
        username="emp2",
        password="Employee@123",
        role=Role.EMPLOYEE,
        manager_id=MANAGER1_ID,
    ),
]


def get_seed_employees() -> list[SeedUser]:
    """Return the seeded users whose role is ``EMPLOYEE``."""

    return [user for user in SEED_USERS if user.role == Role.EMPLOYEE]


# user_id -> SeedUser index, built once so cross-service lookups (team scoping,
# reporting-manager resolution, username enrichment) are O(1).
_USERS_BY_ID: dict[str, SeedUser] = {user.user_id: user for user in SEED_USERS}


def get_user(user_id: str) -> Optional[SeedUser]:
    """Resolve a seeded user by id, or ``None`` if no such user exists."""

    return _USERS_BY_ID.get(user_id)


def get_manager_id(employee_id: str) -> Optional[str]:
    """Return the reporting-manager id for an employee, or ``None``.

    Because the platform has no self-registration, the seed data is the
    complete, authoritative org chart; every service can rely on it to map an
    employee to their approving manager without a cross-service call.
    """

    user = _USERS_BY_ID.get(employee_id)
    return user.manager_id if user else None


def is_team_member(manager_id: str, employee_id: str) -> bool:
    """Return ``True`` if ``employee_id`` reports to ``manager_id``."""

    user = _USERS_BY_ID.get(employee_id)
    return bool(user and user.manager_id == manager_id)


def get_team_member_ids(manager_id: str) -> list[str]:
    """Return the ids of every employee reporting to ``manager_id``."""

    return [
        user.user_id
        for user in SEED_USERS
        if user.manager_id == manager_id
    ]
