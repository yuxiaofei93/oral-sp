import json
import logging
import re
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

_request_id: ContextVar[str] = ContextVar("request_id", default="")
_request_id_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def current_request_id() -> str:
    return _request_id.get()


class JsonFormatter(logging.Formatter):
    extra_fields = (
        "backend",
        "duration_ms",
        "email_ref",
        "error_message",
        "error_type",
        "method",
        "path",
        "purpose",
        "record_id",
        "smtp_host",
        "smtp_port",
        "stack_trace",
        "status_code",
        "use_ssl",
        "use_tls",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        request_id = getattr(record, "request_id", "") or current_request_id()
        if request_id:
            payload["request_id"] = request_id
        for field in self.extra_fields:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("oral_sp.request")

    def __call__(self, request):
        supplied_request_id = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied_request_id
            if _request_id_pattern.fullmatch(supplied_request_id)
            else uuid.uuid4().hex
        )
        request.request_id = request_id
        token = _request_id.set(request_id)
        started_at = time.monotonic()
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            status_code = response.status_code
            log_method = self.logger.warning if status_code >= 500 else self.logger.info
            log_method(
                "request.completed",
                extra={
                    "duration_ms": round((time.monotonic() - started_at) * 1000),
                    "method": request.method,
                    "path": request.path,
                    "request_id": request_id,
                    "status_code": status_code,
                },
            )
            return response
        finally:
            _request_id.reset(token)
