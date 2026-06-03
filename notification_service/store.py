"""Append-only in-memory store for the Notification Service.

Records are only ever inserted - never updated or deleted - so the list is a
complete, immutable audit trail of every notification event consumed from
RabbitMQ. Lightweight lookup helpers support filtering by event type, target
employee, and related leave request (mirroring the schema indexes).
"""

from __future__ import annotations

from notification_service.models import NotificationLog
from shared.enums import NotificationEventType

notification_logs_store: list[NotificationLog] = []


def add_log(log: NotificationLog) -> None:
    """Append a notification log entry (append-only; never mutated)."""

    notification_logs_store.append(log)


def get_logs_by_event_type(
    event_type: NotificationEventType,
) -> list[NotificationLog]:
    """Return all log entries for a given event type."""

    return [log for log in notification_logs_store if log.event_type == event_type]


def get_logs_for_employee(employee_id: str) -> list[NotificationLog]:
    """Return all log entries targeting a specific employee."""

    return [log for log in notification_logs_store if log.employee_id == employee_id]


def get_logs_for_request(leave_request_id: str) -> list[NotificationLog]:
    """Return all log entries associated with a specific leave request."""

    return [
        log
        for log in notification_logs_store
        if log.leave_request_id == leave_request_id
    ]
