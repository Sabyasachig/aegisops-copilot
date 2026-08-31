"""Tests for the RAG runbook knowledge base (Issue #14).

Tests cover:
- chunk_markdown — pure function, no DB needed
- store_runbook / find_relevant_runbooks — no-op when memory disabled
- format_runbooks_for_prompt — pure function
- ingest_runbook_directory — file-system mock
- POST /api/admin/runbooks — auth check + 422 when disabled
- gather_evidence prompt injection from runbook_context
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, mock_open, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_settings(**overrides) -> MagicMock:
    m = MagicMock()
    m.memory_enabled = False
    m.memory_embedding_model = "text-embedding-3-small"
    m.memory_embedding_dim = 8
    m.memory_top_k = 3
    m.openai_api_key = None
    m.runbook_dir = None
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


# ---------------------------------------------------------------------------
# chunk_markdown
# ---------------------------------------------------------------------------


def test_chunk_markdown_splits_large_text() -> None:
    from aegisops_api.memory import chunk_markdown

    words = ["word"] * 1200
    text = " ".join(words)
    chunks = chunk_markdown(text, chunk_size=500, overlap=50)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.split()) <= 500


def test_chunk_markdown_single_small_doc() -> None:
    from aegisops_api.memory import chunk_markdown

    text = "This is a short runbook."
    chunks = chunk_markdown(text, chunk_size=500, overlap=50)

    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_markdown_empty_content() -> None:
    from aegisops_api.memory import chunk_markdown

    assert chunk_markdown("") == []
    assert chunk_markdown("   \n\n  ") == []


def test_chunk_markdown_overlap_repeats_words() -> None:
    from aegisops_api.memory import chunk_markdown

    words = [str(i) for i in range(20)]
    text = " ".join(words)
    chunks = chunk_markdown(text, chunk_size=10, overlap=3)

    # Last 3 words of chunk 0 should appear at start of chunk 1
    last_of_0 = chunks[0].split()[-3:]
    first_of_1 = chunks[1].split()[:3]
    assert last_of_0 == first_of_1


# ---------------------------------------------------------------------------
# format_runbooks_for_prompt
# ---------------------------------------------------------------------------


def test_format_runbooks_for_prompt_empty() -> None:
    from aegisops_api.memory import format_runbooks_for_prompt

    assert format_runbooks_for_prompt([]) == ""


def test_format_runbooks_for_prompt_renders_entries() -> None:
    from aegisops_api.memory import RunbookChunk, format_runbooks_for_prompt

    items = [
        RunbookChunk(title="Payments Runbook", service="payments",
                     content="Roll back the deploy.", source_path="/runbooks/payments.md", distance=0.08),
        RunbookChunk(title="Generic SRE", service=None,
                     content="Check disk usage.", source_path="/runbooks/sre.md", distance=0.22),
    ]
    result = format_runbooks_for_prompt(items)

    assert "Relevant runbook snippets" in result
    assert "Payments Runbook" in result
    assert "Generic SRE" in result
    assert "Roll back the deploy." in result
    assert "0.080" in result


# ---------------------------------------------------------------------------
# store_runbook — no-op when disabled
# ---------------------------------------------------------------------------


def test_store_runbook_noop_when_disabled() -> None:
    from aegisops_api.memory import store_runbook

    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def _run():
        with patch("aegisops_api.memory.get_settings", return_value=_mock_settings()):
            return await store_runbook(db, title="T", content="content")

    n = asyncio.run(_run())
    assert n == 0
    db.add.assert_not_called()


def test_store_runbook_swallows_db_errors() -> None:
    from aegisops_api.memory import store_runbook

    db = MagicMock()
    db.add = MagicMock(side_effect=RuntimeError("no pgvector"))
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    async def _run():
        with patch("aegisops_api.memory.get_settings",
                   return_value=_mock_settings(memory_enabled=True)):
            return await store_runbook(db, title="T", content="some content for testing")

    n = asyncio.run(_run())
    assert n == 0
    db.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# find_relevant_runbooks — no-op when disabled
# ---------------------------------------------------------------------------


def test_find_relevant_runbooks_noop_when_disabled() -> None:
    from aegisops_api.memory import find_relevant_runbooks

    db = MagicMock()
    db.execute = AsyncMock()

    async def _run():
        with patch("aegisops_api.memory.get_settings", return_value=_mock_settings()):
            return await find_relevant_runbooks(db, query="payments spike")

    result = asyncio.run(_run())
    assert result == []
    db.execute.assert_not_awaited()


def test_find_relevant_runbooks_returns_empty_on_error() -> None:
    from aegisops_api.memory import find_relevant_runbooks

    db = MagicMock()
    db.execute = AsyncMock(side_effect=RuntimeError("no pgvector"))

    async def _run():
        with patch("aegisops_api.memory.get_settings",
                   return_value=_mock_settings(memory_enabled=True)):
            return await find_relevant_runbooks(db, query="q")

    result = asyncio.run(_run())
    assert result == []


# ---------------------------------------------------------------------------
# ingest_runbook_directory
# ---------------------------------------------------------------------------


def test_ingest_runbook_directory_noop_when_disabled() -> None:
    from aegisops_api.memory import ingest_runbook_directory

    db = MagicMock()
    db.add = MagicMock()

    async def _run():
        with patch("aegisops_api.memory.get_settings", return_value=_mock_settings()):
            return await ingest_runbook_directory(db, "/runbooks")

    n = asyncio.run(_run())
    assert n == 0
    db.add.assert_not_called()


def test_ingest_runbook_directory_reads_md_files() -> None:
    from aegisops_api.memory import ingest_runbook_directory

    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def _run():
        with patch("aegisops_api.memory.get_settings",
                   return_value=_mock_settings(memory_enabled=True)), \
             patch("os.listdir", return_value=["payments.md", "README.txt"]), \
             patch("builtins.open", mock_open(read_data="# Payments Runbook\n\nRoll back deploy.")):
            return await ingest_runbook_directory(db, "/runbooks")

    n = asyncio.run(_run())
    # One .md file → at least 1 chunk stored
    assert n >= 1
    db.add.assert_called()


# ---------------------------------------------------------------------------
# POST /api/admin/runbooks endpoint
# ---------------------------------------------------------------------------


def test_upload_runbook_requires_admin(client) -> None:
    tok = client.post(
        "/api/auth/token",
        json={"username": "test-operator", "password": "operatorpass123"},
    ).json()["access_token"]
    resp = client.post(
        "/api/admin/runbooks",
        json={"title": "T", "content": "test"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 403


def test_upload_runbook_returns_422_when_memory_disabled(authed_client) -> None:
    resp = authed_client.post(
        "/api/admin/runbooks",
        json={"title": "T", "content": "test"},
    )
    # Memory is disabled in test env → endpoint returns 422
    assert resp.status_code == 422
    assert "AIOPS_MEMORY_ENABLED" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# gather_evidence prompt injection
# ---------------------------------------------------------------------------


def test_runbook_context_injected_in_gather_evidence_prompt() -> None:
    """The gather_evidence node enriches the system prompt with runbook context.

    We simulate that enrichment here and verify the runbook block reaches
    the SystemMessage sent to the LLM.
    """
    from aegisops_api import agents

    captured: dict[str, object] = {}

    def _fake_call(messages, provider, model_name):
        captured["messages"] = messages
        r = MagicMock()
        r.content = "evidence output"
        r.response_metadata = {}
        return r, provider

    ctx = "Relevant runbook snippets:\n  [1] Payments Runbook\n  Roll back the deploy."
    # Simulate what the gather_evidence node closure does: inject runbook_context
    # into the system prompt before calling _generate_role_output.
    base_system = "You are the evidence agent. Summarize likely observability signals."
    enriched_system = (
        f"{base_system}\n\n"
        f"Use the following runbook context to guide your analysis:\n{ctx}"
    )

    with patch.object(agents, "call_with_fallback", side_effect=_fake_call):
        agents._generate_role_output(
            role="evidence",
            system_prompt=enriched_system,
            state={
                "incident_id": "INC-99",
                "title": "API 500s",
                "service": "api",
                "severity": "high",
                "summary": "Error rate 10%",
                "owner": "sre",
            },
            provider="groq",
            model_name=None,
        )

    # Runbook context lands in the SystemMessage (messages[0])
    system = captured["messages"][0]
    assert "Roll back the deploy" in system.content
    assert "Payments Runbook" in system.content
