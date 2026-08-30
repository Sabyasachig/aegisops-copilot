from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"       # Normal operation — calls pass through.
    OPEN = "open"           # Blocking — too many recent failures.
    HALF_OPEN = "half_open" # Recovery probe — one call allowed through.


class CircuitBreaker:
    """Per-provider circuit breaker with configurable failure threshold and recovery window."""

    def __init__(
        self,
        provider: str,
        failure_threshold: int = 3,
        recovery_seconds: int = 30,
    ) -> None:
        self.provider = provider
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: datetime | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if (
                self._state == CircuitState.OPEN
                and self._last_failure_time is not None
                and datetime.now(UTC) - self._last_failure_time
                >= timedelta(seconds=self.recovery_seconds)
            ):
                self._state = CircuitState.HALF_OPEN
            return self._state

    def is_available(self) -> bool:
        return self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now(UTC)
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN


# ── Module-level registry ──────────────────────────────────────────────────────

_registry: dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()


def get_circuit(
    provider: str,
    failure_threshold: int = 3,
    recovery_seconds: int = 30,
) -> CircuitBreaker:
    """Return the singleton ``CircuitBreaker`` for ``provider``, creating it on first call."""
    with _registry_lock:
        if provider not in _registry:
            _registry[provider] = CircuitBreaker(
                provider,
                failure_threshold=failure_threshold,
                recovery_seconds=recovery_seconds,
            )
        return _registry[provider]


def get_all_circuit_states() -> dict[str, str]:
    """Return a ``{provider: state_value}`` snapshot of all tracked circuits."""
    with _registry_lock:
        return {p: cb.state.value for p, cb in _registry.items()}


def reset_all() -> None:
    """Clear the entire circuit registry.  **For tests only.**"""
    with _registry_lock:
        _registry.clear()
