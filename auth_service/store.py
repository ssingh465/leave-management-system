"""In-memory user identity store for the Auth Service.

Holds every seeded user keyed by ``user_id`` and a secondary
``username -> user_id`` index that backs the login lookup. Both structures are
module-level singletons that live for the lifetime of the process. There are
no API paths that mutate this store; it is populated only by the seed loader.
"""

from __future__ import annotations

from typing import Optional

from auth_service.models import User

users_store: dict[str, User] = {}
username_index: dict[str, str] = {}


def add_user(user: User) -> None:
    """Insert a user and maintain the username index."""

    users_store[user.user_id] = user
    username_index[user.username] = user.user_id


def get_by_username(username: str) -> Optional[User]:
    """Resolve a user by login name, or ``None`` if no such user exists."""

    user_id = username_index.get(username)
    if user_id is None:
        return None
    return users_store.get(user_id)
