"""Request and response payload models for the Auth Service API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Credentials supplied to ``POST /auth/login``."""

    username: str = Field(..., min_length=1, description="Unique login name.")
    password: str = Field(
        ..., min_length=1, description="Plain-text password to verify."
    )


class LoginResponse(BaseModel):
    """Successful login result carrying the signed access token."""

    access_token: str
    token_type: str = "bearer"
