from __future__ import annotations

import logging

import structlog

from .settings import Settings, get_settings


def should_use_json_logs(settings: Settings) -> bool:
    """Return True when JSON logs should be emitted."""
    if settings.log_format == "json":
        return True
    if settings.log_format == "console":
        return False
    return settings.environment.lower() in {"prod", "production"}


def configure_logging(settings: Settings | None = None) -> None:
    """Configure stdlib + structlog once for API and worker processes."""
    cfg = settings or get_settings()

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer = (
        structlog.processors.JSONRenderer()
        if should_use_json_logs(cfg)
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(cfg.log_level.upper())

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    return structlog.get_logger(name)


def clear_log_context() -> None:
    structlog.contextvars.clear_contextvars()


def bind_log_context(
    *,
    incident_id: str | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
    request_id: str | None = None,
) -> None:
    """Bind standard context fields used across API and worker logs."""
    context: dict[str, str] = {}
    if incident_id:
        context["incident_id"] = incident_id
    if run_id:
        context["run_id"] = run_id
    if user_id:
        context["user_id"] = user_id
    if request_id:
        context["request_id"] = request_id
    if context:
        structlog.contextvars.bind_contextvars(**context)
