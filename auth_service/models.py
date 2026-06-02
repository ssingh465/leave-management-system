"""Domain model for a user identity owned by the Auth Service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from shared.enums import Role


@dataclass
class User:
    """A single pre-defined identity.

    ``manager_id`` is the self-referencing link to a manager's ``user_id``;
    it is populated for employees and left ``None`` for managers.
    """

    user_id: str
    username: str
    hashed_password: str
    role: Role
    manager_id: Optional[str] = None
