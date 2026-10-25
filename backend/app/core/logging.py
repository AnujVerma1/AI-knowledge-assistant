"""Structured logging. Readable console output in development, JSON lines in production.

Modules log with the standard library (logging.getLogger(__name__)) and pass fields via
extra={...}; structlog renders them and redacts anything that looks like a credential.
"""

import logging
import sys

import structlog

_SENSITIVE_FRAGMENTS = ("password", "secret", "token", "authorization", "cookie", "api_key")


def _redact_sensitive(_logger, _method, event_dict: dict) -> dict:
    event_dict.pop("color_message", None)  # uvicorn's ANSI-coloured duplicate of the message
    for key in event_dict:
        if any(fragment in key.lower() for fragment in _SENSITIVE_FRAGMENTS):
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(level: str, *, json_logs: bool) -> None:
    shared_processors = [
        structlog.contextvars.merge_contextvars,  # adds request_id bound by the request middleware
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.ExtraAdder(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact_sensitive,
    ]
    renderer = structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                renderer,
            ],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Route uvicorn's logs through the same handler; our middleware replaces its access log.
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    logging.getLogger("uvicorn.access").disabled = True
    for noisy in ("httpx", "httpcore", "chromadb"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
