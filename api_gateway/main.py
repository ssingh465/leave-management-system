"""API Gateway entry point.

The gateway is the only service exposed to clients. It authenticates every
request (except the public ``/auth/login``), logs access, and forwards the
call to the downstream microservice that owns the route, returning that
service's response unchanged.

Middleware order (outermost first): access logging wraps authentication, so
every response - including ``401``s produced by the auth layer - is logged.
A single shared ``httpx.AsyncClient`` is created on startup and reused for all
forwarded requests for connection pooling.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from api_gateway.jwt_middleware import JWTAuthMiddleware
from api_gateway.logging_middleware import AccessLogMiddleware
from api_gateway.router import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# Upstream call budget. Kept short so a stalled downstream surfaces quickly as
# a 504 rather than tying up gateway connections.
_UPSTREAM_TIMEOUT_SECONDS = 10.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=_UPSTREAM_TIMEOUT_SECONDS)
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(title="API Gateway", lifespan=lifespan)

# Added last == outermost: access logging wraps the auth check.
app.add_middleware(JWTAuthMiddleware)
app.add_middleware(AccessLogMiddleware)

app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for the gateway itself (public, no auth required)."""

    return {"status": "ok", "service": "api-gateway"}
