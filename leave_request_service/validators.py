"""Business-rule validations for applying for leave.

Implements the four checks required before a request is accepted, each mapped
to a deliberate HTTP status so clients can distinguish the failure mode:

* **date range** - ``start_date`` must not be after ``end_date``     -> 400
* **past dates** - ``start_date`` must not be before today (UTC)     -> 400
* **day count**  - ``number_of_days`` must equal the inclusive span  -> 400
* **overlap**    - no other active request may cover the same days   -> 409

(The balance check is the fifth gate and lives in the endpoint because it
requires an inter-service call; it returns 409 when balance is insufficient.)
Pydantic handles structural validation (missing fields, bad types, non-positive
day counts) and returns 422 before any of these run.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import HTTPException, status

from leave_request_service.store import get_requests_for_employee
from shared.enums import LeaveStatus

# Requests in these states occupy calendar days and therefore block overlaps.
_ACTIVE_STATUSES = frozenset({LeaveStatus.PENDING, LeaveStatus.APPROVED})


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def validate_dates(start_date: date, end_date: date, number_of_days: int) -> None:
    """Validate the date range, past-date rule, and declared day count (400)."""

    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must not be after end_date",
        )
    if start_date < _today_utc():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must not be in the past",
        )
    inclusive_days = (end_date - start_date).days + 1
    if number_of_days != inclusive_days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"number_of_days ({number_of_days}) does not match the "
                f"inclusive date range ({inclusive_days} day(s))"
            ),
        )


def check_overlap(employee_id: str, start_date: date, end_date: date) -> None:
    """Reject a request that overlaps an existing PENDING/APPROVED one (409)."""

    for existing in get_requests_for_employee(employee_id):
        if existing.status not in _ACTIVE_STATUSES:
            continue
        # Two inclusive ranges overlap iff each starts on or before the other ends.
        if existing.start_date <= end_date and start_date <= existing.end_date:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"A {existing.status.value} leave request already exists "
                    f"for dates {existing.start_date} to {existing.end_date}"
                ),
            )
