from __future__ import annotations

from aegisops_api.tracing import get_current_trace_id


class _DummyContext:
    def __init__(self, trace_id: int, is_valid: bool) -> None:
        self.trace_id = trace_id
        self.is_valid = is_valid


class _DummySpan:
    def __init__(self, context: _DummyContext) -> None:
        self._context = context

    def get_span_context(self) -> _DummyContext:
        return self._context


def test_get_current_trace_id_none_when_invalid(monkeypatch) -> None:
    def _fake_current_span():
        return _DummySpan(_DummyContext(trace_id=0, is_valid=False))

    monkeypatch.setattr("aegisops_api.tracing.trace.get_current_span", _fake_current_span)
    assert get_current_trace_id() is None


def test_get_current_trace_id_formats_32_char_hex(monkeypatch) -> None:
    expected = "0000000000000000000000000000002a"

    def _fake_current_span():
        return _DummySpan(_DummyContext(trace_id=42, is_valid=True))

    monkeypatch.setattr("aegisops_api.tracing.trace.get_current_span", _fake_current_span)
    assert get_current_trace_id() == expected
