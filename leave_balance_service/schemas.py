"""Request and response payload models for the Leave Balance Service API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from leave_balance_service.models import LeaveBalance
from shared.enums import LeaveType


class BalanceItem(BaseModel):
    """A single leave-type balance, with the derived ``remaining`` exposed."""

    leave_type: LeaveType
    total_allocated: int
    used: int
    remaining: int

    @classmethod
    def from_model(cls, balance: LeaveBalance) -> "BalanceItem":
        return cls(
            leave_type=balance.leave_type,
            total_allocated=balance.total_allocated,
            used=balance.used,
            remaining=balance.remaining,
        )


class EmployeeBalancesResponse(BaseModel):
    """All balance records for one employee."""

    employee_id: str
    balances: list[BalanceItem]


class DeductRequest(BaseModel):
    """Internal deduction command issued by the Manager Service on approval."""

    employee_id: str = Field(..., min_length=1)
    leave_type: LeaveType
    days: int = Field(..., gt=0, description="Whole days to deduct (must be > 0).")


class DeductResponse(BaseModel):
    """Result of a successful deduction: the balance after the change."""

    employee_id: str
    leave_type: LeaveType
    total_allocated: int
    used: int
    remaining: int
