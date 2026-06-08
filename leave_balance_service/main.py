"""Leave Balance Service entry point.

Owns every employee's per-leave-type balance. Exposes two gateway-facing reads
(an employee's own balances and, with team-scoped authorization, a specific
employee's balances) plus one internal deduction endpoint used by the Manager
Service when it approves a request. Balances are seeded at startup; ``remaining``
is always derived from ``total_allocated - used`` so it can never drift.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status

from leave_balance_service.schemas import (
    BalanceItem,
    DeductRequest,
    DeductResponse,
    EmployeeBalancesResponse,
)
from leave_balance_service.seed import seed_balances
from leave_balance_service.store import apply_deduction, get_balances_for_employee
from shared.auth_context import CallerIdentity, get_caller
from shared.config import settings
from shared.consul_client import deregister_service, register_service
from shared.enums import Role
from shared.exception_handlers import register_global_exception_handler
from shared.logging_config import configure_logging
from shared.seed_config import is_team_member
from shared.tracing import init_tracing, instrument_fastapi

configure_logging(settings.service_name)
logger = logging.getLogger("leave_balance_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_tracing(settings.service_name)
    register_service(
        settings.service_name, settings.service_host, settings.service_port
    )
    seed_balances()
    try:
        yield
    finally:
        deregister_service(
            settings.service_name, settings.service_host, settings.service_port
        )


app = FastAPI(title="Leave Balance Service", lifespan=lifespan)
register_global_exception_handler(app)
instrument_fastapi(app)


def _balances_response(employee_id: str) -> EmployeeBalancesResponse:
    balances = get_balances_for_employee(employee_id)
    return EmployeeBalancesResponse(
        employee_id=employee_id,
        balances=[BalanceItem.from_model(balance) for balance in balances],
    )


@app.get("/employees/me/balances", response_model=EmployeeBalancesResponse)
async def my_balances(
    caller: CallerIdentity = Depends(get_caller),
) -> EmployeeBalancesResponse:
    """Return the authenticated caller's own balances."""

    return _balances_response(caller.user_id)


@app.get(
    "/employees/{employee_id}/balances", response_model=EmployeeBalancesResponse
)
async def employee_balances(
    employee_id: str,
    caller: CallerIdentity = Depends(get_caller),
) -> EmployeeBalancesResponse:
    """Return a specific employee's balances, subject to authorization.

    Employees may read only their own balances; managers may additionally read
    the balances of their direct reports. Any other combination is a 403.
    """

    if caller.user_id != employee_id:
        is_manager_of = (
            caller.role == Role.MANAGER
            and is_team_member(caller.user_id, employee_id)
        )
        if not is_manager_of:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this employee's balances",
            )
    return _balances_response(employee_id)


@app.post("/internal/balances/deduct", response_model=DeductResponse)
async def deduct_balance(payload: DeductRequest) -> DeductResponse:
    """Deduct days from a balance (internal; called on manager approval).

    Returns 404 if the employee has no record for that leave type and 409 if
    the deduction would overdraw the remaining balance.
    """

    try:
        balance = apply_deduction(
            payload.employee_id, payload.leave_type, payload.days
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    logger.info(
        "Deducted %d day(s) of %s from employee %s (remaining=%d)",
        payload.days,
        payload.leave_type.value,
        payload.employee_id,
        balance.remaining,
    )
    return DeductResponse(
        employee_id=balance.employee_id,
        leave_type=balance.leave_type,
        total_allocated=balance.total_allocated,
        used=balance.used,
        remaining=balance.remaining,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe (public)."""

    return {"status": "healthy", "service": "leave-balance-service"}
