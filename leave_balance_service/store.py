"""In-memory store for the Leave Balance Service.

Holds every :class:`~leave_balance_service.models.LeaveBalance` keyed by
``balance_id`` plus a composite ``(employee_id, leave_type) -> balance_id``
index that backs both the per-employee balance read and the approval-time
deduction lookup. The composite index also enforces the
one-record-per-employee-per-leave-type uniqueness rule from the schema.
"""

from __future__ import annotations

from typing import Optional

from leave_balance_service.models import LeaveBalance
from shared.enums import LeaveType

balances_store: dict[str, LeaveBalance] = {}
employee_leavetype_index: dict[tuple[str, LeaveType], str] = {}


def add_balance(balance: LeaveBalance) -> None:
    """Insert a balance record, enforcing per-employee/per-type uniqueness."""

    key = (balance.employee_id, balance.leave_type)
    if key in employee_leavetype_index:
        raise ValueError(
            f"Balance for employee {balance.employee_id} and leave type "
            f"{balance.leave_type.value} already exists"
        )
    balances_store[balance.balance_id] = balance
    employee_leavetype_index[key] = balance.balance_id


def get_balance(employee_id: str, leave_type: LeaveType) -> Optional[LeaveBalance]:
    """Resolve a single balance by employee and leave type."""

    balance_id = employee_leavetype_index.get((employee_id, leave_type))
    if balance_id is None:
        return None
    return balances_store.get(balance_id)


def get_balances_for_employee(employee_id: str) -> list[LeaveBalance]:
    """Return all balance records belonging to one employee."""

    return [
        balance
        for balance in balances_store.values()
        if balance.employee_id == employee_id
    ]
