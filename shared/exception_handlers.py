"""Global exception handler that logs, publishes SYSTEM_ERROR, and returns 500."""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request

from shared.config import settings
from shared.enums import NotificationEventType
from shared.rabbitmq_publisher import publish_event

logger = logging.getLogger("shared.exception_handlers")


def register_global_exception_handler(app: FastAPI) -> None:
    """Attach a catch-all handler for unhandled exceptions."""

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        if isinstance(exc, HTTPException):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )

        logger.exception(
            "Unhandled error on %s %s", request.method, request.url.path
        )
        asyncio.create_task(
            publish_event(
                NotificationEventType.SYSTEM_ERROR,
                {
                    "message": str(exc),
                    "service": settings.service_name,
                    "path": request.url.path,
                },
            )
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
