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
