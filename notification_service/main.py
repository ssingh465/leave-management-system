"""Notification Service entry point.

Runs a FastAPI app for health checks and Consul registration while a background
RabbitMQ consumer writes structured notification log entries for every leave
lifecycle event published by the other services.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from notification_service.consumer import run_consumer
from shared.config import settings
from shared.consul_client import deregister_service, register_service
from shared.exception_handlers import register_global_exception_handler
from shared.logging_config import configure_logging
from shared.tracing import init_tracing, instrument_fastapi

configure_logging(settings.service_name)
logger = logging.getLogger("notification_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_tracing(settings.service_name)
    register_service(
        settings.service_name, settings.service_host, settings.service_port
    )
    consumer_task = asyncio.create_task(run_consumer())
    try:
        yield
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
        deregister_service(
            settings.service_name, settings.service_host, settings.service_port
        )


app = FastAPI(title="Notification Service", lifespan=lifespan)
register_global_exception_handler(app)
instrument_fastapi(app)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe (public)."""

    return {"status": "healthy", "service": "notification-service"}
