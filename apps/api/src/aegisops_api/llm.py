from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from tenacity import Retrying, stop_after_attempt, wait_exponential

from .circuit_breaker import get_all_circuit_states, get_circuit  # noqa: F401
from .logging_config import get_logger
from .models import LLMProvider
from .settings import get_settings

logger = get_logger(__name__)


def build_chat_model(
    provider: LLMProvider | None = None, model_name: str | None = None
) -> BaseChatModel:
    settings = get_settings()
    selected_provider = provider or settings.llm_provider
    selected_model = model_name or settings.llm_model

    if selected_provider == "groq":
        return ChatGroq(model=selected_model, temperature=0.1)
    if selected_provider == "openai":
        return ChatOpenAI(model=selected_model, temperature=0.1)
    if selected_provider == "anthropic":
        return ChatAnthropic(model=selected_model, temperature=0.1)

    raise ValueError(f"Unsupported provider: {selected_provider}")


def _invoke_with_retry(model: BaseChatModel, messages: list[BaseMessage], max_attempts: int) -> Any:
    """Invoke ``model`` with exponential-backoff retry, reraise on final failure."""
    for attempt in Retrying(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=0.1, min=0.1, max=2),
    ):
        with attempt:
            return model.invoke(messages)


def _build_fallback_chain(primary: str, fallback_chain: list[str]) -> list[str]:
    return [primary] + [p for p in fallback_chain if p != primary]


def call_with_fallback(
    messages: list[BaseMessage],
    primary_provider: str | None = None,
    model_name: str | None = None,
) -> tuple[Any, str]:
    """Invoke LLM with per-provider retry and circuit-breaker-aware fallback.

    Tries each provider in the configured fallback chain in order.
    Skips providers whose circuit is OPEN.
    Records success/failure on the per-provider circuit after each attempt.
    Logs ``circuit_opened`` when a circuit transitions to OPEN.

    Returns ``(response, used_provider)``.
    Raises ``RuntimeError`` when every provider in the chain is exhausted.
    """
    settings = get_settings()
    primary = primary_provider or settings.llm_provider
    chain = _build_fallback_chain(primary, list(settings.llm_fallback_chain))
    last_exc: Exception | None = None

    for provider in chain:
        circuit = get_circuit(
            provider,
            failure_threshold=settings.llm_circuit_failure_threshold,
            recovery_seconds=settings.llm_circuit_recovery_seconds,
        )
        if not circuit.is_available():
            logger.warning("provider_circuit_open_skip", provider=provider)
            continue

        model = build_chat_model(provider, model_name)
        try:
            response = _invoke_with_retry(model, messages, settings.llm_circuit_retry_attempts)
            circuit.record_success()
            return response, provider
        except Exception as exc:
            circuit.record_failure()
            if not circuit.is_available():
                logger.warning(
                    "circuit_opened",
                    provider=provider,
                    failure_count=circuit._failure_count,
                    reason=str(exc),
                )
            last_exc = exc
            if provider != chain[-1]:
                logger.info("llm_provider_fallback", from_provider=provider, reason=str(exc))

    raise RuntimeError(
        f"All LLM providers exhausted after circuit-breaker checks: {chain}"
    ) from last_exc


@lru_cache(maxsize=8)
def get_chat_model(
    provider: LLMProvider | None = None, model_name: str | None = None
) -> BaseChatModel:
    """Return a cached model instance.  Use ``call_with_fallback`` for circuit-aware invocation."""
    return build_chat_model(provider=provider, model_name=model_name)
