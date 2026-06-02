"""Shared enumerations used across all leave-management microservices.

These enums are the canonical, cross-service value sets for user roles,
leave types, leave-request lifecycle states, and notification events.
They inherit from `str` so they serialise cleanly to JSON via Pydantic
or `dataclasses.asdict` and compare equal to their string value, which
is convenient for store indexes and RabbitMQ payloads.
"""

from enum import Enum


class Role(str, Enum):
    """User role. Stored on `users.role` and embedded in the JWT payload."""

    EMPLOYEE = "EMPLOYEE"
    MANAGER = "MANAGER"


class LeaveType(str, Enum):
    """Leave type. Used on both `leave_balances` and `leave_requests`."""

    CASUAL = "CASUAL"
    SICK = "SICK"
    PRIVILEGE = "PRIVILEGE"


class LeaveStatus(str, Enum):
    """Lifecycle state of a leave request."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class NotificationEventType(str, Enum):
    """Event types published to RabbitMQ and consumed by the Notification Service."""

    LEAVE_APPLIED = "LEAVE_APPLIED"
    LEAVE_APPROVED = "LEAVE_APPROVED"
    LEAVE_REJECTED = "LEAVE_REJECTED"
    SYSTEM_ERROR = "SYSTEM_ERROR"


DEFAULT_LEAVE_ALLOCATIONS: dict[LeaveType, int] = {
    LeaveType.CASUAL: 12,
    LeaveType.SICK: 10,
    LeaveType.PRIVILEGE: 15,
}
