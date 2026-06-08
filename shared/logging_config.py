"""Centralised structured (JSON) logging for every microservice.

Every service calls ``configure_logging(service_name)`` once at import time so
every log line - whether it comes from the app code, FastAPI, uvicorn, or a
third-party library - is emitted as a single JSON object on stdout:

    {
      "timestamp": "2026-06-04T12:34:56.789Z",
      "level": "INFO",
      "logger": "leave_request_service",
      "service": "leave-request-service",
      "message": "Leave request <id> created for employee <id> ..."
    }

JSON-on-stdout is what the ELK stack consumes when enabled: Filebeat tails
Docker container logs, decodes the ``message`` field as JSON, and ships the
resulting structured event to Logstash -> Elasticsearch. The same JSON line is
still human-readable in ``docker-compose logs <service>`` and is easy to grep
when ELK is not running.

Re-calling ``configure_logging`` is safe; existing handlers on the root logger
are removed before the JSON handler is attached so we never end up with
duplicate log lines.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from pythonjsonlogger import jsonlogger


class _UtcJsonFormatter(jsonlogger.JsonFormatter):
    """JsonFormatter that renames the default fields and forces UTC timestamps."""

    def add_fields(
        self,
        log_record: dict,
        record: logging.LogRecord,
        message_dict: dict,
    ) -> None:
        super().add_fields(log_record, record, message_dict)

        # ISO-8601 UTC with millisecond precision, always ending in 'Z'.
        log_record["timestamp"] = (
            datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        # Normalise the level and logger keys (defaults are "levelname"/"name").
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        # Service is stamped on every record by the LogRecord factory installed
        # in `configure_logging`; surface it as a top-level field for Kibana.
        if hasattr(record, "service"):
            log_record["service"] = record.service
        # Surface the exception type when present so it is filterable in Kibana
        # without having to parse the rendered traceback.
        if record.exc_info:
            log_record["exception_type"] = record.exc_info[0].__name__


def configure_logging(service_name: str, *, level: int = logging.INFO) -> None:
    """Install the JSON log handler on the root logger.

    Args:
        service_name: Logical service name (e.g. ``"auth-service"``). Stamped
            on every log record as ``service`` so Kibana can filter per
            service.
        level: Root log level. Defaults to ``INFO``; set ``DEBUG`` via env if
            deeper visibility is needed.
    """

    formatter = _UtcJsonFormatter(
        # The format string declares which standard LogRecord attributes show
        # up as top-level JSON keys; the extra fields added in `add_fields`
        # land alongside them.
        "%(timestamp)s %(level)s %(logger)s %(message)s",
        rename_fields={},
    )
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Drop any handlers a prior call (or `logging.basicConfig`) installed so
    # records are not emitted twice.
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    # Inject the service name as a default extra on every record without
    # forcing every call-site to pass it explicitly.
    old_factory = logging.getLogRecordFactory()

    def _record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        if not hasattr(record, "service"):
            record.service = service_name
        return record

    logging.setLogRecordFactory(_record_factory)

    # Uvicorn ships its own handlers; clear them so its access/error logs flow
    # through the root handler we just installed and come out as JSON too.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(noisy)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
