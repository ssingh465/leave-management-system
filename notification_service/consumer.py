"""RabbitMQ consumer that turns notification events into structured log entries."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import aio_pika

from notification_service.models import NotificationLog
from notification_service.store import add_log
from shared.config import settings
from shared.enums import NotificationEventType
from shared.rabbitmq_publisher import NOTIFICATIONS_QUEUE

logger = logging.getLogger("notification_service.consumer")

_CONNECT_RETRY_SECONDS = 3.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _format_timestamp(value: datetime | None = None) -> str:
    stamp = value or _utcnow()
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_message(event_type: NotificationEventType, payload: dict[str, Any]) -> str:
    """Return the human-readable log line for ``event_type``."""

    timestamp = _format_timestamp()
    if event_type == NotificationEventType.LEAVE_APPLIED:
        return (
            f"[{timestamp}] LEAVE_APPLIED: Employee {payload.get('employee_id')} "
            f"submitted leave request {payload.get('leave_request_id')}. "
            f"Manager {payload.get('manager_id')} notified."
        )
    if event_type == NotificationEventType.LEAVE_APPROVED:
        return (
            f"[{timestamp}] LEAVE_APPROVED: Leave request "
            f"{payload.get('leave_request_id')} approved. "
            f"Employee {payload.get('employee_id')} notified."
        )
    if event_type == NotificationEventType.LEAVE_REJECTED:
        return (
            f"[{timestamp}] LEAVE_REJECTED: Leave request "
            f"{payload.get('leave_request_id')} rejected. "
            f"Reason: {payload.get('reason')}. "
            f"Employee {payload.get('employee_id')} notified."
        )
    if event_type == NotificationEventType.SYSTEM_ERROR:
        return f"[{timestamp}] SYSTEM_ERROR: {payload.get('message')}"

    return f"[{timestamp}] {event_type.value}: {payload}"


def _process_payload(payload: dict[str, Any]) -> NotificationLog:
    raw_event_type = payload.get("event_type")
    event_type = NotificationEventType(str(raw_event_type))
    message = build_message(event_type, payload)
    timestamp = _utcnow()

    log_entry = NotificationLog(
        log_id=str(uuid.uuid4()),
        event_type=event_type,
        employee_id=payload.get("employee_id"),
        manager_id=payload.get("manager_id"),
        leave_request_id=payload.get("leave_request_id"),
        reason=payload.get("reason"),
        message=message,
        timestamp=timestamp,
    )
    add_log(log_entry)
    logger.info(message)
    return log_entry


async def run_consumer() -> None:
    """Connect to RabbitMQ and consume messages until cancelled."""

    while True:
        try:
            connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        except Exception as exc:
            logger.warning(
                "RabbitMQ unavailable, retrying in %.0fs: %s",
                _CONNECT_RETRY_SECONDS,
                exc,
            )
            await asyncio.sleep(_CONNECT_RETRY_SECONDS)
            continue

        try:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=10)
            queue = await channel.declare_queue(NOTIFICATIONS_QUEUE, durable=True)

            logger.info(
                "Notification consumer subscribed to '%s'", NOTIFICATIONS_QUEUE
            )
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        try:
                            payload = json.loads(message.body.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                            logger.warning(
                                "Skipping invalid RabbitMQ payload: %s", exc
                            )
                            continue
                        try:
                            _process_payload(payload)
                        except (KeyError, ValueError) as exc:
                            logger.warning(
                                "Skipping unsupported event payload: %s", exc
                            )
        except asyncio.CancelledError:
            await connection.close()
            raise
        except Exception as exc:
            logger.warning(
                "Notification consumer stopped (%s); reconnecting in %.0fs",
                exc,
                _CONNECT_RETRY_SECONDS,
            )
            await connection.close()
            await asyncio.sleep(_CONNECT_RETRY_SECONDS)
