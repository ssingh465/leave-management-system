"""JWT creation and verification helpers shared by every microservice.

The Auth Service issues access tokens via :func:`create_access_token`; the
API Gateway and downstream services verify and read those tokens via
:func:`decode_token`. Centralising both functions here guarantees that every
service signs and validates with identical secret, algorithm, and lifetime
settings, so a token minted by one service is trusted by all the others.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt

from shared.config import settings
from shared.enums import Role


def create_access_token(user_id: str, role: Role | str) -> str:
    """Build and sign an HS256 access token for the given user.

    The payload carries exactly three claims: ``sub`` (the user id), ``role``
    (the user's role as a plain string), and ``exp`` (an absolute expiry
    computed from the configured token lifetime).
    """

    role_value = role.value if isinstance(role, Role) else str(role)
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expiration_minutes
    )
    payload = {"sub": user_id, "role": role_value, "exp": expire}
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_token(token: str) -> dict:
    """Verify a token's signature and expiry and return its claim set.

    Raises a 401 ``HTTPException`` if the token is malformed, has an invalid
    signature, or has expired.
    """

    try:
        return jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
