"""Outbound calls from the Manager Service to the services it orchestrates.

Approving or rejecting a request, and listing a team's requests, all require
data the Manager Service does not own: leave requests live in the Leave Request
Service and balances in the Leave Balance Service. This module centralises
those HTTP calls (resolving addresses via the shared registry) and returns the
raw ``httpx.Response`` so the endpoint layer can faithfully propagate
downstream status codes. Isolating them here also keeps any later
circuit-breaker wrapping and the test stubs single-point changes.
"""

from __future__ import annotations

from typing import Optional

import httpx

from shared.enums import LeaveStatus, LeaveType
from shared.service_client import BALANCE_SERVICE, REQUEST_SERVICE, resolve


async def list_team_requests(
    client: httpx.AsyncClient,
    manager_id: str,
    *,
    status: Optional[str] = None,
    employee_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> httpx.Response:
    """List the manager's team requests with optional filters."""

    params: dict[str, str] = {"manager_id": manager_id}
    if status:
        params["status"] = status
    if employee_id:
        params["employee_id"] = employee_id
    if from_date:
        params["from_date"] = from_date
    if to_date:
        params["to_date"] = to_date

    base_url = resolve(REQUEST_SERVICE)
    return await client.get(f"{base_url}/internal/requests", params=params)


async def get_request(
    client: httpx.AsyncClient, request_id: str
) -> httpx.Response:
    """Fetch a single request by id (returns a list of zero or one)."""

    base_url = resolve(REQUEST_SERVICE)
    return await client.get(
        f"{base_url}/internal/requests", params={"request_id": request_id}
    )


async def set_request_status(
    client: httpx.AsyncClient,
    request_id: str,
    manager_id: str,
    new_status: LeaveStatus,
    rejection_reason: Optional[str] = None,
) -> httpx.Response:
    """Transition a request to APPROVED/REJECTED on the Request Service."""

    base_url = resolve(REQUEST_SERVICE)
    body: dict[str, str] = {
        "new_status": new_status.value,
        "manager_id": manager_id,
    }
    if rejection_reason is not None:
        body["rejection_reason"] = rejection_reason
    return await client.post(
        f"{base_url}/internal/requests/{request_id}/status", json=body
    )


async def deduct_balance(
    client: httpx.AsyncClient,
    employee_id: str,
    leave_type: LeaveType,
    days: int,
) -> httpx.Response:
    """Deduct days from an employee's balance on the Balance Service."""

    base_url = resolve(BALANCE_SERVICE)
    return await client.post(
        f"{base_url}/internal/balances/deduct",
        json={
            "employee_id": employee_id,
            "leave_type": leave_type.value,
            "days": days,
        },
    )
