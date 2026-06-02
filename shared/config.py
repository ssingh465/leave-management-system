"""Centralised environment-variable configuration for every microservice.

Each service imports `settings` from this module. The values are loaded
once at import time from the process environment (and optionally from a
local `.env` file via `python-dotenv` during development).

Supported variables:

    JWT_SECRET_KEY
    JWT_ALGORITHM
    JWT_EXPIRATION_MINUTES
    RABBITMQ_URL
    CONSUL_URL
    SERVICE_NAME
    SERVICE_HOST
    SERVICE_PORT
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is in requirements.txt
    pass


def _get_str(key: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(key, default)
    if required and (value is None or value == ""):
        raise RuntimeError(f"Required environment variable '{key}' is not set")
    return value or ""


def _get_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable '{key}' must be an integer, got '{raw}'") from exc


@dataclass(frozen=True)
class Settings:
    """Immutable, structured view of the process configuration."""

    jwt_secret_key: str
    jwt_algorithm: str
    jwt_expiration_minutes: int
    rabbitmq_url: str
    consul_url: str
    service_name: str
    service_host: str
    service_port: int


settings = Settings(
    jwt_secret_key=_get_str(
        "JWT_SECRET_KEY",
        default="dev-only-change-me-in-production",
    ),
    jwt_algorithm=_get_str("JWT_ALGORITHM", default="HS256"),
    jwt_expiration_minutes=_get_int("JWT_EXPIRATION_MINUTES", default=60),
    rabbitmq_url=_get_str(
        "RABBITMQ_URL",
        default="amqp://guest:guest@rabbitmq:5672/",
    ),
    consul_url=_get_str("CONSUL_URL", default="http://consul:8500"),
    service_name=_get_str("SERVICE_NAME", default="unknown-service"),
    service_host=_get_str("SERVICE_HOST", default="localhost"),
    service_port=_get_int("SERVICE_PORT", default=8000),
)
