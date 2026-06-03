"""In-memory store for the Leave Request Service.

Holds every :class:`~leave_request_service.models.LeaveRequest` keyed by
``request_id`` plus two secondary indexes:

* ``employee_requests_index`` - ``employee_id -> [request_id, ...]`` backs
  ``GET /leaves/history`` (an employee's own requests).
* ``manager_requests_index`` - ``reporting_manager_id -> [request_id, ...]``
  backs ``GET /manager/requests`` (a manager's team requests).

Each index preserves insertion order so history and team views are naturally
chronological.
"""

from __future__ import annotations

from typing import Optional

from leave_request_service.models import LeaveRequest

requests_store: dict[str, LeaveRequest] = {}
employee_requests_index: dict[str, list[str]] = {}
manager_requests_index: dict[str, list[str]] = {}


def add_request(request: LeaveRequest) -> None:
    """Insert a request and maintain the employee and manager indexes."""

    requests_store[request.request_id] = request
    employee_requests_index.setdefault(request.employee_id, []).append(
        request.request_id
    )
    manager_requests_index.setdefault(request.reporting_manager_id, []).append(
        request.request_id
    )


def get_request(request_id: str) -> Optional[LeaveRequest]:
    """Resolve a single request by id, or ``None`` if it does not exist."""

    return requests_store.get(request_id)


def get_requests_for_employee(employee_id: str) -> list[LeaveRequest]:
    """Return all requests submitted by one employee, in submission order."""

    return [
        requests_store[request_id]
        for request_id in employee_requests_index.get(employee_id, [])
    ]


def get_requests_for_manager(manager_id: str) -> list[LeaveRequest]:
    """Return all requests routed to one manager, in submission order."""

    return [
        requests_store[request_id]
        for request_id in manager_requests_index.get(manager_id, [])
    ]
