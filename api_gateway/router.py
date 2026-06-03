"""Route table and request forwarding for the API Gateway.

Declares the nine public routes of the platform and maps each to the logical
downstream service that owns it. All handlers funnel through :func:`_forward`,
which resolves the service address (via Consul, with a static fallback),
replays the original method/path/query/body over a shared httpx client, and
streams the downstream response back to the caller.

The gateway path always equals the downstream path, so forwarding simply
reuses ``request.url.path``. The caller's verified identity - placed on
``request.state.user`` by the auth middleware - is injected as
``X-User-Id`` / ``X-User-Role`` headers so downstream services can authorize
without re-validating the JWT.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse

from api_gateway import consul_resolver

logger = logging.getLogger("api_gateway.router")

router = APIRouter()

# Logical service that owns each route, keyed for clarity in the handlers.
AUTH_SERVICE = "auth-service"
BALANCE_SERVICE = "leave-balance-service"
REQUEST_SERVICE = "leave-request-service"
MANAGER_SERVICE = "manager-service"

# Headers we must not copy verbatim between client<->gateway<->service.
# Hop-by-hop headers are connection-specific; content-length/encoding are
# recomputed by httpx and by the response we return.
_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
)


def _build_forward_headers(request: Request) -> dict[str, str]:
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP
    }
    user = getattr(request.state, "user", None)
    if user:
        if user.get("sub"):
            headers["X-User-Id"] = str(user["sub"])
        if user.get("role"):
            headers["X-User-Role"] = str(user["role"])
    return headers


def _build_response(downstream: httpx.Response) -> Response:
    headers = {
        key: value
        for key, value in downstream.headers.items()
        if key.lower() not in _HOP_BY_HOP and key.lower() != "content-encoding"
    }
    return Response(
        content=downstream.content,
        status_code=downstream.status_code,
        headers=headers,
        media_type=downstream.headers.get("content-type"),
    )


async def _forward(request: Request, service_name: str) -> Response:
    """Forward the current request to ``service_name`` and return its response."""

    base_url = consul_resolver.resolve(service_name)
    target_url = f"{base_url}{request.url.path}"

    client: httpx.AsyncClient = request.app.state.http_client
    body = await request.body()

    try:
        downstream = await client.request(
            method=request.method,
            url=target_url,
            params=dict(request.query_params),
            headers=_build_forward_headers(request),
            content=body,
        )
    except httpx.TimeoutException:
        logger.warning("Timeout forwarding to %s (%s)", service_name, target_url)
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={"detail": f"Upstream service '{service_name}' timed out"},
        )
    except httpx.RequestError as exc:
        logger.warning("Failed to reach %s (%s): %s", service_name, target_url, exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": f"Upstream service '{service_name}' is unavailable"},
        )

    return _build_response(downstream)


# ---------------------------------------------------------------------------
# Auth (public) - 1 route
# ---------------------------------------------------------------------------
@router.post("/auth/login")
async def login(request: Request) -> Response:
    return await _forward(request, AUTH_SERVICE)


# ---------------------------------------------------------------------------
# Leave Balance - 2 routes
# ---------------------------------------------------------------------------
@router.get("/employees/me/balances")
async def my_balances(request: Request) -> Response:
    return await _forward(request, BALANCE_SERVICE)


@router.get("/employees/{employee_id}/balances")
async def employee_balances(request: Request, employee_id: str) -> Response:
    return await _forward(request, BALANCE_SERVICE)


# ---------------------------------------------------------------------------
# Leave Request - 3 routes
# ---------------------------------------------------------------------------
@router.post("/leaves")
async def apply_leave(request: Request) -> Response:
    return await _forward(request, REQUEST_SERVICE)


@router.get("/leaves/history")
async def leave_history(request: Request) -> Response:
    return await _forward(request, REQUEST_SERVICE)


@router.patch("/leaves/{leave_id}/cancel")
async def cancel_leave(request: Request, leave_id: str) -> Response:
    return await _forward(request, REQUEST_SERVICE)


# ---------------------------------------------------------------------------
# Manager - 3 routes
# ---------------------------------------------------------------------------
@router.get("/manager/requests")
async def manager_requests(request: Request) -> Response:
    return await _forward(request, MANAGER_SERVICE)


@router.post("/manager/requests/{request_id}/approve")
async def approve_request(request: Request, request_id: str) -> Response:
    return await _forward(request, MANAGER_SERVICE)


@router.post("/manager/requests/{request_id}/reject")
async def reject_request(request: Request, request_id: str) -> Response:
    return await _forward(request, MANAGER_SERVICE)
