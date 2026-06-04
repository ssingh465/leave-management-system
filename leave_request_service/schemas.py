"""Request and response payload models for the Leave Request Service API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from leave_request_service.models import LeaveRequest
from shared.enums import LeaveStatus, LeaveType


class ApplyLeaveRequest(BaseModel):
    """Body for ``POST /leaves`` (the employee is taken from the auth context).

    ``reporting_manager_id`` is optional: when omitted it is resolved from the
    org chart; when supplied it must match, so a client cannot reroute a
    request to an arbitrary approver.
    """

    leave_type: LeaveType
    start_date: date
    end_date: date
    number_of_days: int = Field(..., gt=0, description="Inclusive working span.")
    reason: str = Field(..., min_length=1, max_length=500)
    reporting_manager_id: Optional[str] = Field(default=None, min_length=1)


class LeaveRequestResponse(BaseModel):
    """Canonical representation of a leave request returned to callers."""

    request_id: str
    employee_id: str
    leave_type: LeaveType
    start_date: date
    end_date: date
    number_of_days: int
    reason: str
    reporting_manager_id: str
    status: LeaveStatus
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, request: LeaveRequest) -> "LeaveRequestResponse":
        return cls(
            request_id=request.request_id,
            employee_id=request.employee_id,
            leave_type=request.leave_type,
            start_date=request.start_date,
            end_date=request.end_date,
            number_of_days=request.number_of_days,
            reason=request.reason,
            reporting_manager_id=request.reporting_manager_id,
            status=request.status,
            rejection_reason=request.rejection_reason,
            created_at=request.created_at,
            updated_at=request.updated_at,
        )


class LeaveHistoryResponse(BaseModel):
    """A page of an employee's leave history."""

    items: list[LeaveRequestResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class StatusUpdateRequest(BaseModel):
    """Internal command to approve or reject a request (Manager Service only).

    ``manager_id`` is the acting manager; the service verifies the request is
    actually routed to them before allowing the transition.
    """

    new_status: LeaveStatus
    manager_id: str = Field(..., min_length=1)
    rejection_reason: Optional[str] = Field(default=None, max_length=500)
