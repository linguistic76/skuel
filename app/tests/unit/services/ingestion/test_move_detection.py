"""Unit tests for content-based move detection (exact hash + similarity).

Contract: docs/roadmap/done/hash-assisted-move-detection.md. A uid-less vault rename must
rewrite the tracker row (old path → new path, SAME uid) so the #616
path-keyed upsert reuses the uid instead of delete+creating. Phase 1's exact
hash catches pure renames; Phase 2's mutual-best lexical similarity over the
residual catches rename + edit in one sync. Ambiguity, trivial content, and
sub-threshold similarity fall back to delete+create — a wrong merge fuses two
notes' identities, so the missed move is the safe failure.

The matchers and scorer are pure (tested against fixture rows directly); the
tracker pre-pass is tested with a mocked backend + real tmp_path files,
mirroring test_deletion_reconciliation.py.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.ingestion.ingestion_tracker import IngestionTracker
from core.services.ingestion.move_detection import (
    SIMILARITY_MOVE_THRESHOLD,
    MoveCandidate,
    NewFileCandidate,
    match_moves_by_hash,
    match_moves_by_similarity,
    similarity_score,
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


_LONG_BODY = (
    "The Feynman technique asks you to explain a concept in plain language "
    "as if teaching a child, then identify the gaps in your explanation, "
    "return to the source material to fill them, and finally simplify again "
    "until the explanation flows without jargon or hand-waving."
)


class TestSimilarityScore:
    def test_identical_text_scores_one(self) -> None:
        assert similarity_score(_LONG_BODY, _LONG_BODY) == 1.0

    def test_whitespace_and_case_normalized(self) -> None:
        reflowed = _LONG_BODY.upper().replace(". ", ".\n\n").replace(" ", "  ")
        assert similarity_score(_LONG_BODY, reflowed) == 1.0

    def test_disjoint_text_scores_zero(self) -> None:
        unrelated = (
            "Sourdough starters need equal weights of flour and water once "
            "the culture peaks and begins to fall each feeding cycle."
        )
        assert similarity_score(_LONG_BODY, unrelated) == 0.0

    def test_empty_side_scores_zero(self) -> None:
        assert similarity_score("", _LONG_BODY) == 0.0
        assert similarity_score(_LONG_BODY, "   \n  ") == 0.0

    def test_small_edit_scores_high(self) -> None:
        edited = _LONG_BODY + " Added one trailing sentence after the rename."
        assert SIMILARITY_MOVE_THRESHOLD <= similarity_score(_LONG_BODY, edited) < 1.0

    def test_rewrite_scores_low(self) -> None:
        rewrite = (
            "Spaced repetition schedules reviews at increasing intervals so "
            "that each recall lands just before the memory would decay, "
            "which strengthens retention far more than massed practice."
        )
        assert similarity_score(_LONG_BODY, rewrite) < SIMILARITY_MOVE_THRESHOLD

    def test_sub_floor_bodies_abstain(self) -> None:
        # Codex #618 round 5: a tiny body carries no identity evidence — two
        # unrelated notes whose stored body is just "done" would score 1.0
        # and FUSE. Below the token floor the scorer abstains entirely.
        assert similarity_score("done", "done") == 0.0
        nine_tokens = "one two three four five six seven eight nine"
        assert similarity_score(nine_tokens, nine_tokens) == 0.0

    def test_floor_boundary_ten_tokens_scores(self) -> None:
        ten_tokens = "one two three four five six seven eight nine ten"
        assert similarity_score(ten_tokens, ten_tokens) == 1.0


class TestMatchMovesBySimilarity:
    def test_edit_above_threshold_pairs_with_score(self) -> None:
        row = MoveCandidate(file_path="/v/old.md", entity_uid="ue_a", content_hash="h1")
        new_file = NewFileCandidate(file_path="/v/new.md", content_hash="h2")
        edited = _LONG_BODY + " Small addition."

        result = match_moves_by_similarity([(row, _LONG_BODY)], [(new_file, edited)])

        assert len(result.pairs) == 1
        pair = result.pairs[0]
        assert pair.row == row
        assert pair.new_file == new_file
        assert pair.score >= SIMILARITY_MOVE_THRESHOLD
        assert result.ambiguous == ()

    def test_rewrite_below_threshold_not_merged(self) -> None:
        # False-positive guard: one note deleted + one unrelated note added
        # in the same sync must NOT fuse identities.
        row = MoveCandidate(file_path="/v/old.md", entity_uid="ue_a", content_hash="h1")
        new_file = NewFileCandidate(file_path="/v/new.md", content_hash="h2")
        unrelated = (
            "Grocery run for the week: oats, lentils, spinach, olive oil, "
            "and whatever citrus looks fresh at the market stand."
        )

        result = match_moves_by_similarity([(row, _LONG_BODY)], [(new_file, unrelated)])

        assert result.pairs == ()

    def test_threshold_boundary_inclusive(self) -> None:
        row = MoveCandidate(file_path="/v/old.md", entity_uid="ue_a", content_hash="h1")
        new_file = NewFileCandidate(file_path="/v/new.md", content_hash="h2")
        edited = _LONG_BODY + " Added one trailing sentence after the rename."
        score = similarity_score(_LONG_BODY, edited)

        at_threshold = match_moves_by_similarity(
            [(row, _LONG_BODY)], [(new_file, edited)], threshold=score
        )
        above_threshold = match_moves_by_similarity(
            [(row, _LONG_BODY)], [(new_file, edited)], threshold=score + 1e-9
        )

        assert len(at_threshold.pairs) == 1  # >= is inclusive
        assert above_threshold.pairs == ()

    def test_mutual_best_resolves_competing_candidates(self) -> None:
        # G1 scores against both N1 (identical) and N2 (edited): G1's unique
        # best is N1, so only G1↔N1 pairs even though (G1, N2) also clears
        # the threshold — N2's best row is G1, but the agreement isn't mutual.
        row = MoveCandidate(file_path="/v/g1.md", entity_uid="ue_g1", content_hash="h1")
        n1 = NewFileCandidate(file_path="/v/n1.md", content_hash="h2")
        n2 = NewFileCandidate(file_path="/v/n2.md", content_hash="h3")
        edited = _LONG_BODY + " Small addition."
        assert similarity_score(_LONG_BODY, edited) >= SIMILARITY_MOVE_THRESHOLD

        result = match_moves_by_similarity([(row, _LONG_BODY)], [(n1, _LONG_BODY), (n2, edited)])

        assert len(result.pairs) == 1
        assert result.pairs[0].new_file == n1
        assert result.pairs[0].score == 1.0

    def test_tied_top_score_abstains_as_ambiguous(self) -> None:
        # Two new files with identical content: the row's top score is tied,
        # so no unique best exists — abstain rather than guess.
        row = MoveCandidate(file_path="/v/old.md", entity_uid="ue_a", content_hash="h1")
        n1 = NewFileCandidate(file_path="/v/twin1.md", content_hash="h2")
        n2 = NewFileCandidate(file_path="/v/twin2.md", content_hash="h3")

        result = match_moves_by_similarity(
            [(row, _LONG_BODY)], [(n1, _LONG_BODY), (n2, _LONG_BODY)]
        )

        assert result.pairs == ()
        assert any("tied" in message for message in result.ambiguous)

    def test_two_pairs_resolve_independently(self) -> None:
        other_body = (
            "Deliberate practice targets the edge of current ability with "
            "immediate feedback, full concentration, and repetition designed "
            "around specific weaknesses rather than comfortable strengths."
        )
        row_a = MoveCandidate(file_path="/v/a.md", entity_uid="ue_a", content_hash="h1")
        row_b = MoveCandidate(file_path="/v/b.md", entity_uid="ue_b", content_hash="h2")
        new_a = NewFileCandidate(file_path="/v/moved-a.md", content_hash="h3")
        new_b = NewFileCandidate(file_path="/v/moved-b.md", content_hash="h4")

        result = match_moves_by_similarity(
            [(row_a, _LONG_BODY), (row_b, other_body)],
            [
                (new_b, other_body + " Tweaked ending sentence here."),
                (new_a, _LONG_BODY + " Small addition."),
            ],
        )

        assert {(p.row.entity_uid, p.new_file.file_path) for p in result.pairs} == {
            ("ue_a", "/v/moved-a.md"),
            ("ue_b", "/v/moved-b.md"),
        }


def _backend_for_moves(
    tracked_rows: list[dict],
    live_uids: list[str],
    entity_contents: dict[str, str] | None = None,
) -> MagicMock:
    """Mocked backend: gone rows come from get_tracked_files_under; the
    metadata lookup answers per-path from the same rows (a canonical-path
    subset query, like the real Cypher); get_entity_contents answers per-uid
    from ``entity_contents`` (only live nodes with non-empty content yield a
    row, like the real Cypher)."""
    backend = MagicMock()
    backend.get_tracked_files_under = AsyncMock(return_value=Result.ok(tracked_rows))

    contents = entity_contents or {}

    async def _contents_for(uids: list[str]) -> Result[list[dict]]:
        return Result.ok(
            [{"uid": uid, "content": contents[uid]} for uid in uids if uid in contents]
        )

    backend.get_entity_contents = AsyncMock(side_effect=_contents_for)

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
            "authored_edges": [],
        }
        backend.delete_ingestion_metadata.assert_awaited_once_with([str(old_path)])

    @pytest.mark.asyncio
    async def test_rename_plus_edit_falls_back_to_delete_create(self, tmp_path) -> None:
        # Hash differs (content edited in the same sync) AND the gone node has
        # no stored content to similarity-match against → no move. A node
        # with empty/None content can never be a similarity move source.
        old_path = tmp_path / "note.md"
        new_path = tmp_path / "renamed-note.md"
        new_path.write_text("EDITED body", encoding="utf-8")
        anchor = tmp_path / "anchor.md"  # keeps the physical-existence valve open
        anchor.write_text("anchor", encoding="utf-8")

        backend = _backend_for_moves(
            [
                {
                    "file_path": str(old_path),
                    "entity_uid": "ue_ee90ef12",
                    "content_hash": _sha("original body"),
                },
                {"file_path": str(anchor), "entity_uid": "ue_anchor", "content_hash": "other"},
            ],
            live_uids=["ue_ee90ef12"],
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
    async def test_rename_plus_edit_similarity_preserves_identity(self, tmp_path) -> None:
        # The Phase 2 case: rename + edit in ONE sync. Hash no longer
        # matches, but the gone node's stored body is ≥ threshold similar to
        # the new file's resolved content → tracker row rewritten under the
        # same uid, with the score carried on the AppliedMove.
        old_path = tmp_path / "feynman-technique.md"  # renamed away
        new_path = tmp_path / "feynman-method.md"
        edited_body = _LONG_BODY + " Added one trailing sentence after the rename."
        new_path.write_text(
            f"---\ntype: user_entry\ntitle: Feynman method\ntags: [learning]\n---\n{edited_body}",
            encoding="utf-8",
        )

        backend = _backend_for_moves(
            [
                {
                    "file_path": str(old_path),
                    "entity_uid": "ue_ab12cd34",
                    "content_hash": _sha("frozen pre-rename file bytes"),
                }
            ],
            live_uids=["ue_ab12cd34"],
            entity_contents={"ue_ab12cd34": _LONG_BODY},
        )
        tracker = IngestionTracker(backend)

        result = await tracker.detect_and_apply_moves(tmp_path, [new_path])

        assert result.is_ok
        assert len(result.value.applied) == 1
        move = result.value.applied[0]
        assert (
            move.entity_uid == "ue_ab12cd34"
        )  # minted uid-less shape — the only sanctioned source
        assert move.old_path == str(old_path)
        assert move.new_path == str(new_path.resolve())
        assert move.similarity is not None
        assert SIMILARITY_MOVE_THRESHOLD <= move.similarity < 1.0
        # Same rewrite rails as exact moves: pending markers so a failed
        # ingest this run still retries next sync.
        upsert = backend.update_ingestion_metadata.await_args.args[0]
        assert upsert == {
            "file_path": str(new_path.resolve()),
            "content_hash": "",
            "file_mtime": 0.0,
            "entity_uid": "ue_ab12cd34",
            "authored_edges": [],
        }
        backend.delete_ingestion_metadata.assert_awaited_once_with([str(old_path)])

    @pytest.mark.asyncio
    async def test_genuinely_replaced_file_not_merged(self, tmp_path) -> None:
        # False-positive guard: delete note A + add unrelated note B in the
        # same sync — low similarity must NOT fuse their identities.
        old_path = tmp_path / "feynman-technique.md"
        new_path = tmp_path / "grocery-list.md"
        new_path.write_text(
            "---\ntype: user_entry\n---\n"
            "Grocery run for the week: oats, lentils, spinach, olive oil, "
            "and whatever citrus looks fresh at the market stand.",
            encoding="utf-8",
        )

        backend = _backend_for_moves(
            [
                {
                    "file_path": str(old_path),
                    "entity_uid": "ue_ab12cd34",
                    "content_hash": _sha("frozen pre-rename file bytes"),
                }
            ],
            live_uids=["ue_ab12cd34"],
            entity_contents={"ue_ab12cd34": _LONG_BODY},
        )
        tracker = IngestionTracker(backend)

        result = await tracker.detect_and_apply_moves(tmp_path, [new_path])

        assert result.is_ok
        assert result.value.applied == ()
        backend.update_ingestion_metadata.assert_not_called()
        backend.delete_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_frontmatter_resolved_before_scoring(self, tmp_path) -> None:
        # TRAP (found shipping P1): the node's `content` is the resolved BODY,
        # but the on-disk file includes YAML frontmatter. The file must be
        # resolved the same way ingestion resolves it before scoring — this
        # fixture's frontmatter is bulky enough that scoring the raw file
        # text would fall below the threshold.
        old_path = tmp_path / "note.md"
        new_path = tmp_path / "note-renamed.md"
        frontmatter = (
            "---\n"
            "type: user_entry\n"
            "title: A note with a deliberately verbose frontmatter block\n"
            "tags: [alpha, beta, gamma, delta, epsilon, zeta, eta, theta]\n"
            "description: this block exists to dilute raw-text similarity\n"
            "aliases: [one, two, three, four, five, six, seven, eight]\n"
            "extra: padding padding padding padding padding padding padding\n"
            "more: padding padding padding padding padding padding padding\n"
            "---\n"
        )
        raw_file_text = frontmatter + _LONG_BODY
        new_path.write_text(raw_file_text, encoding="utf-8")
        # Premise: raw text scores below threshold, resolved body scores 1.0.
        assert similarity_score(_LONG_BODY, raw_file_text) < SIMILARITY_MOVE_THRESHOLD

        backend = _backend_for_moves(
            [
                {
                    "file_path": str(old_path),
                    "entity_uid": "ue_bb34ef56",
                    "content_hash": _sha("frozen pre-rename file bytes"),
                }
            ],
            live_uids=["ue_bb34ef56"],
            entity_contents={"ue_bb34ef56": _LONG_BODY},
        )
        tracker = IngestionTracker(backend)

        result = await tracker.detect_and_apply_moves(tmp_path, [new_path])

        assert result.is_ok
        assert len(result.value.applied) == 1
        assert result.value.applied[0].similarity == 1.0

    @pytest.mark.asyncio
    async def test_explicit_empty_content_field_suppresses_matching(self, tmp_path) -> None:
        # `content: ""` in frontmatter suppresses body capture (key presence,
        # not truthiness — mirrors build_user_entry_request), so the resolved
        # comparison content is empty → never a similarity candidate.
        old_path = tmp_path / "note.md"
        new_path = tmp_path / "note-renamed.md"
        new_path.write_text(
            f'---\ntype: user_entry\ntitle: Suppressed\ncontent: ""\n---\n{_LONG_BODY}',
            encoding="utf-8",
        )

        backend = _backend_for_moves(
            [
                {
                    "file_path": str(old_path),
                    "entity_uid": "ue_cc56ab78",
                    "content_hash": _sha("frozen pre-rename file bytes"),
                }
            ],
            live_uids=["ue_cc56ab78"],
            entity_contents={"ue_cc56ab78": _LONG_BODY},
        )
        tracker = IngestionTracker(backend)

        result = await tracker.detect_and_apply_moves(tmp_path, [new_path])

        assert result.is_ok
        assert result.value.applied == ()
        backend.update_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_yaml_file_never_a_similarity_candidate(self, tmp_path) -> None:
        # Similarity matching is markdown-only: uid-less notes are markdown;
        # YAML entity files author their uids and have no body to compare.
        old_path = tmp_path / "note.md"
        new_path = tmp_path / "note.yaml"
        new_path.write_text(f"title: whatever\ncontent: {_LONG_BODY}", encoding="utf-8")

        backend = _backend_for_moves(
            [
                {
                    "file_path": str(old_path),
                    "entity_uid": "ue_dd78cd90",
                    "content_hash": _sha("frozen pre-rename file bytes"),
                }
            ],
            live_uids=["ue_dd78cd90"],
            entity_contents={"ue_dd78cd90": _LONG_BODY},
        )
        tracker = IngestionTracker(backend)

        result = await tracker.detect_and_apply_moves(tmp_path, [new_path])

        assert result.is_ok
        assert result.value.applied == ()
        backend.update_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_exact_and_similarity_moves_in_one_sync(self, tmp_path) -> None:
        # A pure rename and a rename+edit in the SAME sync: the exact pass
        # takes the hash match, the similarity pass takes the residual —
        # neither double-handles the other's candidate.
        pure_new = tmp_path / "pure-renamed.md"
        pure_new.write_text("stable body preserved verbatim by the rename", encoding="utf-8")
        edited_new = tmp_path / "edited-renamed.md"
        edited_new.write_text(
            f"---\ntype: user_entry\n---\n{_LONG_BODY} Small addition.", encoding="utf-8"
        )

        backend = _backend_for_moves(
            [
                {
                    "file_path": str(tmp_path / "pure.md"),
                    "entity_uid": "ue_pure",
                    "content_hash": _file_hash(pure_new),
                },
                {
                    "file_path": str(tmp_path / "edited.md"),
                    "entity_uid": "ue_ee90ef12",
                    "content_hash": _sha("frozen pre-rename file bytes"),
                },
            ],
            live_uids=["ue_pure", "ue_ee90ef12"],
            entity_contents={"ue_ee90ef12": _LONG_BODY},
        )
        tracker = IngestionTracker(backend)

        result = await tracker.detect_and_apply_moves(tmp_path, [pure_new, edited_new])

        assert result.is_ok
        by_uid = {move.entity_uid: move for move in result.value.applied}
        assert set(by_uid) == {"ue_pure", "ue_ee90ef12"}
        assert by_uid["ue_pure"].similarity is None  # exact hash — no score
        assert by_uid["ue_ee90ef12"].similarity is not None
        assert by_uid["ue_ee90ef12"].similarity >= SIMILARITY_MOVE_THRESHOLD
        assert backend.update_ingestion_metadata.await_count == 2
        assert backend.delete_ingestion_metadata.await_count == 2

    # ---- Codex #618 candidacy gates: similarity is uid-less-UserEntry-only ----

    async def _similarity_case(
        self, tmp_path, file_name: str, file_text: str, row_uid: str = "ue_aa11bb22"
    ):
        """One gone row (minted-uid unless overridden, content=_LONG_BODY) vs one new file."""
        new_path = tmp_path / file_name
        new_path.write_text(file_text, encoding="utf-8")
        backend = _backend_for_moves(
            [
                {
                    "file_path": str(tmp_path / "gone.md"),
                    "entity_uid": row_uid,
                    "content_hash": _sha("frozen pre-rename file bytes"),
                }
            ],
            live_uids=[row_uid],
            entity_contents={row_uid: _LONG_BODY},
        )
        tracker = IngestionTracker(backend)
        result = await tracker.detect_and_apply_moves(tmp_path, [new_path])
        return result, backend

    @pytest.mark.asyncio
    async def test_authored_uid_new_file_never_a_destination(self, tmp_path) -> None:
        # Codex #618 P1: a new file carrying an authored `uid:` ignores the
        # rewritten row's uid at ingestion (uid_override wins) and re-stamps
        # the row — the gone node would be orphaned, never reconciled.
        result, backend = await self._similarity_case(
            tmp_path,
            "similar-but-authored.md",
            f"---\ntype: user_entry\nuid: moc.worldview\n---\n{_LONG_BODY} Small addition.",
        )
        assert result.is_ok
        assert result.value.applied == ()
        backend.update_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_bare_null_uid_still_a_destination(self, tmp_path) -> None:
        # Codex #618 round 3: a bare `uid:` parses to YAML null, which
        # build_user_entry_request treats as NO override — the prior
        # (rewritten) uid is still honored, so the file is safe to bridge.
        result, _backend = await self._similarity_case(
            tmp_path,
            "template-note.md",
            f"---\ntype: user_entry\nuid:\n---\n{_LONG_BODY} Small addition.",
        )
        assert result.is_ok
        assert len(result.value.applied) == 1
        assert result.value.applied[0].entity_uid == "ue_aa11bb22"

    @pytest.mark.asyncio
    async def test_empty_string_uid_never_a_destination(self, tmp_path) -> None:
        # `uid: ""` is NOT None — it fails build_user_entry_request's
        # `uid_override is None` gate and mints a fresh uid, so bridging a
        # row toward it would orphan the gone node.
        result, backend = await self._similarity_case(
            tmp_path,
            "empty-uid-note.md",
            f'---\ntype: user_entry\nuid: ""\n---\n{_LONG_BODY} Small addition.',
        )
        assert result.is_ok
        assert result.value.applied == ()
        backend.update_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_periodic_new_file_never_a_destination(self, tmp_path) -> None:
        # A periodic note derives its uid (ue:daily:{user}:{date}) — it never
        # honors a prior uid, so rewriting a row toward it would orphan the
        # gone node.
        result, backend = await self._similarity_case(
            tmp_path,
            "daily-note.md",
            "---\ntype: user_entry\nmetadata:\n  entry_kind: daily\ndate: 2026-07-12\n---\n"
            f"{_LONG_BODY} Small addition.",
        )
        assert result.is_ok
        assert result.value.applied == ()
        backend.update_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_turn_in_file_never_a_destination(self, tmp_path) -> None:
        # A turn-in file must keep minting fresh nodes — injecting a uid
        # would silently kill the turn-in channel (#616 hard gate).
        result, backend = await self._similarity_case(
            tmp_path,
            "turn-in.md",
            "---\ntype: user_entry\nfulfills_exercise_uid: ex_12345678\n---\n"
            f"{_LONG_BODY} Small addition.",
        )
        assert result.is_ok
        assert result.value.applied == ()
        backend.update_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_user_entry_type_never_a_destination(self, tmp_path) -> None:
        # A `type: Ku` file routes through the curriculum pipeline, which
        # stamps its own uid over the rewritten row — gone node orphaned.
        result, backend = await self._similarity_case(
            tmp_path,
            "similar-ku.md",
            f"---\ntype: Ku\ntitle: Similar Ku\n---\n{_LONG_BODY} Small addition.",
        )
        assert result.is_ok
        assert result.value.applied == ()
        backend.update_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_retired_alias_type_never_a_destination(self, tmp_path) -> None:
        # Codex #618 round 4: ADR-054-retired type aliases (je_input,
        # je_output, exercise_submission) alias back to USER_ENTRY via
        # EntityType.from_string, but the ingestion detector REJECTS them —
        # such a file fails ingestion, so a rewritten row toward it would
        # keep the gone node alive forever. The gate uses the detector's own
        # verdict.
        result, backend = await self._similarity_case(
            tmp_path,
            "legacy-submission.md",
            f"---\ntype: exercise_submission\n---\n{_LONG_BODY} Small addition.",
        )
        assert result.is_ok
        assert result.value.applied == ()
        backend.update_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_authored_uid_gone_row_never_a_source(self, tmp_path) -> None:
        # Codex #618 P1, other direction: a gone AUTHORED/periodic identity
        # (here a derived periodic uid) is stable across paths — bridging it
        # onto a uid-less note would fuse the new note into the deleted
        # note's identity. Only minted `ue_<8hex>` uids are move sources; the
        # content fetch must not even be attempted.
        result, backend = await self._similarity_case(
            tmp_path,
            "similar-note.md",
            f"---\ntype: user_entry\n---\n{_LONG_BODY} Small addition.",
            row_uid="ue:daily:user_mike:2026-07-12",
        )
        assert result.is_ok
        assert result.value.applied == ()
        backend.get_entity_contents.assert_not_called()
        backend.update_ingestion_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_frontmatter_skipped_not_fatal(self, tmp_path) -> None:
        # Codex #618 P2: valid-YAML-but-not-a-mapping frontmatter (a list)
        # must skip the file, not abort the whole sync with AttributeError.
        result, backend = await self._similarity_case(
            tmp_path,
            "list-frontmatter.md",
            f"---\n- alpha\n- beta\n---\n{_LONG_BODY} Small addition.",
        )
        assert result.is_ok
        assert result.value.applied == ()
        backend.update_ingestion_metadata.assert_not_called()

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
