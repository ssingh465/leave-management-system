"""Fire-and-forget RabbitMQ event publishing for leave lifecycle notifications.

Publishers connect to ``RABBITMQ_URL``, declare the durable ``notifications``
queue, and publish a JSON payload containing ``event_type`` plus the IDs and
metadata relevant to that event. Callers should treat publishing as best-effort
and must not block an HTTP response on broker availability.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import aio_pika

from shared.config import settings
from shared.enums import NotificationEventType

logger = logging.getLogger("shared.rabbitmq_publisher")

NOTIFICATIONS_QUEUE = "notifications"


async def publish_event(
    event_type: NotificationEventType, payload: dict[str, Any]
) -> None:
    """Publish a notification event to the ``notifications`` queue."""

    message_body = {"event_type": event_type.value, **payload}

    try:
        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    except Exception as exc:
        logger.warning("RabbitMQ connection failed for %s: %s", event_type.value, exc)
        return

    try:
        channel = await connection.channel()
        await channel.declare_queue(NOTIFICATIONS_QUEUE, durable=True)
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(message_body).encode("utf-8"),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
            ),
            routing_key=NOTIFICATIONS_QUEUE,
        )
        logger.debug("Published %s event to RabbitMQ", event_type.value)
    except Exception as exc:
        logger.warning("RabbitMQ publish failed for %s: %s", event_type.value, exc)
    finally:
        await connection.close()
