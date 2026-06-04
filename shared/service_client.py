"""Resolution of logical service names to base URLs for inter-service calls.

Some services must call one another directly (not via the gateway): the Leave
Request Service checks balances, and the Manager Service deducts balances and
reads/updates requests. Those callers ask this module for a downstream base
URL by logical name.

Resolution prefers a healthy instance reported by Consul (once service
registration is in place) and falls back to a static map of Docker Compose
hostnames, so inter-service calls work on the compose network even before
service discovery exists. Any circuit-breaker wrapping of these calls is
layered on separately; this module deliberately stays transport-agnostic and
only answers "where is service X?".
"""

from __future__ import annotations

import logging

import httpx

from shared.config import settings

logger = logging.getLogger("shared.service_client")

# Logical service names (kept here so every caller refers to the same string).
AUTH_SERVICE = "auth-service"
BALANCE_SERVICE = "leave-balance-service"
REQUEST_SERVICE = "leave-request-service"
MANAGER_SERVICE = "manager-service"
NOTIFICATION_SERVICE = "notification-service"

# Logical service name -> default (host, port) on the Docker Compose network.
STATIC_SERVICE_MAP: dict[str, tuple[str, int]] = {
    AUTH_SERVICE: (AUTH_SERVICE, 8001),
    BALANCE_SERVICE: (BALANCE_SERVICE, 8002),
    REQUEST_SERVICE: (REQUEST_SERVICE, 8003),
    MANAGER_SERVICE: (MANAGER_SERVICE, 8004),
    NOTIFICATION_SERVICE: (NOTIFICATION_SERVICE, 8005),
}

# How long to wait on Consul before falling back to the static map.
_CONSUL_TIMEOUT_SECONDS = 1.0


def _static_base_url(service_name: str) -> str:
    try:
        host, port = STATIC_SERVICE_MAP[service_name]
    except KeyError as exc:
        raise KeyError(f"Unknown downstream service '{service_name}'") from exc
    return f"http://{host}:{port}"


def _query_consul(service_name: str) -> str | None:
    """Return one healthy instance base URL from Consul, or ``None``."""

    url = f"{settings.consul_url}/v1/health/service/{service_name}"
    try:
        response = httpx.get(
            url, params={"passing": "true"}, timeout=_CONSUL_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        entries = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.debug("Consul lookup for '%s' failed: %s", service_name, exc)
        return None

    for entry in entries:
        service = entry.get("Service", {})
        node = entry.get("Node", {})
        address = service.get("Address") or node.get("Address")
        port = service.get("Port")
        if address and port:
            return f"http://{address}:{port}"
    return None


def resolve(service_name: str) -> str:
    """Return a base URL (``http://host:port``) for ``service_name``.

    Prefers a healthy Consul instance; falls back to the static Docker
    Compose hostname when Consul has nothing to offer.
    """

    return _query_consul(service_name) or _static_base_url(service_name)
