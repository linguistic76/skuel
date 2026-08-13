"""Path-keyed identity for uid-less vault UserEntries — the ingest_file wiring.

Both ingest doors converge on ``UnifiedIngestionService.ingest_file``'s
USER_ENTRY branch, which resolves the tracker's prior ``path → uid`` row and
passes it down so a uid-less knowledge note upserts in place instead of
minting a fresh random uid every sync (which orphaned the old node — 276 stale
copies measured 2026-07-12). These tests pin that wiring at the door and the
private-flip retraction that rides on the now-stable identity.

Contract: docs/roadmap/done/uidless-vault-entry-identity-upsert.md
Pure gating of ``build_user_entry_request`` lives in
``tests/unit/services/user_entry/test_user_entry_ingestion.py``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry import UserEntry
from core.services.ingestion.unified_ingestion_service import UnifiedIngestionService
from core.services.user_entry.audience_resolver import ShareOutcome
from core.utils.result_simplified import Result


def _entry(uid: str, pipeline: Pipeline = Pipeline.KNOWLEDGE, private: bool = False) -> UserEntry:
    return UserEntry(
        uid=uid,
        title="Probe",
        user_uid="user_1",
        pipeline=pipeline,
        private=private,
    )


def _user_entry_service(entry: UserEntry) -> MagicMock:
    service = MagicMock()
    resolver = MagicMock()
    resolver.resolve_default_teachers = AsyncMock(return_value=[])
    resolver.validate_references = AsyncMock(return_value=Result.ok(None))
    resolver.validate = MagicMock(return_value=Result.ok(None))
    service.audience_resolver = resolver
    service.create_entry = AsyncMock(return_value=Result.ok((entry, ShareOutcome())))
    # Default: the tracked prior uid names this very UserEntry (label+ownership
    # guard passes → reuse proceeds). Foreign-uid tests override this.
    service.get_entry = AsyncMock(return_value=Result.ok(entry))
    return service


def _ingestion_backend(prior_uid: str | None) -> MagicMock | None:
    """A tracker backend returning one IngestionMetadata row (or none)."""
    if prior_uid is None:
        backend = MagicMock()
        backend.get_ingestion_metadata = AsyncMock(return_value=Result.ok([]))
        return backend
    backend = MagicMock()
    backend.get_ingestion_metadata = AsyncMock(
        return_value=Result.ok(
            [
                {
                    "file_path": "/vault/knowledge/probe.md",
                    "content_hash": "h",
                    "file_mtime": 1.0,
                    "last_ingested_at": datetime.now(),
                    "entity_uid": prior_uid,
                }
            ]
        )
    )
    return backend


def _ingestion_service(
    entry: UserEntry, prior_uid: str | None
) -> tuple[UnifiedIngestionService, MagicMock]:
    """Return the service plus the UserEntryService mock (create_entry lives on
    the mock — accessing it via ``svc.user_entry_service`` trips union-attr)."""
    service = _user_entry_service(entry)
    svc = UnifiedIngestionService(
        write_backend=MagicMock(),
        bulk_backend=MagicMock(),
        user_entry_service=service,
        ingestion_backend=_ingestion_backend(prior_uid),
    )
    svc._chunk_entity_content = AsyncMock(return_value=True)  # type: ignore[method-assign]
    return svc, service


def _note(tmp_path: Path, frontmatter: str, body: str = "The note body.") -> Path:
    note = tmp_path / "vault" / "knowledge" / "probe.md"
    note.parent.mkdir(parents=True)
    note.write_text(f"---\ntype: user_entry\n{frontmatter}\n---\n{body}\n", encoding="utf-8")
    return note


@pytest.mark.asyncio
async def test_prior_uid_flows_into_create_entry_request(tmp_path: Path) -> None:
    """A uid-less knowledge note adopts the tracker's prior uid → upsert channel."""
    svc, service = _ingestion_service(_entry("ue_prior"), prior_uid="ue_prior")
    note = _note(tmp_path, "pipeline: knowledge\ntitle: Probe")

    result = await svc.ingest_file(note, user_uid="user_1")

    assert result.is_ok, result.expect_error()
    request = service.create_entry.await_args.kwargs["request"]
    assert request.uid == "ue_prior"


@pytest.mark.asyncio
async def test_first_sync_without_tracker_row_mints_fresh(tmp_path: Path) -> None:
    """No prior row → request.uid None so the service mints a fresh random uid."""
    svc, service = _ingestion_service(_entry("ue_new"), prior_uid=None)
    note = _note(tmp_path, "pipeline: knowledge\ntitle: Probe")

    result = await svc.ingest_file(note, user_uid="user_1")

    assert result.is_ok, result.expect_error()
    request = service.create_entry.await_args.kwargs["request"]
    assert request.uid is None


@pytest.mark.asyncio
async def test_foreign_prior_uid_is_not_reused(tmp_path: Path) -> None:
    """A tracker row whose uid names a non-UserEntry (a re-typed file's old Ku
    uid, or an ``edge:`` identity) must NOT be reused — get_entry returns None,
    so the note mints a fresh uid instead of colliding / creating an edge-id
    UserEntry (Codex #616)."""
    svc, service = _ingestion_service(_entry("ue_new"), prior_uid="ku.foo.bar")
    service.get_entry = AsyncMock(return_value=Result.ok(None))  # not a UserEntry
    note = _note(tmp_path, "pipeline: knowledge\ntitle: Probe")

    result = await svc.ingest_file(note, user_uid="user_1")

    assert result.is_ok, result.expect_error()
    request = service.create_entry.await_args.kwargs["request"]
    assert request.uid is None


@pytest.mark.asyncio
async def test_private_flip_reuses_uid_and_clears_chunks(tmp_path: Path) -> None:
    """The crux: flipping a uid-less note ``private: true`` now updates the SAME
    node (prior uid) AND takes the chunk clear path — retraction that was broken
    while the flip minted a new node."""
    svc, service = _ingestion_service(_entry("ue_prior", private=True), prior_uid="ue_prior")
    note = _note(tmp_path, "pipeline: knowledge\ntitle: Probe\nprivate: true")

    result = await svc.ingest_file(note, user_uid="user_1")

    assert result.is_ok, result.expect_error()
    # Same identity: the private flip upserts the prior node, not a fresh one.
    request = service.create_entry.await_args.kwargs["request"]
    assert request.uid == "ue_prior"
    # Retraction: the chunk step runs the clear path ("") on that same uid.
    svc._chunk_entity_content.assert_awaited_once()  # type: ignore[attr-defined]
    chunk_args = svc._chunk_entity_content.await_args.args  # type: ignore[attr-defined]
    assert chunk_args[0] == "ue_prior"
    assert chunk_args[1] == ""


@pytest.mark.asyncio
async def test_no_ingestion_backend_falls_back_to_mint(tmp_path: Path) -> None:
    """Minimal composes / tests without a tracker still work — no prior uid,
    fresh mint (request.uid None)."""
    service = _user_entry_service(_entry("ue_new"))
    svc = UnifiedIngestionService(
        write_backend=MagicMock(),
        bulk_backend=MagicMock(),
        user_entry_service=service,
        ingestion_backend=None,
    )
    svc._chunk_entity_content = AsyncMock(return_value=True)  # type: ignore[method-assign]
    note = _note(tmp_path, "pipeline: knowledge\ntitle: Probe")

    result = await svc.ingest_file(note, user_uid="user_1")

    assert result.is_ok, result.expect_error()
    request = service.create_entry.await_args.kwargs["request"]
    assert request.uid is None
