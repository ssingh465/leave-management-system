"""Outbound calls from the Leave Request Service to the Leave Balance Service.

Applying for leave requires knowing the employee's remaining balance, which is
owned by another service. This module performs that read over HTTP, resolving
the balance service's address via the shared service registry. It impersonates
the applying employee through the same ``X-User-*`` headers the gateway would
inject, so the balance service's own authorization treats it as a self-read.

The call is intentionally isolated in one function so it can later be wrapped
in a circuit breaker, and so tests can stub it without a live balance service.
"""

from __future__ import annotations

import httpx

from shared.enums import LeaveType, Role
from shared.service_client import BALANCE_SERVICE, resolve


async def fetch_remaining(
    client: httpx.AsyncClient, employee_id: str, leave_type: LeaveType
) -> int:
    """Return the employee's remaining days for ``leave_type``.

    Raises ``httpx`` errors if the balance service is unreachable or returns a
    non-2xx status; the caller maps those to a 503.
    """

    base_url = resolve(BALANCE_SERVICE)
    response = await client.get(
        f"{base_url}/employees/{employee_id}/balances",
        headers={
            "X-User-Id": employee_id,
            "X-User-Role": Role.EMPLOYEE.value,
        },
    )
    response.raise_for_status()
    payload = response.json()

    for item in payload.get("balances", []):
        if item.get("leave_type") == leave_type.value:
            return int(item.get("remaining", 0))
    return 0
