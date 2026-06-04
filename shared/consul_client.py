"""Consul agent registration helpers used by every microservice on startup."""

from __future__ import annotations

import logging

import httpx

from shared.config import settings

logger = logging.getLogger("shared.consul_client")

_REGISTRATION_TIMEOUT_SECONDS = 3.0


def _service_id(name: str, host: str, port: int) -> str:
    return f"{name}-{host}-{port}"


def register_service(name: str, host: str, port: int) -> None:
    """Register this instance with the local Consul agent."""

    service_id = _service_id(name, host, port)
    payload = {
        "ID": service_id,
        "Name": name,
        "Address": host,
        "Port": port,
        "Check": {
            "HTTP": f"http://{host}:{port}/health",
            "Interval": "10s",
            "Timeout": "5s",
            "DeregisterCriticalServiceAfter": "1m",
        },
    }
    url = f"{settings.consul_url}/v1/agent/service/register"

    try:
        response = httpx.put(
            url, json=payload, timeout=_REGISTRATION_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        logger.info("Registered %s with Consul at %s:%s", name, host, port)
    except httpx.HTTPError as exc:
        logger.warning("Consul registration failed for %s: %s", name, exc)


def deregister_service(name: str, host: str, port: int) -> None:
    """Remove this instance from the Consul agent registry."""

    service_id = _service_id(name, host, port)
    url = f"{settings.consul_url}/v1/agent/service/deregister/{service_id}"

    try:
        response = httpx.put(url, timeout=_REGISTRATION_TIMEOUT_SECONDS)
        response.raise_for_status()
        logger.info("Deregistered %s from Consul", service_id)
    except httpx.HTTPError as exc:
        logger.warning("Consul deregistration failed for %s: %s", service_id, exc)
