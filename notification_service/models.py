"""Domain model for a notification log entry owned by the Notification Service.

Each record captures one event consumed from RabbitMQ. The Notification
Service is intentionally decoupled: ``employee_id``, ``manager_id``, and
``leave_request_id`` are plain data carried in the event payload, not enforced
foreign keys. Which fields are populated depends on ``event_type`` (see the
schema's event-to-log mapping).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from shared.enums import NotificationEventType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class NotificationLog:
    """A single immutable notification audit entry."""

    log_id: str
    event_type: NotificationEventType
    employee_id: Optional[str] = None
    manager_id: Optional[str] = None
    leave_request_id: Optional[str] = None
    reason: Optional[str] = None
    message: str = ""
    timestamp: datetime = field(default_factory=_utcnow)
