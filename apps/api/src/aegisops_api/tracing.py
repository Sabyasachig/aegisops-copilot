from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .settings import Settings

_TRACING_CONFIGURED = False


def configure_tracing(settings: Settings) -> None:
    global _TRACING_CONFIGURED

    if _TRACING_CONFIGURED or not settings.tracing_enabled:
        return

    provider = TracerProvider(
        resource=Resource.create(
            {
                SERVICE_NAME: settings.otel_service_name,
            }
        )
    )
    exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _TRACING_CONFIGURED = True


def instrument_fastapi(app: FastAPI, settings: Settings) -> None:
    if not settings.tracing_enabled:
        return

    configure_tracing(settings)
    FastAPIInstrumentor.instrument_app(app, excluded_urls=settings.otel_excluded_urls)


def get_current_trace_id() -> str | None:
    span = trace.get_current_span()
    context = span.get_span_context()
    if context is None or not context.is_valid:
        return None
    return f"{context.trace_id:032x}"
