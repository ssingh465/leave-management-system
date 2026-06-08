"""API Gateway entry point.



The gateway is the only service exposed to clients. It authenticates every

request (except the public ``/auth/login``), logs access, and forwards the

call to the downstream microservice that owns the route, returning that

service's response unchanged.



Middleware order (outermost first): access logging wraps authentication, so

every response - including ``401``s produced by the auth layer - is logged.

A single shared ``httpx.AsyncClient`` is created on startup and reused for all

forwarded requests for connection pooling.

"""



from __future__ import annotations



from contextlib import asynccontextmanager



import httpx

from fastapi import FastAPI



from api_gateway.jwt_middleware import JWTAuthMiddleware

from api_gateway.logging_middleware import AccessLogMiddleware

from api_gateway.router import router

from shared.config import settings

from shared.consul_client import deregister_service, register_service

from shared.exception_handlers import register_global_exception_handler

from shared.logging_config import configure_logging

from shared.tracing import init_tracing, instrument_fastapi, instrument_httpx



configure_logging(settings.service_name)



# Upstream call budget. Kept short so a stalled downstream surfaces quickly as

# a 504 rather than tying up gateway connections.

_UPSTREAM_TIMEOUT_SECONDS = 10.0





@asynccontextmanager

async def lifespan(app: FastAPI):

    init_tracing(settings.service_name)

    instrument_httpx()

    register_service(

        settings.service_name, settings.service_host, settings.service_port

    )

    app.state.http_client = httpx.AsyncClient(timeout=_UPSTREAM_TIMEOUT_SECONDS)

    try:

        yield

    finally:

        await app.state.http_client.aclose()

        deregister_service(

            settings.service_name, settings.service_host, settings.service_port

        )





app = FastAPI(title="API Gateway", lifespan=lifespan)

register_global_exception_handler(app)

instrument_fastapi(app)



# Added last == outermost: access logging wraps the auth check.

app.add_middleware(JWTAuthMiddleware)

app.add_middleware(AccessLogMiddleware)



app.include_router(router)





@app.get("/health")

async def health() -> dict[str, str]:

    """Liveness probe for the gateway itself (public, no auth required)."""



    return {"status": "healthy", "service": "api-gateway"}


