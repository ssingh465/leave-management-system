# Employee Leave Management System (ELMS)

A backend-only microservices platform that lets employees apply for leave and lets
managers view, approve, or reject requests for their direct reports. Built as six
Python / FastAPI services that talk to each other over HTTP through an API
gateway, publish notification events through RabbitMQ, and discover each other
through Consul.

The system is fully containerised and ships with a single `docker-compose.yml`
that brings up all eight containers (Consul + RabbitMQ + six services) on one
shared network.

> Demo video: `https://github.com/ssingh465/leave-management-system`
>
> Repository: `https://nagarro-my.sharepoint.com/:v:/r/personal/shubhanshu_singh_nagarro_com/Documents/Recordings/NAGP%20%E2%80%93%20Microservices%20Assignment%20Demo%20%2008%20Jun%202026-20260608_224157-Meeting%20Recording.mp4?csf=1&web=1&e=cnrGn5&nav=eyJyZWZlcnJhbEluZm8iOnsicmVmZXJyYWxBcHAiOiJTdHJlYW1XZWJBcHAiLCJyZWZlcnJhbFZpZXciOiJTaGFyZURpYWxvZy1MaW5rIiwicmVmZXJyYWxBcHBQbGF0Zm9ybSI6IldlYiIsInJlZmVycmFsTW9kZSI6InZpZXcifX0%3D`

---

## Table of Contents

1. [Architecture](#architecture)
2. [Services and ports](#services-and-ports)
3. [Prerequisites](#prerequisites)
4. [Quick start](#quick-start)
5. [Environment variables](#environment-variables)
6. [Seeded users and credentials](#seeded-users-and-credentials)
7. [API endpoints (through the gateway)](#api-endpoints-through-the-gateway)
8. [Postman collection](#postman-collection)
9. [Docker Hub images](#docker-hub-images)
10. [Building and pushing images](#building-and-pushing-images)
11. [Operational notes](#operational-notes)
12. [Observability: ELK stack](#observability-elk-stack)
13. [Documentation](#documentation)
14. [Project layout](#project-layout)
15. [Troubleshooting](#troubleshooting)

---

## Architecture

```mermaid
flowchart LR
  Client[Postman Client] --> GW[API Gateway :8080]
  GW --> Auth[Auth Service :8001]
  GW --> Bal[Leave Balance :8002]
  GW --> Req[Leave Request :8003]
  GW --> Mgr[Manager :8004]
  Req -->|"check balance (httpx + breaker)"| Bal
  Mgr -->|"deduct (httpx + breaker)"| Bal
  Mgr -->|"read / update status"| Req
  Req -->|publish| MQ[(RabbitMQ :5672)]
  Mgr -->|publish| MQ
  MQ --> Notif[Notification :8005]
  Auth -. register .-> Consul[(Consul :8500)]
  Bal -. register .-> Consul
  Req -. register .-> Consul
  Mgr -. register .-> Consul
  Notif -. register .-> Consul
  GW -. resolve .-> Consul
```

Key design choices:

- **Stateless services.** Each service holds its own in-memory store; nothing is
  shared across services and there is no database. State is rebuilt from
  `shared/seed_config.py` on startup.
- **Gateway-only ingress.** Only the API gateway publishes a host port (`8080`).
  Every other service is reachable only through the gateway from the outside,
  and over the internal Docker network between services.
- **HS256 JWT.** The auth service issues a signed token at `/auth/login`; the
  gateway validates it once at the edge and every downstream service trusts the
  `X-User-Id` / `X-User-Role` headers it forwards.
- **Async eventing.** Leave Request and Manager publish `LEAVE_APPLIED`,
  `LEAVE_APPROVED`, `LEAVE_REJECTED`, and `SYSTEM_ERROR` events to RabbitMQ;
  Notification consumes them and renders human-readable templates to stdout.
- **Circuit breakers.** Cross-service HTTP calls (request -> balance,
  manager -> balance, manager -> request) are wrapped in `pybreaker`; when an
  upstream is unhealthy the breaker opens and callers see a clean `503`.
- **Tracing.** OpenTelemetry is wired in via `shared/tracing.py`, with FastAPI
  and httpx auto-instrumentation. Spans are exported to stdout.

## Services and ports

| Service                   | Container name                       | Port  | Notes                                       |
| ------------------------- | ------------------------------------ | ----- | ------------------------------------------- |
| API Gateway               | `leave-mgmt-api-gateway`             | 8080  | Only host-published port                    |
| Auth Service              | `leave-mgmt-auth-service`            | 8001  | Issues HS256 JWTs                           |
| Leave Balance Service     | `leave-mgmt-leave-balance-service`   | 8002  | 12 / 10 / 15 CASUAL / SICK / PRIVILEGE      |
| Leave Request Service     | `leave-mgmt-leave-request-service`   | 8003  | 4 validations + lifecycle                   |
| Manager Service           | `leave-mgmt-manager-service`         | 8004  | Approve / reject, team-scope RBAC           |
| Notification Service      | `leave-mgmt-notification-service`    | 8005  | RabbitMQ consumer, logs to stdout           |
| Consul                    | `leave-mgmt-consul`                  | 8500  | Service registry + UI                       |
| RabbitMQ                  | `leave-mgmt-rabbitmq`                | 15672 | Management UI (AMQP on 5672)                |

## Prerequisites

- Docker Engine **24+** and Docker Compose **v2+**
- ~2 GB free RAM for the full stack
- (Optional) [Newman](https://github.com/postmanlabs/newman) if you want to run
  the Postman collection from the CLI

That's it. No local Python install is needed to run the system - everything
runs inside containers.

## Quick start

```bash
# 1. Clone
git clone

# 2. Provision local environment file
cp .env.example .env
# (defaults are usable as-is; see "Environment variables" below)

# 3. Bring everything up (build from source the first time)
docker-compose up --build

# 4. Watch the logs - you should see all six services register with Consul
#    and the notification service connect to RabbitMQ.

# 5. Smoke-test the cold start
curl -s -X POST http://localhost:8080/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"manager1","password":"Manager@123"}'
# -> { "access_token": "...", "token_type": "bearer" }
```

Useful URLs once the stack is running:

- API Gateway: <http://localhost:8080>
- Consul UI: <http://localhost:8500>
- RabbitMQ UI: <http://localhost:15672> (guest / guest)

To stop and clean up:

```bash
docker-compose down            # stop containers, keep network
docker-compose down --volumes  # also remove any named volumes
```

### Run from pre-built Docker Hub images

If you do not want to build locally, set `DOCKERHUB_USERNAME` in `.env` to the
account that owns the published images and then:

```bash
docker-compose pull
docker-compose up
```

(`up` without `--build` skips the local image build and uses what `pull` just
fetched.)

## Environment variables

Configuration lives in `.env` (loaded by `docker-compose` via `env_file:` and by
each Python service via `python-dotenv`). The shipped `.env.example` documents
every variable; the table below summarises them.

### Application variables (the 8 the services read)

| Variable                 | Default                                      | Used by                                | Purpose                                                                 |
| ------------------------ | -------------------------------------------- | -------------------------------------- | ----------------------------------------------------------------------- |
| `JWT_SECRET_KEY`         | `leave-mgmt-dev-secret-change-me-in-...`     | auth, gateway                          | HS256 signing key. **Replace in production.**                           |
| `JWT_ALGORITHM`          | `HS256`                                      | auth, gateway                          | Token algorithm.                                                        |
| `JWT_EXPIRATION_MINUTES` | `60`                                         | auth                                   | Access token lifetime.                                                  |
| `RABBITMQ_URL`           | `amqp://guest:guest@rabbitmq:5672/`          | request, manager, notification         | AMQP connection URL.                                                    |
| `CONSUL_URL`             | `http://consul:8500`                         | all six services                       | Consul HTTP API for service registration and resolution.                |
| `SERVICE_NAME`           | overridden per service                       | all six services                       | Logical name used for Consul registration and log enrichment.           |
| `SERVICE_HOST`           | overridden per service                       | all six services                       | Hostname Consul will hand out for the service.                          |
| `SERVICE_PORT`           | overridden per service                       | all six services                       | Port Consul will hand out for the service.                              |

`SERVICE_NAME` / `SERVICE_HOST` / `SERVICE_PORT` are set per-container inside
`docker-compose.yml` (so the same `.env` works for every service); the other
five values are global to the stack.

### Docker Hub image coordinates (used only by `docker-compose`)

| Variable             | Default                    | Purpose                                                                     |
| -------------------- | -------------------------- | --------------------------------------------------------------------------- |
| `DOCKERHUB_USERNAME` | `your-dockerhub-username`  | Account that owns the published images. Required for `pull` / `push`.       |
| `IMAGE_TAG`          | `latest`                   | Image tag (e.g. `v1.0.0`). `latest` is fine for local development.          |

## Seeded users and credentials

The platform has no self-registration; a small, fixed roster of users is
loaded into the auth service at startup. The same UUIDs are reused across
every service so balance records and reporting-manager links line up.

| Role     | Username   | Password         | UUID                                     | Reports to |
| -------- | ---------- | ---------------- | ---------------------------------------- | ---------- |
| MANAGER  | `manager1` | `Manager@123`    | `00000000-0000-0000-0000-000000000001`   |  -         |
| EMPLOYEE | `emp1`     | `Employee@123`   | `00000000-0000-0000-0000-000000000002`   | `manager1` |
| EMPLOYEE | `emp2`     | `Employee@123`   | `00000000-0000-0000-0000-000000000003`   | `manager1` |

Every employee is seeded with `CASUAL=12 / SICK=10 / PRIVILEGE=15` days.

> These are **development-only** credentials. Replace them (and
> `JWT_SECRET_KEY`) before deploying anywhere reachable from the public
> internet.

## API endpoints (through the gateway)

All routes below are reached at `http://localhost:8080`. Only `POST /auth/login`
is public; every other route requires `Authorization: Bearer <jwt>`.

| Method | Path                                       | Auth     | Description                                                  |
| ------ | ------------------------------------------ | -------- | ------------------------------------------------------------ |
| POST   | `/auth/login`                              | public   | Exchange username + password for an HS256 JWT                |
| GET    | `/employees/me/balances`                   | any user | Caller's leave balances                                      |
| GET    | `/employees/{id}/balances`                 | RBAC     | Self, or a manager reading a direct report                   |
| POST   | `/leaves`                                  | employee | Apply for leave (runs all four validations)                  |
| GET    | `/leaves/history`                          | employee | Caller's history with `status` filter + pagination           |
| PATCH  | `/leaves/{id}/cancel`                      | employee | Cancel a `PENDING` request (owned by caller)                 |
| GET    | `/manager/requests`                        | manager  | List team requests (optional status / employee / date)       |
| POST   | `/manager/requests/{id}/approve`           | manager  | Approve a `PENDING` request (deducts balance)                |
| POST   | `/manager/requests/{id}/reject`            | manager  | Reject a `PENDING` request (mandatory `rejection_reason`)    |

Internal routes (`/internal/...`) are deliberately **not** exposed by the
gateway; they are reachable only from inside the Docker network.

## Postman collection

A complete collection ships at `ELMS_Postman_Collection.json` (Postman v2.1, 9
folders / 54 requests / 73 assertions).

1. Import `ELMS_Postman_Collection.json` into Postman.
2. The collection defines `base_url` (defaults to `http://localhost:8080`) and
   stores tokens / request IDs as **collection variables** as the run
   progresses, so it is meant to be executed top-to-bottom.
3. A collection-level prerequest script computes dates relative to "today"
   (`range_a` ... `range_e`, plus `past_*`), keeping the past-date and overlap
   scenarios stable no matter when you run it.
4. Either click **Run Collection** in Postman, or run from the CLI:

   ```bash
   newman run ELMS_Postman_Collection.json
   ```

Folders `01 - Authentication` through `08 - Cancel Leave` cover the happy path
plus every documented failure mode (RBAC 403s, lifecycle 409s, validation
400s, Pydantic 422s, auth 401s). Folder `09 - Cross-Cutting` contains manual
procedures (circuit-breaker 503 by killing the balance service, tracing in
stdout, `SYSTEM_ERROR` publishing) - the request bodies and asserts are still
there, you just need to perform the out-of-band action first.

The collection is generated from `build_collection.py`; re-run that script to
regenerate the JSON when endpoints change.

## Docker Hub images

The stack is published as six images. The default names below assume the
placeholder username; swap `your-dockerhub-username` for the real account.

| Service               | Image                                                        |
| --------------------- | ------------------------------------------------------------ |
| API Gateway           | `your-dockerhub-username/elms-api-gateway:latest`            |
| Auth                  | `your-dockerhub-username/elms-auth-service:latest`           |
| Leave Balance         | `your-dockerhub-username/elms-leave-balance-service:latest`  |
| Leave Request         | `your-dockerhub-username/elms-leave-request-service:latest`  |
| Manager               | `your-dockerhub-username/elms-manager-service:latest`        |
| Notification          | `your-dockerhub-username/elms-notification-service:latest`   |

Each `docker-compose` service entry has both `build:` (so source builds still
work) and `image:` (so `pull` works once images exist on Docker Hub). The
`image:` value is `${DOCKERHUB_USERNAME:-your-dockerhub-username}/elms-<svc>:${IMAGE_TAG:-latest}`,
so overriding the two env vars is enough to point the same compose file at any
account or tag.

## Building and pushing images

### Build all six locally

```bash
docker-compose build
```

This populates the `image:` names from compose (so the resulting tags are
already `<DOCKERHUB_USERNAME>/elms-<svc>:<IMAGE_TAG>`), which means you can push
without an extra `docker tag` step.

### Push to Docker Hub

```bash
# 1. Set the env vars used by compose to derive image names
export DOCKERHUB_USERNAME=<your-account>
export IMAGE_TAG=latest

# 2. (Re-)build so the images are tagged with the right name
docker-compose build

# 3. Authenticate and push
docker login
docker-compose push
```

On Windows PowerShell use `$env:DOCKERHUB_USERNAME = "<your-account>"` instead
of `export`, or just edit `.env` directly.

### Pull and run from Docker Hub

```bash
docker-compose pull
docker-compose up
```

## Observability: ELK stack

Every service emits **structured JSON log lines** on stdout via
`shared/logging_config.py`:

```json
{"timestamp":"2026-06-04T12:34:56.789Z","level":"INFO","logger":"leave_request_service","service":"leave-request-service","message":"Leave request <id> created for employee <id> (CASUAL, 3 day(s))"}
```

The base 8-container stack does **not** require ELK - those JSON lines are
already searchable with `docker-compose logs <service>` and easy to pipe into
`jq`. The ELK stack adds proper indexed search on top.

### Starting the ELK stack (opt-in via a compose profile)

```bash
docker-compose --profile elk up --build
```

This adds four containers alongside the existing eight:

| Container             | Port | Role                                                                                                |
| --------------------- | ---- | --------------------------------------------------------------------------------------------------- |
| `leave-mgmt-elasticsearch` | 9200 | Single-node Elasticsearch (security disabled for the demo)                                     |
| `leave-mgmt-logstash`      | 5044 | Beats input -> JSON decode (`elk/logstash/pipeline/logstash.conf`) -> Elasticsearch              |
| `leave-mgmt-kibana`        | 5601 | UI; index pattern `elms-logs-*`                                                                  |
| `leave-mgmt-filebeat`      | -    | Reads `/var/lib/docker/containers/*.log` via the Docker socket and ships to Logstash             |

Filebeat tails Docker's per-container log files (the JSON line each Python
service writes is the `message` field on Docker's side), forwards them to
Logstash, which decodes `message` as JSON and indexes the resulting fields
into Elasticsearch. Kibana on port 5601 shows them via Discover.

Without the `--profile elk` flag the four ELK containers are not started; the
default `docker-compose up` is untouched.

### Stopping the ELK stack

```bash
docker-compose --profile elk down            # stop everything (app + ELK)
docker-compose --profile elk down --volumes  # also discard the Elasticsearch indices
```

## Documentation

Every long-form deliverable lives under `docs/`:

| Document                                                                       | What's in it                                                                            |
| ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| [`docs/MICROSERVICES_DESIGN.md`](docs/MICROSERVICES_DESIGN.md)                  | Architecture overview, container topology, service responsibilities, data ownership     |
| [`docs/INTER_SERVICE_COMMUNICATION.md`](docs/INTER_SERVICE_COMMUNICATION.md)    | Every HTTP edge, the RabbitMQ event flow, Consul registration/resolution, the breakers  |

## Operational notes

- **Cold start order.** `consul` and `rabbitmq` come up first (with
  healthchecks); the application services depend on them being healthy.
  Downstream services also wait for their immediate upstreams (e.g. Manager
  waits for Balance + Request) via `depends_on`.
- **Service discovery.** Each service registers itself with Consul on startup
  and deregisters on shutdown (see `shared/consul_client.py`). The gateway
  resolves downstream services through Consul - so renaming a service in
  compose without updating Consul registration will break routing.
- **Event flow.** `LEAVE_APPLIED` is published when an employee successfully
  applies; `LEAVE_APPROVED` / `LEAVE_REJECTED` are published when the manager
  decides; `SYSTEM_ERROR` is published when an uncaught exception bubbles into
  the global handler. The notification service logs all four to stdout, so
  `docker-compose logs notification-service -f` is a good live view.
- **Circuit breakers.** Each cross-service call has a dedicated `pybreaker`
  instance. When a downstream is killed (e.g. `docker-compose stop leave-balance-service`),
  the next few apply / approve calls fail through and trip the breaker; once
  open, the gateway returns `503` immediately until the reset timeout elapses.

## Project layout

```
.
├── api_gateway/             # FastAPI gateway: JWT, routing, httpx forwarding
├── auth_service/            # Login + JWT issuance + user seeding
├── leave_balance_service/   # Balance CRUD + internal deduct endpoint
├── leave_request_service/   # Apply / history / cancel + validations
├── manager_service/         # Team view + approve / reject orchestration
├── notification_service/    # aio-pika consumer + 4 log templates
├── shared/                  # Code reused by every service
│   ├── auth_context.py
│   ├── circuit_breakers.py
│   ├── config.py
│   ├── consul_client.py
│   ├── enums.py
│   ├── exception_handlers.py
│   ├── jwt_utils.py
│   ├── logging_config.py       # JSON structured logs to stdout
│   ├── rabbitmq_publisher.py
│   ├── seed_config.py
│   ├── service_client.py
│   └── tracing.py
├── docs/                    # Long-form deliverables
│   ├── MICROSERVICES_DESIGN.md
│   └── INTER_SERVICE_COMMUNICATION.md
├── elk/                     # ELK stack (opt-in via `--profile elk`)
│   ├── logstash/pipeline/logstash.conf
│   └── filebeat/filebeat.yml
├── docker-compose.yml       # 8 default containers + 4 ELK (profile-gated)
├── .env / .env.example      # Environment variables (see above)
├── .dockerignore            # Keeps build context lean
├── ELMS_Postman_Collection.json
├── build_collection.py      # Generator for the Postman collection
└── README.md
```

Each application image is built from the **repo-root context** (so `shared/`
is always on the path) using its own `Dockerfile`; the compose file pins
`context: .` and `dockerfile: <service>/Dockerfile` accordingly.

## Troubleshooting

| Symptom                                                              | Likely cause                                              | Fix                                                                                          |
| -------------------------------------------------------------------- | --------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `docker-compose pull` says `pull access denied`                      | `DOCKERHUB_USERNAME` is still the placeholder             | Set `DOCKERHUB_USERNAME=<your-account>` in `.env`, or rebuild locally with `up --build`.     |
| `POST /auth/login` returns `401` with the right credentials          | Stack hasn't finished starting; auth service still seeding | Wait a few seconds and retry. `docker-compose logs auth-service` should show "Seeded N users". |
| `503` from `/leaves` or `/manager/requests/{id}/approve`             | Downstream circuit breaker is open                        | `docker-compose ps` - the balance or request service is probably down. Bring it back up.     |
| All requests return `502` / `connection refused`                     | A service failed to register with Consul                  | Open <http://localhost:8500/ui/dc1/services> - the missing service won't be listed. Check its logs. |
| `docker-compose up` keeps recreating containers in a loop            | Healthcheck failing on Consul or RabbitMQ                 | Check `docker-compose logs consul rabbitmq`; usually a stale named container. `docker-compose down -v` and retry. |
| Postman runs but every assert fails                                  | Wrong `base_url` collection variable                      | Open the collection variables tab - it should be `http://localhost:8080`.                    |

---
