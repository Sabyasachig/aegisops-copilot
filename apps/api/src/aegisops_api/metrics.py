from __future__ import annotations

from prometheus_client import Counter, Histogram

_AGENT_RUN_DURATION_SECONDS = Histogram(
    "agent_run_duration_seconds",
    "Wall-clock duration of completed agent runs.",
    buckets=(0.5, 1, 2.5, 5, 10, 20, 30, 60, 120, 300),
)

_LLM_TOKEN_TOTAL = Counter(
    "llm_token_total",
    "Total LLM tokens consumed by provider.",
    labelnames=("provider",),
)

_INCIDENT_MTTR_SECONDS = Histogram(
    "incident_mttr_seconds",
    "Mean time to resolve for incidents marked as resolved.",
    buckets=(60, 300, 900, 1800, 3600, 7200, 21600, 43200, 86400),
)


def observe_agent_run_duration(seconds: float) -> None:
    if seconds >= 0:
        _AGENT_RUN_DURATION_SECONDS.observe(seconds)


def add_llm_tokens(tokens: int, provider: str) -> None:
    if tokens > 0:
        _LLM_TOKEN_TOTAL.labels(provider=provider).inc(tokens)


def observe_incident_mttr(seconds: float) -> None:
    if seconds >= 0:
        _INCIDENT_MTTR_SECONDS.observe(seconds)