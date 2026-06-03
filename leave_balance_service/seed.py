"""Seed loader for the Leave Balance Service.

At startup every seeded employee (from :mod:`shared.seed_config`) is given
exactly three balance records - CASUAL, SICK, and PRIVILEGE - using the
canonical allocations defined in :data:`shared.enums.DEFAULT_LEAVE_ALLOCATIONS`
(12 / 10 / 15). Managers get no balance records. ``used`` starts at 0.
"""

from __future__ import annotations

import uuid

from leave_balance_service.models import LeaveBalance
from leave_balance_service.store import add_balance, balances_store
from shared.enums import DEFAULT_LEAVE_ALLOCATIONS
from shared.seed_config import get_seed_employees


def init_balances_for_employee(employee_id: str) -> list[LeaveBalance]:
    """Build the three initial balance records for one employee.

    Returns the created records (CASUAL/SICK/PRIVILEGE) with fresh
    ``balance_id`` UUIDs and ``used`` set to 0.
    """

    return [
        LeaveBalance(
            balance_id=str(uuid.uuid4()),
            employee_id=employee_id,
            leave_type=leave_type,
            total_allocated=allocation,
            used=0,
        )
        for leave_type, allocation in DEFAULT_LEAVE_ALLOCATIONS.items()
    ]


def seed_balances() -> None:
    """Initialise balance records for every seeded employee (idempotent)."""

    if balances_store:
        return

    for employee in get_seed_employees():
        for balance in init_balances_for_employee(employee.user_id):
            add_balance(balance)
