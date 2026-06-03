"""Domain model for a leave-balance record owned by the Leave Balance Service.

Each employee has exactly three records (one per :class:`~shared.enums.LeaveType`).
``remaining`` is never stored: it is derived at read time from
``total_allocated - used`` so the two persisted integers can never drift out
of sync with a cached total.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.enums import LeaveType


@dataclass
class LeaveBalance:
    """A single employee/leave-type balance row."""

    balance_id: str
    employee_id: str
    leave_type: LeaveType
    total_allocated: int
    used: int = 0

    @property
    def remaining(self) -> int:
        """Days still available: ``total_allocated - used``."""

        return self.total_allocated - self.used
