"""Named pybreaker instances and an async helper for inter-service HTTP calls."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

import pybreaker

# Shared breaker for every call to the Leave Balance Service.
leave_balance_cb = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=30,
    name="leave_balance_service",
)

# Breaker for Manager Service calls to the Leave Request Service.
leave_request_cb = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=30,
    name="leave_request_service",
)

T = TypeVar("T")


async def invoke_with_breaker(
    breaker: pybreaker.CircuitBreaker,
    coro_factory: Callable[[], Awaitable[T]],
) -> T:
    """Await ``coro_factory()`` through ``breaker``.

    Raises ``pybreaker.CircuitBreakerError`` when the circuit is open and
    re-raises any exception raised by the coroutine after recording a failure.
    """

    if breaker.current_state == "open":
        raise pybreaker.CircuitBreakerError("Circuit breaker is open")

    try:
        result = await coro_factory()
    except Exception as exc:

        def _record_failure() -> None:
            raise exc

        try:
            breaker.call(_record_failure)
        except pybreaker.CircuitBreakerError:
            # Threshold reached on this failure; surface the original error now.
            raise exc
        except Exception:
            raise exc
        raise exc

    breaker.call(lambda: True)
    return result
