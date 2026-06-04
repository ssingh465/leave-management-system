"""Auth Service entry point.

Exposes a single public endpoint, ``POST /auth/login``. Identities are loaded
into an in-memory store at startup. A submitted password is checked against the
stored BCrypt hash; on success the service returns an HS256-signed token that
carries the user id and role. Unknown usernames and bad passwords both return
an identical 401 so the API does not reveal which accounts exist.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status

from auth_service.schemas import LoginRequest, LoginResponse
from auth_service.seed import seed_users, verify_password
from auth_service.store import get_by_username
from shared.config import settings
from shared.consul_client import deregister_service, register_service
from shared.exception_handlers import register_global_exception_handler
from shared.jwt_utils import create_access_token
from shared.tracing import init_tracing, instrument_fastapi

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("auth_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_tracing(settings.service_name)
    register_service(
        settings.service_name, settings.service_host, settings.service_port
    )
    seed_users()
    try:
        yield
    finally:
        deregister_service(
            settings.service_name, settings.service_host, settings.service_port
        )


app = FastAPI(title="Auth Service", lifespan=lifespan)
register_global_exception_handler(app)
instrument_fastapi(app)


@app.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    user = get_by_username(payload.username)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_access_token(user.user_id, user.role)
    return LoginResponse(access_token=token, token_type="bearer")


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe (public)."""

    return {"status": "ok", "service": "auth-service"}
