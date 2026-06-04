"""OpenTelemetry bootstrap with console span export for local development."""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor


def init_tracing(service_name: str) -> None:
    """Configure a process-wide tracer that prints spans to stdout."""

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)


def instrument_fastapi(app) -> None:
    """Auto-instrument inbound HTTP requests for a FastAPI application."""

    FastAPIInstrumentor.instrument_app(app)


def instrument_httpx() -> None:
    """Propagate trace context on outbound httpx calls."""

    HTTPXClientInstrumentor().instrument()
