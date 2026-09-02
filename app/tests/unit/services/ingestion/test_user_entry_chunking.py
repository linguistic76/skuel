"""UserEntry chunk substrate (canon P3) — the ingest_file wiring.

The USER_ENTRY branch of ``UnifiedIngestionService.ingest_file`` runs the
shared body-chunk step (``_chunk_entity_content``) after a successful entry
persist: a non-private knowledge note passes its effective content (so
:ContentChunk children exist for companion retrieval), everything else passes
``""`` — the explicit clear path that retracts stale chunks on a private- or
pipeline-flip. These tests pin that wiring:

- knowledge + non-private → chunk step gets the note body
- explicit ``content:`` frontmatter wins over the body (even when falsy)
- private / non-knowledge pipeline (REFERENCE) → chunk step gets "" (clear path)
- a chunk-step failure (returns False) never fails the file
- the result dict's ``chunks_generated`` reflects the real outcome

The chunk step itself (empty-body clear, CORE-tier gating, adapter-less noop)
is covered by ``test_post_persist_embedding.py``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry import UserEntry
from core.services.ingestion.unified_ingestion_service import UnifiedIngestionService
from core.services.user_entry.audience_resolver import ShareOutcome


def _entry(pipeline: Pipeline, private: bool = False) -> UserEntry:
    return UserEntry(
        uid="ue_probe",
        title="Probe",
        user_uid="user_1",
        pipeline=pipeline,
        private=private,
    )


def _user_entry_service(entry: UserEntry) -> MagicMock:
    from core.utils.result_simplified import Result

    service = MagicMock()
    resolver = MagicMock()
    resolver.resolve_default_teachers = AsyncMock(return_value=[])
    resolver.validate_references = AsyncMock(return_value=Result.ok(None))
    resolver.validate = MagicMock(return_value=Result.ok(None))
    service.audience_resolver = resolver
    service.create_entry = AsyncMock(return_value=Result.ok((entry, ShareOutcome())))
    return service


def _ingestion_service(entry: UserEntry) -> UnifiedIngestionService:
    svc = UnifiedIngestionService(
        write_backend=MagicMock(),
        bulk_backend=MagicMock(),
        user_entry_service=_user_entry_service(entry),
    )
    svc._chunk_entity_content = AsyncMock(return_value=True)  # type: ignore[method-assign]
    return svc


def _note(tmp_path: Path, frontmatter: str, body: str = "The body of the note.") -> Path:
    note = tmp_path / "vault" / "knowledge" / "probe.md"
    note.parent.mkdir(parents=True)
    note.write_text(f"---\ntype: user_entry\n{frontmatter}\n---\n{body}\n", encoding="utf-8")
    return note


@pytest.mark.asyncio
async def test_knowledge_note_chunks_with_body(tmp_path: Path) -> None:
    svc = _ingestion_service(_entry(Pipeline.KNOWLEDGE))
    note = _note(tmp_path, "pipeline: knowledge\ntitle: Probe")

    result = await svc.ingest_file(note, user_uid="user_1")

    assert result.is_ok, result.expect_error()
    svc._chunk_entity_content.assert_awaited_once()  # type: ignore[attr-defined]
    args = svc._chunk_entity_content.await_args.args  # type: ignore[attr-defined]
    assert args[0] == "ue_probe"
    assert "The body of the note." in args[1]
    assert args[2] == "markdown"
    # Inline body stays load-bearing (/gradebook, journal digest) — the chunk
    # subtree is additive, never a body takeover (Codex P1 #615).
    kwargs = svc._chunk_entity_content.await_args.kwargs  # type: ignore[attr-defined]
    assert kwargs["preserve_entity_body"] is True
    assert result.value["chunks_generated"] is True


@pytest.mark.asyncio
async def test_explicit_content_field_wins_over_body(tmp_path: Path) -> None:
    svc = _ingestion_service(_entry(Pipeline.KNOWLEDGE))
    note = _note(tmp_path, 'pipeline: knowledge\ntitle: Probe\ncontent: "field content"')

    result = await svc.ingest_file(note, user_uid="user_1")

    assert result.is_ok
    body_passed = svc._chunk_entity_content.await_args.args[1]  # type: ignore[attr-defined]
    assert body_passed == "field content"


@pytest.mark.asyncio
async def test_explicit_empty_content_takes_clear_path(tmp_path: Path) -> None:
    # An intentional `content: ""` suppresses body capture — the persisted
    # entry has no content, so the chunk step must clear, not chunk the body.
    svc = _ingestion_service(_entry(Pipeline.KNOWLEDGE))
    note = _note(tmp_path, 'pipeline: knowledge\ntitle: Probe\ncontent: ""')

    result = await svc.ingest_file(note, user_uid="user_1")

    assert result.is_ok
    assert svc._chunk_entity_content.await_args.args[1] == ""  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_private_note_takes_clear_path(tmp_path: Path) -> None:
    svc = _ingestion_service(_entry(Pipeline.KNOWLEDGE, private=True))
    note = _note(tmp_path, "pipeline: knowledge\ntitle: Probe\nprivate: true")

    result = await svc.ingest_file(note, user_uid="user_1")

    assert result.is_ok, result.expect_error()
    # The clear path still runs (retracts stale chunks on a flip-to-private
    # re-sync) but never with the body.
    svc._chunk_entity_content.assert_awaited_once()  # type: ignore[attr-defined]
    assert svc._chunk_entity_content.await_args.args[1] == ""  # type: ignore[attr-defined]
    assert result.value["chunks_generated"] is True  # mock returns True; wiring is what's pinned


@pytest.mark.asyncio
async def test_reference_pipeline_takes_clear_path(tmp_path: Path) -> None:
    svc = _ingestion_service(_entry(Pipeline.REFERENCE))
    note = _note(tmp_path, "pipeline: reference\ntitle: Probe")

    result = await svc.ingest_file(note, user_uid="user_1")

    assert result.is_ok, result.expect_error()
    svc._chunk_entity_content.assert_awaited_once()  # type: ignore[attr-defined]
    assert svc._chunk_entity_content.await_args.args[1] == ""  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_chunk_failure_never_fails_the_file(tmp_path: Path) -> None:
    svc = _ingestion_service(_entry(Pipeline.KNOWLEDGE))
    svc._chunk_entity_content = AsyncMock(return_value=False)  # type: ignore[method-assign]
    note = _note(tmp_path, "pipeline: knowledge\ntitle: Probe")

    result = await svc.ingest_file(note, user_uid="user_1")

    assert result.is_ok
    assert result.value["chunks_generated"] is False


@pytest.mark.asyncio
async def test_chunking_params_resolved_for_user_entry(tmp_path: Path) -> None:
    from core.services.ingestion.config import resolve_chunking_params

    svc = _ingestion_service(_entry(Pipeline.KNOWLEDGE))
    note = _note(tmp_path, "pipeline: knowledge\ntitle: Probe")

    await svc.ingest_file(note, user_uid="user_1")

    params_passed = svc._chunk_entity_content.await_args.args[4]  # type: ignore[attr-defined]
    assert params_passed == resolve_chunking_params(EntityType.USER_ENTRY)
