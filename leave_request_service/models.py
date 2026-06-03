"""Domain model for a leave request owned by the Leave Request Service.

This is the central transactional record. It is created with ``status`` =
PENDING and transitions to APPROVED, REJECTED, or CANCELLED. ``created_at`` and
``updated_at`` are UTC; ``updated_at`` is refreshed on every status change.
``rejection_reason`` is populated only when a request is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from shared.enums import LeaveStatus, LeaveType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class LeaveRequest:
    """A single leave request and its lifecycle state."""

    request_id: str
    employee_id: str
    leave_type: LeaveType
    start_date: date
    end_date: date
    number_of_days: int
    reason: str
    reporting_manager_id: str
    status: LeaveStatus = LeaveStatus.PENDING
    rejection_reason: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
