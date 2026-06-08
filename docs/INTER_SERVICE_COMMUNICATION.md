# Inter-Service Communication Writeup

**Companion to:** [`MICROSERVICES_DESIGN.md`](MICROSERVICES_DESIGN.md)

This document describes how the six ELMS application services actually talk to
each other at runtime: every synchronous HTTP edge, the asynchronous event
flow over RabbitMQ, how services find each other through Consul, how the
circuit breakers behave when a downstream is unhealthy, and the assumptions
we relied on while wiring it up.

---

## 1. Communication channels at a glance

| Channel    | Implementation                                            | Used for                                                   |
| ---------- | --------------------------------------------------------- | ---------------------------------------------------------- |
| HTTP       | `httpx.AsyncClient` per service (`app.state.http_client`) | Every client-visible call and every required inter-service call |
| AMQP       | `aio-pika` over RabbitMQ                                  | Fire-and-forget notification events                        |
| Discovery  | Consul HTTP API (`/v1/agent/service/...` + `/v1/health/service/...`) | Service registration + gateway resolution         |
| Resilience | `pybreaker.CircuitBreaker` instances in `shared/circuit_breakers.py` | Wraps every cross-service HTTP call               |
| Tracing    | OpenTelemetry (FastAPI + httpx instrumentation)           | Propagates a trace id through the call chain               |

---

## 2. Synchronous HTTP calls

### 2.1 Gateway -> domain services (every request)

Every client request to `http://localhost:8080` is:

1. **Auth-checked** by `JWTAuthMiddleware` (`api_gateway/jwt_middleware.py`),
   except `POST /auth/login`. Missing / malformed / expired tokens get a
   uniform `401` with a `WWW-Authenticate: Bearer` header.
2. **Routed** by `api_gateway/router.py` based on path + method to one of the
   five domain services using `consul_resolver.resolve(<service_name>)` to
   pick a target host.
3. **Forwarded** with the original method / body / query string, plus two
   gateway-injected headers:

   ```
   X-User-Id:   <sub claim from JWT>
   X-User-Role: <role claim from JWT>
   ```

   Downstream services read those via `shared/auth_context.py`. They never
   re-validate the JWT - the gateway is the single source of truth for
   authentication. (Defence-in-depth: services still check role / ownership
   for authorisation decisions.)
4. **Returned** to the client with the downstream status / body unchanged.
5. **Logged** by `AccessLogMiddleware` as one JSON line:

   ```json
   { "level":"INFO","logger":"api_gateway.access","method":"POST","path":"/leaves","status":201,"latency_ms":24.3 }
   ```

The gateway holds a single shared `httpx.AsyncClient` with a 10 s upstream
timeout, created in the FastAPI lifespan.

#### 2.1.1 Routing table

| Method + Path                                  | Target service          | Notes                                       |
| ---------------------------------------------- | ----------------------- | ------------------------------------------- |
| `POST /auth/login`                             | `auth-service`          | Public; auth middleware excludes this path  |
| `GET /employees/me/balances`                   | `leave-balance-service` |                                              |
| `GET /employees/{id}/balances`                 | `leave-balance-service` | Balance service enforces self-or-manager    |
| `POST /leaves`                                 | `leave-request-service` |                                              |
| `GET /leaves/history`                          | `leave-request-service` |                                              |
| `PATCH /leaves/{id}/cancel`                    | `leave-request-service` |                                              |
| `GET /manager/requests`                        | `manager-service`       | Manager-only via `X-User-Role`              |
| `POST /manager/requests/{id}/approve`          | `manager-service`       |                                              |
| `POST /manager/requests/{id}/reject`           | `manager-service`       | Mandatory `rejection_reason`                |

Any path matching `/internal/*` is **not** routed by the gateway. Those
endpoints are reachable only from inside the Docker network and are used by
service-to-service calls (next section).

### 2.2 Service-to-service HTTP

There are exactly three cross-service synchronous edges:

#### 2.2.1 Leave Request -> Leave Balance (on `POST /leaves`)

- **What:** read the caller's remaining days for the requested leave type.
- **Why sync:** the apply decision depends on whether
  `payload.number_of_days <= remaining`.
- **Where:** `leave_request_service/balance_client.fetch_remaining()`, called
  from `apply_leave()` via `invoke_with_breaker(leave_balance_cb, ...)`.
- **Endpoint hit:** `GET /employees/{employee_id}/balances` on the Balance
  Service (forwarded over the Docker network with the caller's `X-User-Id` /
  `X-User-Role` headers so the Balance Service's RBAC check still passes).
- **Failure mapping:** circuit-breaker open OR transport error -> `503` to
  the client, with a clear `detail`: "Leave Balance Service is unavailable".

#### 2.2.2 Manager -> Leave Balance (on `POST /manager/requests/{id}/approve`)

- **What:** deduct days from the employee's balance.
- **Why sync:** we must not flip the request to `APPROVED` if the deduction
  would overdraw.
- **Where:** `manager_service/clients.deduct_balance()`, called from
  `approve_request()` via `invoke_with_breaker(leave_balance_cb, ...)`.
- **Endpoint hit:** `POST /internal/balances/deduct` on the Balance Service.
- **Order:** deduct first, then update request status. If the deduction fails
  with `409` (insufficient), the request stays `PENDING` and we propagate the
  `409` to the manager.

#### 2.2.3 Manager -> Leave Request (on `approve` and `reject`)

- **What:** load the request (to verify ownership + state) and then flip its
  status.
- **Why sync:** the Manager Service owns no state; the Request Service is
  the only place this record lives.
- **Where:** `manager_service/clients.get_request()` +
  `clients.set_request_status()`, both invoked through
  `invoke_with_breaker(leave_request_cb, ...)`.
- **Endpoints hit:**
  - `GET /internal/requests?request_id=<id>`
  - `POST /internal/requests/{id}/status` with `{manager_id, new_status, rejection_reason?}`
- **Authorisation:** the Request Service double-checks that the request's
  `reporting_manager_id` matches the `manager_id` in the payload before
  applying the transition.

### 2.3 Standard error response shape

Every error from any service is a JSON object with a single `detail` field:

```json
{ "detail": "<clear, specific message>" }
```

| Code | Meaning in ELMS                                                                       |
| ---- | ------------------------------------------------------------------------------------- |
| 400  | Business validation (bad date range, past date, day-count mismatch, invalid filter)   |
| 401  | Missing / invalid / expired JWT (gateway), or login failure (auth)                    |
| 403  | RBAC: not manager, not self, or request not routed to the acting manager              |
| 404  | Resource not found (leave request, balance row for employee+type)                     |
| 409  | Lifecycle conflict (overlap, insufficient balance, not-PENDING)                       |
| 422  | Pydantic structural / type validation (missing field, wrong type, non-positive days)  |
| 500  | Unhandled error (caught by `shared/exception_handlers.py`; also publishes `SYSTEM_ERROR`) |
| 503  | Circuit breaker open OR downstream transport error                                    |

---

## 3. Asynchronous events (RabbitMQ)

### 3.1 Topology

```
Publishers ──► RabbitMQ ──► Consumer ──► stdout (JSON line per event)
```

- **Broker:** `rabbitmq:5672` (`RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/`).
- **Queue:** `notifications`, durable, declared by every publisher on first
  publish (`shared/rabbitmq_publisher.py`). Idempotent.
- **Routing:** default exchange, routing key = queue name.
- **Persistence:** `delivery_mode=PERSISTENT` so messages survive a broker
  restart.

### 3.2 Event catalogue

| Event              | Publisher          | When                                                                  | Payload                                                                                              |
| ------------------ | ------------------ | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `LEAVE_APPLIED`    | Leave Request      | `POST /leaves` succeeds                                               | `event_type`, `employee_id`, `manager_id`, `leave_request_id`                                        |
| `LEAVE_APPROVED`   | Manager            | `POST /manager/requests/{id}/approve` succeeds                        | `event_type`, `employee_id`, `leave_request_id`                                                      |
| `LEAVE_REJECTED`   | Manager            | `POST /manager/requests/{id}/reject` succeeds                         | `event_type`, `employee_id`, `leave_request_id`, `reason`                                            |
| `SYSTEM_ERROR`     | Any service        | An unhandled exception bubbles into `shared/exception_handlers.py`    | `event_type`, `service`, `path`, `message`                                                           |

### 3.3 Publish semantics

Publishes are fire-and-forget. Every call site does:

```python
asyncio.create_task(publish_event(EventType.X, {...}))
```

so the HTTP response returns without waiting for the broker. If RabbitMQ is
down, the publisher logs a warning and returns - the HTTP request still
succeeds. Notifications are intentionally best-effort log entries.

### 3.4 Consumer

`notification_service/consumer.py` connects with `aio-pika.connect_robust`,
declares the same queue (idempotent), and consumes with manual ack. For
each event it:

1. Renders one of four log templates (matching the event type).
2. Appends the rendered entry to an in-memory list (`notification_service/store.py`).
3. Acks the message.

Templates are deliberately human-readable so they appear nicely in
`docker-compose logs notification-service` *and* in Kibana when the ELK
profile is on.

---

## 4. Resilience: circuit breakers

`shared/circuit_breakers.py` defines two named breakers, one per downstream
service that participates in cross-service synchronous calls:

| Breaker name             | Wraps calls to        | Used by                                  |
| ------------------------ | --------------------- | ---------------------------------------- |
| `leave_balance_service`  | Leave Balance         | Leave Request (fetch) + Manager (deduct) |
| `leave_request_service`  | Leave Request         | Manager (load + set status)              |

**Configuration:** `fail_max=3, reset_timeout=30s`. Three failures in a row
open the breaker; after 30 s it transitions to half-open and a single
success closes it again.

**Behaviour when open:**
- `invoke_with_breaker(...)` raises `pybreaker.CircuitBreakerError`.
- The caller catches it and raises `HTTPException(503, "...")` with a clear
  message (e.g. "Leave Balance Service is unavailable" or "A downstream
  service is unavailable").
- The client gets a `503` immediately, without us trying (and failing) to
  reach the dead downstream again.

**Demonstrating it:** stop the Balance Service container, then issue three
`POST /leaves` or `POST /manager/requests/{id}/approve` calls. The first
two return `503`-via-transport (the request actually hit the dead
container and timed out), the third returns `503` instantly because the
breaker is now open. Bring the container back up; after 30 s the next call
succeeds. The Postman collection has a documented manual scenario for this
in folder `09 - Cross-Cutting`.

---

## 5. Service discovery (Consul)

### 5.1 Registration

On startup every service calls `shared/consul_client.register_service(name, host, port)`,
which PUTs to `{CONSUL_URL}/v1/agent/service/register` with:

```json
{
  "ID": "<name>-<host>-<port>",
  "Name": "<name>",
  "Address": "<host>",
  "Port": <port>,
  "Check": {
    "HTTP": "http://<host>:<port>/health",
    "Interval": "10s",
    "Timeout": "5s",
    "DeregisterCriticalServiceAfter": "1m"
  }
}
```

Consul then polls `/health` every 10 s. If the service goes critical and
stays critical for 1 minute, Consul removes the registration automatically.

On shutdown, FastAPI's lifespan calls `deregister_service(...)`, which PUTs
to `/v1/agent/service/deregister/<id>` for a clean exit.

### 5.2 Resolution (gateway)

`api_gateway/consul_resolver.resolve(name)` is called on every forwarded
request. It:

1. Queries `{CONSUL_URL}/v1/health/service/<name>?passing=true` with a 1 s
   timeout.
2. If Consul returns one or more healthy instances, round-robins across them
   (state cached in `_round_robin`).
3. If Consul is unreachable OR has no passing instance, falls back to a
   `STATIC_SERVICE_MAP` (the docker-compose service names). This keeps the
   gateway working during cold start before all services have registered.

Service-to-service calls (Request -> Balance, Manager -> {Request,Balance})
do **not** go through the resolver today; they use the docker-compose
hostnames directly via `shared/service_client.py`. This is a deliberate
simplification (see assumptions §7).

---

## 6. Tracing

`shared/tracing.py` calls `init_tracing(service_name)` in every service's
lifespan, then `instrument_fastapi(app)` and (where there are outbound
calls) `instrument_httpx()`. The result:

- Every incoming request gets a server span.
- Every outbound `httpx` call gets a client span, with a propagated
  `traceparent` header.
- Spans are exported to stdout via `ConsoleSpanExporter`, so the trace ID
  shows up in every service's JSON logs.

That means a single apply -> deduct -> set-status call chain can be
reconstructed end-to-end by grepping for the same `trace_id` across the
five services' logs (or, in the ELK profile, filtering by `trace_id` in
Kibana).

---

## 7. Assumptions

These are deliberate simplifications made during the design of the system.

1. **No DB.** Every service holds its state in process-local Python dicts;
   restart loses data. Reseed-on-startup makes this safe for the demo.
2. **Single shared JWT secret.** Both the gateway and the auth service use
   `JWT_SECRET_KEY` for HS256 sign + verify. A real deployment would use an
   asymmetric key pair so only auth holds the private key.
3. **Gateway is the only auth.** Downstream services trust the gateway's
   `X-User-Id` / `X-User-Role` headers. Because `/internal/*` is unreachable
   from outside the Docker network, this is safe as long as the network is
   trusted. Anyone with access to the Docker network can call internal
   endpoints, by design (for the Manager + Request services to talk).
4. **`/internal/*` is private.** The gateway router has zero `/internal/*`
   routes. A real deployment would enforce this with a network policy as
   well; here we rely on Docker network isolation.
5. **Service-to-service calls use compose hostnames.** Only the gateway
   round-robins through Consul. With one instance per service this is
   equivalent; scaling out a downstream would need the same Consul lookup on
   the caller side (a half-day refactor of `shared/service_client.py`).
6. **Fire-and-forget RabbitMQ.** If the broker is down, the HTTP request
   still succeeds and the event is lost.    Notifications are best-effort log entries by design. A real system would
   use a transactional outbox.
7. **In-memory notification log.** The notification consumer keeps the
   rendered log lines in a list inside its own process; restart clears it.
   The text is also in stdout and (if ELK is on) in Elasticsearch.
8. **Static seed UUIDs + credentials.** `shared/seed_config.py` is the
   source of truth that every service reads at startup. There is no
   self-registration and no admin endpoint for adding users.
9. **Single broker, single Consul.** No HA. Restarting either is disruptive;
   a real deployment would cluster both.
10. **Tracing exports to stdout, not to an OTLP collector.** Switching to a
    real collector is just a setting in `shared/tracing.py`.

---

## 8. Live verification commands

Every check the spec asks for can be reproduced from a single
`docker-compose up --build`:

| Check                                           | How                                                                                  |
| ----------------------------------------------- | ------------------------------------------------------------------------------------ |
| All 6 services in Consul                        | <http://localhost:8500/ui/dc1/services>                                              |
| Notification consumer is wired                  | `docker-compose logs notification-service -f` then issue an apply / approve / reject |
| Circuit breaker opens                           | Stop Balance, hit `POST /leaves` thrice, observe the third returns `503` instantly   |
| Trace ids correlate                             | Search the per-service logs for the same `trace_id`                                  |
| `SYSTEM_ERROR` publishes on 500                 | Trigger an exception in a service, see the event arrive in Notification             |
| ELK indexing (when `--profile elk`)             | <http://localhost:5601> -> Discover -> index pattern `elms-logs-*`                    |
