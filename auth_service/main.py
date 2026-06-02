"""Auth Service entry point.

Exposes a single public endpoint, ``POST /auth/login``. Identities are loaded
into an in-memory store at startup. A submitted password is checked against the
stored BCrypt hash; on success the service returns an HS256-signed token that
carries the user id and role. Unknown usernames and bad passwords both return
an identical 401 so the API does not reveal which accounts exist.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status

from auth_service.schemas import LoginRequest, LoginResponse
from auth_service.seed import seed_users, verify_password
from auth_service.store import get_by_username
from shared.jwt_utils import create_access_token


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_users()
    yield


app = FastAPI(title="Auth Service", lifespan=lifespan)


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
