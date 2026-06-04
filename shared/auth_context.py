"""Caller-identity propagation for downstream microservices.

Only the API Gateway validates the JWT. After it does, it forwards the
verified identity to the owning service as two headers - ``X-User-Id`` and
``X-User-Role`` - and the downstream service trusts them (its public routes
are never reachable from outside the Docker network without passing through
the gateway). This module turns those headers into a typed
:class:`CallerIdentity` via FastAPI dependencies, and offers a role guard so
endpoints can enforce role-based authorization declaratively.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from shared.enums import Role


@dataclass(frozen=True)
class CallerIdentity:
    """The authenticated caller as resolved from gateway-injected headers."""

    user_id: str
    role: Role


async def get_caller(
    x_user_id: Optional[str] = Header(default=None),
    x_user_role: Optional[str] = Header(default=None),
) -> CallerIdentity:
    """Resolve the caller from the ``X-User-Id`` / ``X-User-Role`` headers.

    Raises ``401`` if either header is absent or the role is unrecognised.
    A request that reaches a public route without these headers did not pass
    through the gateway and is therefore treated as unauthenticated.
    """

    if not x_user_id or not x_user_role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authenticated user context",
        )
    try:
        role = Role(x_user_role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user role in request context",
        ) from exc
    return CallerIdentity(user_id=x_user_id, role=role)


async def require_manager(
    caller: CallerIdentity = Depends(get_caller),
) -> CallerIdentity:
    """Dependency that allows only callers whose role is ``MANAGER`` (else 403).

    Composed with :func:`get_caller`; intended for manager-only endpoints.
    """

    if caller.role != Role.MANAGER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires a manager role",
        )
    return caller
