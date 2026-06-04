"""Request and response payload models for the Manager Service API.

The Manager Service owns no data of its own; it composes the Leave Request and
Leave Balance services. These models shape its inbound rejection command and
the outbound team-request view (enriched with the employee's display name from
the shared org chart).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from shared.enums import LeaveStatus, LeaveType
from shared.seed_config import get_user


class RejectLeaveRequest(BaseModel):
    """Body for rejecting a request - the reason is mandatory."""

    rejection_reason: str = Field(..., min_length=1, max_length=500)


class ManagerRequestView(BaseModel):
    """A team member's leave request as presented to their manager."""

    request_id: str
    employee_id: str
    employee_name: Optional[str] = None
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
    def from_payload(cls, data: dict) -> "ManagerRequestView":
        user = get_user(data.get("employee_id", ""))
        return cls(employee_name=user.username if user else None, **data)
