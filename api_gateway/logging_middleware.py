"""Access-logging middleware for the API Gateway.

Emits one structured log line per request with the method, path, resulting
status code, and wall-clock duration. It sits as the outermost middleware so
it records every response the gateway produces - including ``401``s rejected
by the auth middleware and errors raised inside route handlers.
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("api_gateway.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Log method, path, status, and latency for every request."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "%s %s -> 500 (%.1fms)",
                request.method,
                request.url.path,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s -> %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
