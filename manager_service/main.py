"""Manager Service entry point.

A thin orchestration layer over the Leave Request and Leave Balance services.
Every route is manager-only (enforced via the gateway-injected role) and
team-scoped (a manager may act only on requests routed to them). Approving a
request deducts the employee's balance before flipping the request to APPROVED;
rejecting one records a mandatory reason. The service holds no state of its own.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status

from manager_service import clients
from manager_service.schemas import ManagerRequestView, RejectLeaveRequest
from shared.auth_context import CallerIdentity, require_manager
from shared.enums import LeaveStatus, LeaveType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("manager_service")

_UPSTREAM_TIMEOUT_SECONDS = 5.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=_UPSTREAM_TIMEOUT_SECONDS)
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(title="Manager Service", lifespan=lifespan)


async def _call(coro) -> httpx.Response:
    """Await a downstream call, mapping transport failures to a 503."""

    try:
        return await coro
    except httpx.HTTPError as exc:
        logger.warning("Downstream call failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="A downstream service is unavailable",
        ) from exc


def _propagate(response: httpx.Response) -> dict | list:
    """Return the JSON body for 2xx; otherwise re-raise the downstream error."""

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


async def _load_team_request(
    client: httpx.AsyncClient, request_id: str, manager_id: str
) -> dict:
    """Fetch a request and assert it is routed to the acting manager."""

    response = await _call(clients.get_request(client, request_id))
    items = _propagate(response)
    if not items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found"
        )
    leave_request = items[0]
    if leave_request.get("reporting_manager_id") != manager_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This request is not routed to you",
        )
    return leave_request


@app.get("/manager/requests", response_model=list[ManagerRequestView])
async def list_requests(
    request: Request,
    caller: CallerIdentity = Depends(require_manager),
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="PENDING/APPROVED/REJECTED/CANCELLED.",
    ),
    employee_id: Optional[str] = Query(default=None),
    from_date: Optional[str] = Query(default=None),
    to_date: Optional[str] = Query(default=None),
) -> list[ManagerRequestView]:
    """List the acting manager's team requests, with optional filters."""

    response = await _call(
        clients.list_team_requests(
            request.app.state.http_client,
            caller.user_id,
            status=status_filter,
            employee_id=employee_id,
            from_date=from_date,
            to_date=to_date,
        )
    )
    items = _propagate(response)
    return [ManagerRequestView.from_payload(item) for item in items]


@app.post(
    "/manager/requests/{request_id}/approve", response_model=ManagerRequestView
)
async def approve_request(
    request_id: str,
    request: Request,
    caller: CallerIdentity = Depends(require_manager),
) -> ManagerRequestView:
    """Approve a pending team request: deduct balance, then mark APPROVED."""

    client = request.app.state.http_client
    leave_request = await _load_team_request(client, request_id, caller.user_id)

    if leave_request.get("status") != LeaveStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only a PENDING request can be approved "
                f"(current status: {leave_request.get('status')})"
            ),
        )

    # Deduct first so an insufficient balance aborts before any status change.
    deduct_response = await _call(
        clients.deduct_balance(
            client,
            leave_request["employee_id"],
            LeaveType(leave_request["leave_type"]),
            leave_request["number_of_days"],
        )
    )
    _propagate(deduct_response)

    update_response = await _call(
        clients.set_request_status(
            client, request_id, caller.user_id, LeaveStatus.APPROVED
        )
    )
    updated = _propagate(update_response)
    logger.info("Manager %s approved request %s", caller.user_id, request_id)
    return ManagerRequestView.from_payload(updated)


@app.post(
    "/manager/requests/{request_id}/reject", response_model=ManagerRequestView
)
async def reject_request(
    request_id: str,
    payload: RejectLeaveRequest,
    request: Request,
    caller: CallerIdentity = Depends(require_manager),
) -> ManagerRequestView:
    """Reject a pending team request, recording the mandatory reason."""

    client = request.app.state.http_client
    leave_request = await _load_team_request(client, request_id, caller.user_id)

    if leave_request.get("status") != LeaveStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only a PENDING request can be rejected "
                f"(current status: {leave_request.get('status')})"
            ),
        )

    update_response = await _call(
        clients.set_request_status(
            client,
            request_id,
            caller.user_id,
            LeaveStatus.REJECTED,
            rejection_reason=payload.rejection_reason,
        )
    )
    updated = _propagate(update_response)
    logger.info("Manager %s rejected request %s", caller.user_id, request_id)
    return ManagerRequestView.from_payload(updated)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe (public)."""

    return {"status": "ok", "service": "manager-service"}
