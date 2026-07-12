"""Unit tests for content-hash-assisted move detection (Phase 1, exact hash).

Contract: /plans/hash-assisted-move-detection.md. A uid-less vault rename must
rewrite the tracker row (old path → new path, SAME uid) so the #616
path-keyed upsert reuses the uid instead of delete+creating; ambiguity and
trivial content fall back to delete+create.

The 1:1 matcher is pure (tested against fixture rows directly); the tracker
pre-pass is tested with a mocked backend + real tmp_path files, mirroring
test_deletion_reconciliation.py.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.ingestion.ingestion_tracker import IngestionTracker
from core.services.ingestion.move_detection import (
    MoveCandidate,
    NewFileCandidate,
    match_moves_by_hash,
)
from core.utils.result_simplified import Result


def _sha(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _row(path: str, uid: str, content: str) -> MoveCandidate:
    return MoveCandidate(file_path=path, entity_uid=uid, content_hash=_sha(content))


def _new(path: str, content: str) -> NewFileCandidate:
    return NewFileCandidate(file_path=path, content_hash=_sha(content))


class TestMatchMovesByHash:
    def test_one_to_one_match_pairs(self) -> None:
        row = _row("/v/old.md", "ue_abc", "note body")
        new_file = _new("/v/new.md", "note body")

        result = match_moves_by_hash([row], [new_file])

        assert len(result.pairs) == 1
        assert result.pairs[0].row == row
        assert result.pairs[0].new_file == new_file
        assert result.ambiguous == ()
        assert result.residual_rows == ()
        assert result.residual_files == ()

    def test_hash_mismatch_no_pair_both_in_residual(self) -> None:
        # Rename + edit in one sync: hashes differ → the Phase 2 case.
        row = _row("/v/old.md", "ue_abc", "original body")
        new_file = _new("/v/new.md", "edited body")

        result = match_moves_by_hash([row], [new_file])

        assert result.pairs == ()
        assert result.residual_rows == (row,)
        assert result.residual_files == (new_file,)

    def test_ambiguous_two_gone_rows_share_hash(self) -> None:
        rows = [
            _row("/v/a.md", "ue_a", "same body"),
            _row("/v/b.md", "ue_b", "same body"),
        ]
        new_file = _new("/v/c.md", "same body")

        result = match_moves_by_hash(rows, [new_file])

        assert result.pairs == ()
        assert len(result.ambiguous) == 1
        assert "2 deleted" in result.ambiguous[0]
        # Ambiguous candidates stay in the residual — Phase 2's similarity +
        # mutual-best matching may still resolve them.
        assert set(result.residual_rows) == set(rows)
        assert result.residual_files == (new_file,)

    def test_ambiguous_two_new_files_share_hash(self) -> None:
        row = _row("/v/a.md", "ue_a", "same body")
        new_files = [_new("/v/b.md", "same body"), _new("/v/c.md", "same body")]

        result = match_moves_by_hash([row], new_files)

        assert result.pairs == ()
        assert len(result.ambiguous) == 1
        assert result.residual_rows == (row,)
        assert set(result.residual_files) == set(new_files)

    def test_multiple_distinct_hashes_pair_independently(self) -> None:
        rows = [
            _row("/v/one.md", "ue_1", "body one"),
            _row("/v/two.md", "ue_2", "body two"),
        ]
        new_files = [
            _new("/v/moved-two.md", "body two"),
            _new("/v/moved-one.md", "body one"),
        ]

        result = match_moves_by_hash(rows, new_files)

        assert len(result.pairs) == 2
        by_uid = {pair.row.entity_uid: pair.new_file.file_path for pair in result.pairs}
        assert by_uid == {"ue_1": "/v/moved-one.md", "ue_2": "/v/moved-two.md"}
        assert result.residual_rows == ()
        assert result.residual_files == ()


def _backend_for_moves(tracked_rows: list[dict], live_uids: list[str]) -> MagicMock:
    """Mocked backend: gone rows come from get_tracked_files_under; the
    metadata lookup answers per-path from the same rows (a canonical-path
    subset query, like the real Cypher)."""
    backend = MagicMock()
    backend.get_tracked_files_under = AsyncMock(return_value=Result.ok(tracked_rows))

    async def _metadata_for(paths: list[str]) -> Result[list[dict]]:
        by_path = {row["file_path"]: row for row in tracked_rows}
        return Result.ok(
            [
                {
                    "file_path": p,
                    "content_hash": by_path[p].get("content_hash", ""),
                    "file_mtime": 0.0,
                    "last_ingested_at": None,
                    "entity_uid": by_path[p]["entity_uid"],
                }
                for p in paths
                if p in by_path
            ]
        )

    backend.get_ingestion_metadata = AsyncMock(side_effect=_metadata_for)
    backend.get_entity_owner_uids = AsyncMock(return_value=Result.ok([]))
    backend.get_live_entity_uids = AsyncMock(
        return_value=Result.ok([{"uid": uid} for uid in live_uids])
    )
    backend.update_ingestion_metadata = AsyncMock(return_value=Result.ok([]))
    backend.delete_ingestion_metadata = AsyncMock(return_value=Result.ok([{"deleted": 1}]))
    return backend


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestDetectAndApplyMoves:
    @pytest.mark.asyncio
    async def test_pure_rename_rewrites_tracker_row(self, tmp_path) -> None:
        # Old path tracked + gone; new path on disk with identical content.
        old_path = tmp_path / "note.md"  # never created (renamed away)
        new_path = tmp_path / "renamed-note.md"
        new_path.write_text("uid-less knowledge note body", encoding="utf-8")
        anchor = tmp_path / "anchor.md"  # keeps the physical-existence valve open
        anchor.write_text("anchor", encoding="utf-8")

        backend = _backend_for_moves(
            [
                {
                    "file_path": str(old_path),
                    "entity_uid": "ue_moved1",
                    "content_hash": _file_hash(new_path),
                },
                {"file_path": str(anchor), "entity_uid": "ue_anchor", "content_hash": "other"},
            ],
            live_uids=["ue_moved1"],
        )
        tracker = IngestionTracker(backend)

        result = await tracker.detect_and_apply_moves(tmp_path, [new_path])

        assert result.is_ok
        assert len(result.value.applied) == 1
        move = result.value.applied[0]
        assert move.entity_uid == "ue_moved1"
        assert move.old_path == str(old_path)
        assert move.new_path == str(new_path.resolve())
        # Row rewritten: new path claims the uid with pending markers (empty
        # hash / mtime 0) so a failed ingest this run still retries next sync.
        upsert = backend.update_ingestion_metadata.await_args.args[0]
        assert upsert == {
            "file_path": str(new_path.resolve()),
            "content_hash": "",
            "file_mtime": 0.0,
            "entity_uid": "ue_moved1",
        }
        backend.delete_ingestion_metadata.assert_awaited_once_with([str(old_path)])

    @pytest.mark.asyncio
    async def test_rename_plus_edit_falls_back_to_delete_create(self, tmp_path) -> None:
        # Hash differs (content edited in the same sync) → no move (Phase 2).
        old_path = tmp_path / "note.md"
        new_path = tmp_path / "renamed-note.md"
        new_path.write_text("EDITED body", encoding="utf-8")
        anchor = tmp_path / "anchor.md"  # keeps the physical-existence valve open
        anchor.write_text("anchor", encoding="utf-8")

        backend = _backend_for_moves(
            [
                {
                    "file_path": str(old_path),
                    "entity_uid": "ue_edited",
                    "content_hash": _sha("original body"),
                },
                {"file_path": str(anchor), "entity_uid": "ue_anchor", "content_hash": "other"},
            ],
            live_uids=["ue_edited"],
        )
        tracker = IngestionTracker(backend)

        result = await tracker.detect_and_apply_moves(tmp_path, [new_path])

        assert result.is_ok
        assert result.value.applied == ()
        backend.update_ingestion_metadata.assert_not_called()
        backend.delete_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_ambiguous_identical_notes_never_matched(self, tmp_path) -> None:
        # Two gone rows share one hash with two new files → all skipped.
        new_a = tmp_path / "moved-a.md"
        new_b = tmp_path / "moved-b.md"
        new_a.write_text("duplicated template", encoding="utf-8")
        new_b.write_text("duplicated template", encoding="utf-8")
        shared = _file_hash(new_a)
        anchor = tmp_path / "anchor.md"  # keeps the physical-existence valve open
        anchor.write_text("anchor", encoding="utf-8")

        backend = _backend_for_moves(
            [
                {"file_path": str(tmp_path / "a.md"), "entity_uid": "ue_a", "content_hash": shared},
                {"file_path": str(tmp_path / "b.md"), "entity_uid": "ue_b", "content_hash": shared},
                {"file_path": str(anchor), "entity_uid": "ue_anchor", "content_hash": "other"},
            ],
            live_uids=["ue_a", "ue_b"],
        )
        tracker = IngestionTracker(backend)

        result = await tracker.detect_and_apply_moves(tmp_path, [new_a, new_b])

        assert result.is_ok
        assert result.value.applied == ()
        backend.update_ingestion_metadata.assert_not_called()
        backend.delete_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_trivial_content_never_matched(self, tmp_path) -> None:
        # Whitespace-only files hash-collide meaninglessly — excluded.
        new_path = tmp_path / "empty-note.md"
        new_path.write_text("   \n\n  ", encoding="utf-8")
        anchor = tmp_path / "anchor.md"
        anchor.write_text("anchor", encoding="utf-8")

        backend = _backend_for_moves(
            [
                {
                    "file_path": str(tmp_path / "old-empty.md"),
                    "entity_uid": "ue_empty",
                    "content_hash": _file_hash(new_path),
                },
                {"file_path": str(anchor), "entity_uid": "ue_anchor", "content_hash": "other"},
            ],
            live_uids=["ue_empty"],
        )
        tracker = IngestionTracker(backend)

        result = await tracker.detect_and_apply_moves(tmp_path, [new_path])

        assert result.is_ok
        assert result.value.applied == ()
        backend.update_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_dead_node_guard_skips_rewrite(self, tmp_path) -> None:
        # A stale row pointing at a hand-deleted node is not a move source.
        new_path = tmp_path / "renamed.md"
        new_path.write_text("body", encoding="utf-8")
        anchor = tmp_path / "anchor.md"
        anchor.write_text("anchor", encoding="utf-8")

        backend = _backend_for_moves(
            [
                {
                    "file_path": str(tmp_path / "old.md"),
                    "entity_uid": "ue_dead",
                    "content_hash": _file_hash(new_path),
                },
                {"file_path": str(anchor), "entity_uid": "ue_anchor", "content_hash": "other"},
            ],
            live_uids=[],  # uid names no live node
        )
        tracker = IngestionTracker(backend)

        result = await tracker.detect_and_apply_moves(tmp_path, [new_path])

        assert result.is_ok
        assert result.value.applied == ()
        backend.update_ingestion_metadata.assert_not_called()
        backend.delete_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_authored_uid_move_already_reclaimed_is_not_a_candidate(self, tmp_path) -> None:
        # Regression guard: an authored-uid rename whose identity is already
        # claimed by the new tracked path (the existing uid-based moved/stale
        # split) is a STALE row, not a delete candidate — the hash pre-pass
        # must not double-handle it.
        new_path = tmp_path / "renamed" / "ku.thing.md"
        new_path.parent.mkdir()
        new_path.write_text("ku body", encoding="utf-8")
        old_path = tmp_path / "ku.thing.md"  # gone

        backend = _backend_for_moves(
            [
                {
                    "file_path": str(old_path),
                    "entity_uid": "ku.thing",
                    "content_hash": _file_hash(new_path),
                },
                {
                    "file_path": str(new_path),
                    "entity_uid": "ku.thing",
                    "content_hash": _file_hash(new_path),
                },
            ],
            live_uids=["ku.thing"],
        )
        tracker = IngestionTracker(backend)

        result = await tracker.detect_and_apply_moves(tmp_path, [new_path])

        assert result.is_ok
        assert result.value.applied == ()
        backend.update_ingestion_metadata.assert_not_called()
        backend.delete_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_whole_folder_rename_still_detects_moves(self, tmp_path) -> None:
        # Codex #617: renaming EVERY tracked note at once makes all old paths
        # vanish — the physical-existence mass-deletion valve reads that as an
        # unmounted vault, but the valves are deletion-only and must not gate
        # move detection. The disambiguating evidence is the new files on
        # disk, which a real unmount cannot produce.
        new_a = tmp_path / "reorg" / "note-a.md"
        new_b = tmp_path / "reorg" / "note-b.md"
        new_a.parent.mkdir()
        new_a.write_text("unique body alpha", encoding="utf-8")
        new_b.write_text("unique body beta", encoding="utf-8")

        backend = _backend_for_moves(
            [
                {
                    "file_path": str(tmp_path / "note-a.md"),
                    "entity_uid": "ue_a",
                    "content_hash": _file_hash(new_a),
                },
                {
                    "file_path": str(tmp_path / "note-b.md"),
                    "entity_uid": "ue_b",
                    "content_hash": _file_hash(new_b),
                },
            ],
            live_uids=["ue_a", "ue_b"],
        )
        tracker = IngestionTracker(backend)

        result = await tracker.detect_and_apply_moves(tmp_path, [new_a, new_b])

        assert result.is_ok
        assert {m.entity_uid for m in result.value.applied} == {"ue_a", "ue_b"}
        assert backend.update_ingestion_metadata.await_count == 2
        assert backend.delete_ingestion_metadata.await_count == 2

    @pytest.mark.asyncio
    async def test_no_new_files_no_moves(self, tmp_path) -> None:
        anchor = tmp_path / "anchor.md"
        anchor.write_text("anchor", encoding="utf-8")
        backend = _backend_for_moves(
            [
                {
                    "file_path": str(tmp_path / "gone.md"),
                    "entity_uid": "ue_gone",
                    "content_hash": _sha("body"),
                },
                {"file_path": str(anchor), "entity_uid": "ue_anchor", "content_hash": "other"},
            ],
            live_uids=["ue_gone"],
        )
        tracker = IngestionTracker(backend)

        # The only file to process is already tracked (not new) → no move.
        result = await tracker.detect_and_apply_moves(tmp_path, [anchor])

        assert result.is_ok
        assert result.value.applied == ()
        backend.update_ingestion_metadata.assert_not_called()
