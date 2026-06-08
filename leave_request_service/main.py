"""Leave Request Service entry point.

Owns the leave-request lifecycle. Gateway-facing routes let an employee apply
for leave (with the four business validations), page through their own history,
and cancel a pending request. Two internal routes - a filtered list and a
status transition - are consumed only by the Manager Service over the Docker
network to power team views and approve/reject.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

import httpx
import pybreaker
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status

from leave_request_service import balance_client
from leave_request_service.models import LeaveRequest
from leave_request_service.schemas import (
    ApplyLeaveRequest,
    LeaveHistoryResponse,
    LeaveRequestResponse,
    StatusUpdateRequest,
)
from leave_request_service.store import (
    add_request,
    get_request,
    get_requests_for_employee,
    get_requests_for_manager,
    requests_store,
    set_status,
)
from leave_request_service.validators import check_overlap, validate_dates
from shared.auth_context import CallerIdentity, get_caller
from shared.circuit_breakers import invoke_with_breaker, leave_balance_cb
from shared.config import settings
from shared.consul_client import deregister_service, register_service
from shared.enums import LeaveStatus, NotificationEventType
from shared.exception_handlers import register_global_exception_handler
from shared.logging_config import configure_logging
from shared.rabbitmq_publisher import publish_event
from shared.seed_config import get_manager_id
from shared.tracing import init_tracing, instrument_fastapi, instrument_httpx

configure_logging(settings.service_name)
logger = logging.getLogger("leave_request_service")

_UPSTREAM_TIMEOUT_SECONDS = 5.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_tracing(settings.service_name)
    instrument_httpx()
    register_service(
        settings.service_name, settings.service_host, settings.service_port
    )
    app.state.http_client = httpx.AsyncClient(timeout=_UPSTREAM_TIMEOUT_SECONDS)
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        deregister_service(
            settings.service_name, settings.service_host, settings.service_port
        )


app = FastAPI(title="Leave Request Service", lifespan=lifespan)
register_global_exception_handler(app)
instrument_fastapi(app)


def _resolve_manager(employee_id: str, provided: Optional[str]) -> str:
    """Resolve the approving manager from the org chart, validating any override."""

    resolved = get_manager_id(employee_id)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No reporting manager is configured for this user",
        )
    if provided is not None and provided != resolved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reporting_manager_id does not match the employee's manager",
        )
    return resolved


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------
@app.post(
    "/leaves",
    response_model=LeaveRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def apply_leave(
    payload: ApplyLeaveRequest,
    request: Request,
    caller: CallerIdentity = Depends(get_caller),
) -> LeaveRequestResponse:
    """Apply for leave after running all four validations + the balance check."""

    validate_dates(payload.start_date, payload.end_date, payload.number_of_days)
    manager_id = _resolve_manager(caller.user_id, payload.reporting_manager_id)
    check_overlap(caller.user_id, payload.start_date, payload.end_date)

    try:
        remaining = await invoke_with_breaker(
            leave_balance_cb,
            lambda: balance_client.fetch_remaining(
                request.app.state.http_client, caller.user_id, payload.leave_type
            ),
        )
    except pybreaker.CircuitBreakerError as exc:
        logger.warning("Balance lookup circuit open for %s", caller.user_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Leave Balance Service is unavailable",
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("Balance lookup failed for %s: %s", caller.user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Leave Balance Service is unavailable",
        ) from exc

    if payload.number_of_days > remaining:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Insufficient {payload.leave_type.value} balance: requested "
                f"{payload.number_of_days}, remaining {remaining}"
            ),
        )

    leave_request = LeaveRequest(
        request_id=str(uuid.uuid4()),
        employee_id=caller.user_id,
        leave_type=payload.leave_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        number_of_days=payload.number_of_days,
        reason=payload.reason,
        reporting_manager_id=manager_id,
    )
    add_request(leave_request)
    asyncio.create_task(
        publish_event(
            NotificationEventType.LEAVE_APPLIED,
            {
                "employee_id": caller.user_id,
                "manager_id": manager_id,
                "leave_request_id": leave_request.request_id,
            },
        )
    )
    logger.info(
        "Leave request %s created for employee %s (%s, %d day(s))",
        leave_request.request_id,
        caller.user_id,
        payload.leave_type.value,
        payload.number_of_days,
    )
    return LeaveRequestResponse.from_model(leave_request)


@app.get("/leaves/history", response_model=LeaveHistoryResponse)
async def leave_history(
    caller: CallerIdentity = Depends(get_caller),
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="ALL (default) or one of PENDING/APPROVED/REJECTED/CANCELLED.",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> LeaveHistoryResponse:
    """Return the caller's own leave history, filtered by status and paginated."""

    requests = get_requests_for_employee(caller.user_id)

    if status_filter and status_filter.upper() != "ALL":
        try:
            wanted = LeaveStatus(status_filter.upper())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter '{status_filter}'",
            ) from exc
        requests = [r for r in requests if r.status == wanted]

    total = len(requests)
    total_pages = (total + page_size - 1) // page_size if total else 0
    start = (page - 1) * page_size
    page_items = requests[start : start + page_size]

    return LeaveHistoryResponse(
        items=[LeaveRequestResponse.from_model(r) for r in page_items],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )


@app.patch("/leaves/{leave_id}/cancel", response_model=LeaveRequestResponse)
async def cancel_leave(
    leave_id: str,
    caller: CallerIdentity = Depends(get_caller),
) -> LeaveRequestResponse:
    """Cancel the caller's own request; only a PENDING request may be cancelled."""

    leave_request = get_request(leave_id)
    if leave_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found"
        )
    if leave_request.employee_id != caller.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to cancel this leave request",
        )
    if leave_request.status != LeaveStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Only a PENDING request can be cancelled "
                f"(current status: {leave_request.status.value})"
            ),
        )

    set_status(leave_request, LeaveStatus.CANCELLED)
    logger.info("Leave request %s cancelled by %s", leave_id, caller.user_id)
    return LeaveRequestResponse.from_model(leave_request)


# ---------------------------------------------------------------------------
# Internal routes (Docker network only; not exposed via the gateway)
# ---------------------------------------------------------------------------
@app.get("/internal/requests", response_model=list[LeaveRequestResponse])
async def list_requests(
    manager_id: Optional[str] = Query(default=None),
    employee_id: Optional[str] = Query(default=None),
    request_id: Optional[str] = Query(default=None),
    status_filter: Optional[LeaveStatus] = Query(default=None, alias="status"),
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
) -> list[LeaveRequestResponse]:
    """List requests by the given filters (used for team views and lookups)."""

    if request_id is not None:
        found = get_request(request_id)
        requests = [found] if found else []
    elif manager_id is not None:
        requests = get_requests_for_manager(manager_id)
    elif employee_id is not None:
        requests = get_requests_for_employee(employee_id)
    else:
        requests = list(requests_store.values())

    if employee_id is not None:
        requests = [r for r in requests if r.employee_id == employee_id]
    if status_filter is not None:
        requests = [r for r in requests if r.status == status_filter]
    if from_date is not None:
        requests = [r for r in requests if r.end_date >= from_date]
    if to_date is not None:
        requests = [r for r in requests if r.start_date <= to_date]

    return [LeaveRequestResponse.from_model(r) for r in requests]


@app.post(
    "/internal/requests/{request_id}/status",
    response_model=LeaveRequestResponse,
)
async def update_request_status(
    request_id: str, payload: StatusUpdateRequest
) -> LeaveRequestResponse:
    """Approve or reject a request on behalf of its routed manager.

    Enforces ownership (the request must be routed to ``manager_id``), the
    PENDING precondition, the allowed target states, and the mandatory
    rejection reason.
    """

    leave_request = get_request(request_id)
    if leave_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found"
        )
    if leave_request.reporting_manager_id != payload.manager_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This request is not routed to the acting manager",
        )
    if leave_request.status != LeaveStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Only a PENDING request can be updated "
                f"(current status: {leave_request.status.value})"
            ),
        )
    if payload.new_status not in (LeaveStatus.APPROVED, LeaveStatus.REJECTED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="new_status must be APPROVED or REJECTED",
        )
    if payload.new_status == LeaveStatus.REJECTED and not (
        payload.rejection_reason and payload.rejection_reason.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A rejection reason is required when rejecting a request",
        )

    set_status(leave_request, payload.new_status, payload.rejection_reason)
    logger.info(
        "Leave request %s set to %s by manager %s",
        request_id,
        payload.new_status.value,
        payload.manager_id,
    )
    return LeaveRequestResponse.from_model(leave_request)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe (public)."""

    return {"status": "healthy", "service": "leave-request-service"}
