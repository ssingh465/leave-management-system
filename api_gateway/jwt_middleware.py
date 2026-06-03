"""Authentication middleware for the API Gateway.

The gateway is the single security boundary in front of the platform: every
request that is not explicitly public must carry a valid ``Authorization:
Bearer <token>`` header. This middleware enforces that contract before a
request ever reaches a route handler, returning ``401`` for a missing,
malformed, invalid, or expired token.

On success the decoded claims are stashed on ``request.state.user`` so the
router can forward the caller's identity (``sub``/``role``) to downstream
services as headers. Downstream services therefore never re-validate the JWT;
they trust the gateway, and their internal endpoints are unreachable from
outside the Docker network.
"""

from __future__ import annotations

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from shared.jwt_utils import decode_token

# Paths that bypass authentication entirely. ``/auth/login`` must be public so
# clients can obtain a token in the first place; the docs/openapi/health paths
# are operational conveniences served by the gateway itself.
PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/auth/login",
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Reject unauthenticated requests to protected routes with a 401."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        scheme, _, token = auth_header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return _unauthorized("Missing or malformed Authorization header")

        try:
            claims = decode_token(token.strip())
        except Exception:  # noqa: BLE001 - decode_token raises HTTPException(401)
            return _unauthorized("Invalid or expired authentication token")

        # Make the verified identity available to downstream forwarding.
        request.state.user = claims
        return await call_next(request)
