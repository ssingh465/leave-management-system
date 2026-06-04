"""Resolution of logical service names to concrete ``host:port`` base URLs.

The gateway never hard-codes downstream addresses into its route handlers.
Instead each route asks this module for the base URL of a logical service
(``auth-service``, ``leave-balance-service``, ...). Resolution is attempted
against Consul's health API first, so that once the services register
themselves the gateway automatically discovers healthy instances and
load-balances across them.

Until Consul registration exists, and whenever Consul has no healthy entry
for a service, resolution falls back to a static map of Docker Compose
service hostnames. Those hostnames match the ``SERVICE_HOST`` values assigned
to each container, so the gateway works end-to-end on the compose network
before service discovery is wired up.
"""

from __future__ import annotations

import itertools
import logging
from threading import Lock

import httpx

from shared.config import settings

logger = logging.getLogger("api_gateway.consul_resolver")


# Logical service name -> default (host, port) on the Docker Compose network.
# These mirror the SERVICE_HOST / SERVICE_PORT values for each container and
# act as the fallback whenever Consul cannot resolve a healthy instance.
STATIC_SERVICE_MAP: dict[str, tuple[str, int]] = {
    "auth-service": ("auth-service", 8001),
    "leave-balance-service": ("leave-balance-service", 8002),
    "leave-request-service": ("leave-request-service", 8003),
    "manager-service": ("manager-service", 8004),
    "notification-service": ("notification-service", 8005),
}

# How long to wait on Consul before giving up and using the static fallback.
_CONSUL_TIMEOUT_SECONDS = 1.0

# Round-robin state per service: the instance set we built the cycle from
# (so we can detect changes) and the live cycle iterator over those instances.
_round_robin: dict[str, tuple[tuple[str, ...], "itertools.cycle[str]"]] = {}
_rr_lock = Lock()


def _static_base_url(service_name: str) -> str:
    try:
        host, port = STATIC_SERVICE_MAP[service_name]
    except KeyError as exc:
        raise KeyError(f"Unknown downstream service '{service_name}'") from exc
    return f"http://{host}:{port}"


def _query_consul(service_name: str) -> list[str]:
    """Return base URLs of healthy instances of ``service_name`` from Consul.

    Returns an empty list if Consul is unreachable or reports no passing
    instances; callers then fall back to the static map.
    """

    url = f"{settings.consul_url}/v1/health/service/{service_name}"
    try:
        response = httpx.get(
            url, params={"passing": "true"}, timeout=_CONSUL_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        entries = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.debug("Consul lookup for '%s' failed: %s", service_name, exc)
        return []

    base_urls: list[str] = []
    for entry in entries:
        service = entry.get("Service", {})
        node = entry.get("Node", {})
        address = service.get("Address") or node.get("Address")
        port = service.get("Port")
        if address and port:
            base_urls.append(f"http://{address}:{port}")
    return base_urls


def resolve(service_name: str) -> str:
    """Return a base URL (``http://host:port``) for the given logical service.

    Prefers a healthy instance reported by Consul (round-robin across them);
    falls back to the static Docker Compose hostname when Consul has nothing.
    """

    instances = _query_consul(service_name)
    if not instances:
        return _static_base_url(service_name)

    instance_key = tuple(instances)
    with _rr_lock:
        state = _round_robin.get(service_name)
        if state is None or state[0] != instance_key:
            cursor = itertools.cycle(instances)
            _round_robin[service_name] = (instance_key, cursor)
        else:
            cursor = state[1]
        return next(cursor)
