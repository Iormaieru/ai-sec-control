"""Logging estructurado para Cloud Run -> Cloud Logging -> Dynatrace.

Todo sale por stdout, una línea JSON por evento. Cloud Logging interpreta
`severity`, `message` y `logging.googleapis.com/trace`; Dynatrace lee esos
mismos campos al ingerir desde Google Cloud y correlaciona por `trace_id` /
`span_id`. Sin dependencias nuevas (stdlib).

Qué NO se loguea, a propósito: contraseñas, tokens JWT, headers de
autorización, query strings, cuerpos de request/response ni el texto de los
documentos analizados (pueden contener información confidencial del banco).
"""

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.audit.context import current_actor_id
from app.core.config import Settings

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
span_id_var: ContextVar[str | None] = ContextVar("span_id", default=None)


_SEVERITY = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}
# Atributos estándar de LogRecord: lo que no está acá vino por `extra=`.
_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {
    "message",
    "asctime",
    "taskName",
    "color_message",  # uvicorn: copia del mensaje con códigos ANSI, ensucia el JSON
}


class RequestContextFilter(logging.Filter):
    """Agrega a cada registro el contexto del request en curso."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.trace_id = trace_id_var.get()
        record.span_id = span_id_var.get()
        actor = current_actor_id.get()
        record.user_id = str(actor) if actor else None
        return True


def _extra_fields(record: logging.LogRecord) -> dict:
    return {
        k: v
        for k, v in vars(record).items()
        if k not in _RESERVED and not k.startswith("_")
    }


class JsonFormatter(logging.Formatter):
    def __init__(self, gcp_project_id: str | None = None) -> None:
        super().__init__()
        self._gcp_project_id = gcp_project_id

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "severity": _SEVERITY.get(record.levelno, "DEFAULT"),
            "message": record.getMessage(),
            "logger": record.name,
        }
        payload.update(
            {k: v for k, v in _extra_fields(record).items() if v is not None}
        )
        if self._gcp_project_id and getattr(record, "trace_id", None):
            payload["logging.googleapis.com/trace"] = (
                f"projects/{self._gcp_project_id}/traces/{record.trace_id}"
            )
            if getattr(record, "span_id", None):
                payload["logging.googleapis.com/spanId"] = record.span_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        extras = {
            k: v
            for k, v in _extra_fields(record).items()
            if v is not None and k != "request_id"
        }
        rid = getattr(record, "request_id", None)
        line = (
            f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<7} {record.name}"
        )
        if rid:
            line += f" [{rid[:8]}]"
        line += f" {record.getMessage()}"
        if extras:
            line += f" {json.dumps(extras, ensure_ascii=False, default=str)}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


class _StdoutHandler(logging.StreamHandler):
    """Escribe en el sys.stdout vigente al momento de emitir, no en el que
    había al crear el handler (mismo criterio que logging.lastResort con
    stderr): sobrevive a que alguien reemplace sys.stdout después."""

    def __init__(self) -> None:
        logging.Handler.__init__(self)

    @property
    def stream(self):  # type: ignore[override]
        return sys.stdout


def configure_logging(settings: Settings) -> None:
    handler = _StdoutHandler()
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(
        JsonFormatter(settings.gcp_project_id)
        if settings.effective_log_format == "json"
        else TextFormatter()
    )

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level.upper())

    # Las librerías HTTP loguean a INFO cada request saliente con su URL
    # completa (query string incluida) y meten ruido: se dejan en WARNING.
    for noisy in ("httpx", "httpx2", "httpcore", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # uvicorn arma sus propios handlers con otro formato: se reencaminan al
    # root (un solo formato) y su access log se reemplaza por el del
    # middleware, que suma request_id, usuario, duración y ruta.
    for name in ("uvicorn", "uvicorn.error"):
        uv = logging.getLogger(name)
        uv.handlers.clear()
        uv.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False


def _parse_cloud_trace(header: str | None) -> tuple[str | None, str | None]:
    """X-Cloud-Trace-Context: TRACE_ID/SPAN_ID;o=1 (lo agrega Cloud Run)."""
    if not header:
        return None, None
    trace, _, rest = header.partition("/")
    span = rest.partition(";")[0]
    return trace or None, span or None


_access_logger = logging.getLogger("app.access")
_QUIET_PATHS = {"/health"}  # los health checks de Cloud Run no deben inundar los logs


class RequestLoggingMiddleware:
    """ASGI puro (no BaseHTTPMiddleware): corre en la misma task que la app,
    así que los ContextVar que asignan las dependencias (ej. el usuario)
    siguen visibles acá cuando termina el request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope["headers"]
        }
        request_id = headers.get("x-request-id") or str(uuid.uuid4())
        trace_id, span_id = _parse_cloud_trace(headers.get("x-cloud-trace-context"))
        request_id_var.set(request_id)
        trace_id_var.set(trace_id)
        span_id_var.set(span_id)

        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", []).append(
                    (b"x-request-id", request_id.encode("latin-1"))
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            _access_logger.error(
                "request_failed", exc_info=True, extra=self._fields(scope, 500, started)
            )
            raise
        else:
            level = (
                logging.DEBUG
                if scope["path"] in _QUIET_PATHS
                else (logging.ERROR if status_code >= 500 else logging.INFO)
            )
            _access_logger.log(
                level, "request", extra=self._fields(scope, status_code, started)
            )

    @staticmethod
    def _fields(scope: Scope, status_code: int, started: float) -> dict:
        route = scope.get("route")
        return {
            "http_method": scope["method"],
            # sin query string: puede traer filtros con datos del negocio
            "http_path": scope["path"],
            "http_route": getattr(route, "path", None),
            "http_status": status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        }
