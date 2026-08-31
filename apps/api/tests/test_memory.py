"""Tests for the agent memory / pgvector context store (Issue #13).

The memory module is feature-flagged behind ``AIOPS_MEMORY_ENABLED``.  These
tests cover:

- deterministic dummy embedding generation
- OpenAI-backed embedding fallback on error
- prompt-formatting of retrieval results
- no-op behavior of ``store_incident_embedding`` and ``find_similar_incidents``
  when memory is disabled
- ``run_incident_workflow`` still accepts and threads through
  ``similar_incidents`` context into the assess-node prompt

Tests never touch the ``incident_embeddings`` table directly, so they run on a
Postgres without the pgvector extension installed.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_settings(**overrides) -> MagicMock:
    m = MagicMock()
    m.memory_enabled = False
    m.memory_embedding_model = "text-embedding-3-small"
    m.memory_embedding_dim = 8  # small dim for fast tests
    m.memory_top_k = 3
    m.openai_api_key = None
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


# ---------------------------------------------------------------------------
# generate_embedding
# ---------------------------------------------------------------------------


def test_generate_embedding_dummy_is_deterministic() -> None:
    from aegisops_api.memory import generate_embedding

    with patch("aegisops_api.memory.get_settings", return_value=_mock_settings()):
        a = generate_embedding("payments service latency spike")
        b = generate_embedding("payments service latency spike")
        c = generate_embedding("different text")

    assert len(a) == 8
    assert a == b, "dummy embedding must be stable for identical input"
    assert a != c, "different text must yield different embedding"
    assert all(-1.0 <= x < 1.0 for x in a)


def test_generate_embedding_uses_openai_when_configured() -> None:
    from aegisops_api.memory import generate_embedding

    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.1] * 8)]
    )
    with patch(
        "aegisops_api.memory.get_settings",
        return_value=_mock_settings(openai_api_key="sk-test"),
    ), patch("openai.OpenAI", return_value=mock_client):
        result = generate_embedding("query")

    assert result == [0.1] * 8
    mock_client.embeddings.create.assert_called_once()


def test_generate_embedding_falls_back_when_openai_errors() -> None:
    from aegisops_api.memory import generate_embedding

    with patch(
        "aegisops_api.memory.get_settings",
        return_value=_mock_settings(openai_api_key="sk-test"),
    ), patch("openai.OpenAI", side_effect=RuntimeError("network down")):
        result = generate_embedding("query")

    # Falls back to deterministic dummy vector
    assert len(result) == 8


# ---------------------------------------------------------------------------
# format_similar_incidents_for_prompt
# ---------------------------------------------------------------------------


def test_format_similar_incidents_empty() -> None:
    from aegisops_api.memory import format_similar_incidents_for_prompt

    assert format_similar_incidents_for_prompt([]) == ""


def test_format_similar_incidents_renders_all_entries() -> None:
    from aegisops_api.memory import SimilarIncident, format_similar_incidents_for_prompt

    items = [
        SimilarIncident(incident_id="INC-1", service="payments", summary="p95 spike", distance=0.12),
        SimilarIncident(incident_id="INC-2", service="payments", summary="db timeout", distance=0.24),
    ]
    result = format_similar_incidents_for_prompt(items)

    assert "Similar past incidents" in result
    assert "INC-1" in result
    assert "INC-2" in result
    assert "0.120" in result
    assert "0.240" in result


# ---------------------------------------------------------------------------
# store_incident_embedding — no-op when disabled
# ---------------------------------------------------------------------------


def test_store_incident_embedding_noop_when_disabled() -> None:
    from aegisops_api.memory import store_incident_embedding

    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def _run() -> None:
        with patch(
            "aegisops_api.memory.get_settings", return_value=_mock_settings(memory_enabled=False)
        ):
            await store_incident_embedding(
                db, incident_id="INC-1", service="payments", summary="Test"
            )

    asyncio.run(_run())
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_store_incident_embedding_swallows_db_errors() -> None:
    from aegisops_api.memory import store_incident_embedding

    db = MagicMock()
    db.add = MagicMock(side_effect=RuntimeError("no pgvector extension"))
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    async def _run() -> None:
        with patch(
            "aegisops_api.memory.get_settings", return_value=_mock_settings(memory_enabled=True)
        ):
            await store_incident_embedding(
                db, incident_id="INC-1", service="payments", summary="Test"
            )

    # Must not raise — memory failures are logged & swallowed
    asyncio.run(_run())
    db.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# find_similar_incidents — no-op when disabled
# ---------------------------------------------------------------------------


def test_find_similar_incidents_returns_empty_when_disabled() -> None:
    from aegisops_api.memory import find_similar_incidents

    db = MagicMock()
    db.execute = AsyncMock()

    async def _run():
        with patch(
            "aegisops_api.memory.get_settings",
            return_value=_mock_settings(memory_enabled=False),
        ):
            return await find_similar_incidents(db, query="payments spike", service="payments")

    result = asyncio.run(_run())
    assert result == []
    db.execute.assert_not_awaited()


def test_find_similar_incidents_returns_empty_on_error() -> None:
    from aegisops_api.memory import find_similar_incidents

    db = MagicMock()
    db.execute = AsyncMock(side_effect=RuntimeError("no pgvector"))

    async def _run():
        with patch(
            "aegisops_api.memory.get_settings", return_value=_mock_settings(memory_enabled=True)
        ):
            return await find_similar_incidents(db, query="q", service="s")

    result = asyncio.run(_run())
    assert result == []


# ---------------------------------------------------------------------------
# Prompt injection into assess node
# ---------------------------------------------------------------------------


def test_similar_incidents_context_reaches_llm_prompt() -> None:
    """The retrieved-incident block should be part of the HumanMessage content."""
    from aegisops_api import agents

    captured: dict[str, object] = {}

    def _fake_call_with_fallback(messages, provider, model_name):
        captured["messages"] = messages
        response = MagicMock()
        response.content = "assess output"
        response.response_metadata = {"token_usage": {"total_tokens": 42}}
        return response, provider

    with patch.object(agents, "call_with_fallback", side_effect=_fake_call_with_fallback):
        result = agents._generate_role_output(
            role="assess",
            system_prompt="You are the triage agent.",
            state={
                "incident_id": "INC-99",
                "title": "Payments 500s",
                "service": "payments",
                "severity": "high",
                "summary": "Elevated error rate",
                "owner": "sre",
                "similar_incidents": (
                    "Similar past incidents on this service:\n"
                    "  1. [INC-42] Deploy rollback needed (distance=0.100)"
                ),
            },
            provider="groq",
            model_name="llama-3.1-8b-instant",
        )

    assert result == "assess output"
    messages = captured["messages"]
    human = messages[1]
    assert "INC-42" in human.content
    assert "Similar past incidents" in human.content


def test_no_similar_incidents_context_omits_block() -> None:
    """When similar_incidents is empty the prompt has no retrieval block."""
    from aegisops_api import agents

    captured: dict[str, object] = {}

    def _fake_call_with_fallback(messages, provider, model_name):
        captured["messages"] = messages
        response = MagicMock()
        response.content = "assess output"
        response.response_metadata = {}
        return response, provider

    with patch.object(agents, "call_with_fallback", side_effect=_fake_call_with_fallback):
        agents._generate_role_output(
            role="assess",
            system_prompt="triage",
            state={
                "incident_id": "INC-99",
                "title": "T",
                "service": "s",
                "severity": "high",
                "summary": "sum",
                "owner": "o",
            },
            provider="groq",
            model_name=None,
        )

    human = captured["messages"][1]
    assert "Similar past incidents" not in human.content
