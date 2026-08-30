"""Tests for the Askesis chunk-draw comparison's pure parts.

The DB half drives the live retrieval path — that is the tool's point. What
must never be wrong silently is the backfill rule and the arm arithmetic: a
thin-draw arm that quietly dropped a filtered hit, or a starvation count off
by one, would argue for a behavior change on bad evidence.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from eval_askesis_chunk_draw import (  # type: ignore[import-not-found]
    ASKESIS_PROMPT_WINDOW,
    DrawRow,
    backfill,
    parents_of,
    summarize,
    unlabelled_in_window,
)
from eval_chunk_retrieval import QuerySet  # type: ignore[import-not-found]


def _chunk(uid: str, parent: str) -> dict[str, object]:
    return {"chunk_uid": uid, "parent_uid": parent}


class TestBackfill:
    def test_full_filtered_draw_is_a_no_op(self) -> None:
        # The fallback must not touch the WIDE intents — 85% of the corpus is
        # eligible for them, so they fill k and the arm should be identical.
        filtered = [_chunk(f"c{i}", "ku.a") for i in range(5)]
        merged, added = backfill(filtered, [_chunk("x", "ku.z")], 5)
        assert added == 0
        assert merged == filtered

    def test_thin_draw_is_topped_up_from_the_unfiltered_draw(self) -> None:
        filtered = [_chunk("c1", "ku.a")]
        unfiltered = [_chunk("c9", "ku.b"), _chunk("c8", "ku.c")]
        merged, added = backfill(filtered, unfiltered, 3)
        assert added == 2
        assert [c["chunk_uid"] for c in merged] == ["c1", "c9", "c8"]

    def test_every_filtered_hit_survives_the_backfill(self) -> None:
        # The design claim: unlike "use the unfiltered draw when thin", this
        # can never lose an intent-appropriate passage that the unfiltered
        # top-k would have ranked out.
        filtered = [_chunk("deep", "ku.definition")]
        unfiltered = [_chunk(f"hi{i}", "ku.other") for i in range(5)]
        merged, _ = backfill(filtered, unfiltered, 5)
        assert merged[0]["chunk_uid"] == "deep"
        assert len(merged) == 5

    def test_duplicates_are_not_drawn_twice(self) -> None:
        filtered = [_chunk("c1", "ku.a")]
        unfiltered = [_chunk("c1", "ku.a"), _chunk("c2", "ku.b")]
        merged, added = backfill(filtered, unfiltered, 5)
        assert added == 1
        assert [c["chunk_uid"] for c in merged] == ["c1", "c2"]

    def test_backfill_stops_at_k(self) -> None:
        merged, added = backfill([], [_chunk(f"c{i}", "ku.a") for i in range(9)], 5)
        assert (len(merged), added) == (5, 5)

    def test_empty_unfiltered_draw_leaves_a_thin_draw_thin(self) -> None:
        # Starvation the fallback cannot cure: nothing cleared min_score.
        merged, added = backfill([_chunk("c1", "ku.a")], [], 5)
        assert (len(merged), added) == (1, 0)


class TestUnlabelledInWindow:
    """The per-arm audience accounting — computed on CHUNKS, inside the window."""

    def _u(self, parent_type: str) -> dict[str, object]:
        return {"chunk_uid": "c", "parent_uid": "p", "parent_entity_type": parent_type}

    def test_curriculum_parents_are_labelled(self) -> None:
        assert unlabelled_in_window([self._u("ku"), self._u("path_step")]) == 0

    def test_user_entry_parents_are_unlabelled(self) -> None:
        assert unlabelled_in_window([self._u("user_entry"), self._u("ku")]) == 1

    def test_only_the_prompt_window_is_counted(self) -> None:
        # A note at draw rank 4 never reaches the prompt, so it biases nothing.
        draw = [self._u("ku")] * ASKESIS_PROMPT_WINDOW + [self._u("user_entry")]
        assert unlabelled_in_window(draw) == 0


class TestParentsOf:
    def test_distinct_parents_in_draw_order(self) -> None:
        hits = [_chunk("c1", "ku.a"), _chunk("c2", "ku.a"), _chunk("c3", "ku.b")]
        assert parents_of(hits) == ["ku.a", "ku.b"]

    def test_missing_parent_uids_are_dropped(self) -> None:
        assert parents_of([{"chunk_uid": "c1"}, _chunk("c2", "ku.b")]) == ["ku.b"]

    def test_chunks_are_sliced_before_dedupe_not_after(self) -> None:
        # Production truncates the CHUNK list (context_retriever.py:299), not a
        # deduped parent list. When several top chunks share a parent, deduping
        # first and slicing after PROMOTES a parent that production threw away.
        draw = [
            _chunk("c1", "ku.a"),
            _chunk("c2", "ku.a"),
            _chunk("c3", "ku.a"),
            _chunk("c4", "ku.expected"),
        ]
        # Right: slice chunks, then dedupe — only ku.a was ever delivered.
        assert parents_of(draw[:ASKESIS_PROMPT_WINDOW]) == ["ku.a"]
        # Wrong (the bug): dedupe, then slice — ku.expected appears to survive.
        assert parents_of(draw)[:ASKESIS_PROMPT_WINDOW] == ["ku.a", "ku.expected"]


def _row(**kw: object) -> DrawRow:
    base: dict[str, object] = {
        "query": "q",
        "kind": "body_paraphrase",
        "intent": "exploratory",
        "filter_types": ["definition"],
        "expect": ("ku.a",),
    }
    base.update(kw)
    return DrawRow(**base)  # type: ignore[arg-type]


class TestSummarize:
    def _set(self) -> QuerySet:
        return QuerySet(version=2, ratified=None, k=5, queries=())

    def test_arms_are_scored_independently(self) -> None:
        rows = [
            _row(
                filtered_window_parents=[],
                thin_draw_window_parents=["ku.a"],
                unfiltered_window_parents=["ku.a"],
                filtered_chunks=1,
                thin_draw_chunks=5,
                unfiltered_chunks=5,
            )
        ]
        report = summarize(rows, self._set(), None)
        assert report["arms"]["filtered"]["hits"] == 0
        assert report["arms"]["thin_draw"]["hits"] == 1
        assert report["arms"]["unfiltered"]["hits"] == 1

    def test_starvation_is_measured_against_the_prompt_window(self) -> None:
        # Production draws 5 but keeps relevant_chunks[:3]. A 4-chunk draw has
        # lost NOTHING, so it must not be counted as starved — only a draw too
        # thin to fill the prompt window costs Askesis context.
        rows = [
            _row(filtered_chunks=4, thin_draw_chunks=5),
            _row(filtered_chunks=1, thin_draw_chunks=5),
        ]
        report = summarize(rows, self._set(), None)
        assert report["arms"]["filtered"]["starved_queries"] == 1
        assert report["arms"]["thin_draw"]["starved_queries"] == 0

    def test_only_parents_reaching_the_prompt_score(self) -> None:
        # The window lists are built from chunks already truncated to the
        # prompt window, so a parent absent from one was never delivered.
        row = _row(filtered_window_parents=["ku.x"], thin_draw_window_parents=["ku.a"])
        report = summarize([row], self._set(), None)
        assert report["arms"]["filtered"]["hits"] == 0
        assert report["arms"]["thin_draw"]["hits"] == 1

    def test_unlabelled_chunks_are_counted_per_arm(self) -> None:
        # A --user run admits the viewer's own notes into the prompt window.
        # They compete but cannot score, so the count has to ride into the
        # report or a depressed recall reads as a retrieval defect.
        rows = [
            _row(filtered_unlabelled=2, thin_draw_unlabelled=1, unfiltered_unlabelled=0),
            _row(filtered_unlabelled=0, thin_draw_unlabelled=0, unfiltered_unlabelled=1),
        ]
        report = summarize(rows, self._set(), "user_mike")
        assert report["arms"]["filtered"]["unlabelled_in_windows"] == 2
        assert report["arms"]["thin_draw"]["unlabelled_in_windows"] == 1
        assert report["arms"]["unfiltered"]["unlabelled_in_windows"] == 1
        assert report["unlabelled_chunks_drawn"] == 4

    def test_a_note_in_one_arm_alone_still_raises_the_total(self) -> None:
        # The biasing case: an unlabelled note occupies ONLY the unfiltered
        # window, depressing that arm alone. Counting a single arm would leave
        # the total at 0 and the delta looking attributable to filtering.
        rows = [_row(unfiltered_unlabelled=1)]
        report = summarize(rows, self._set(), "user_mike")
        assert report["unlabelled_chunks_drawn"] == 1
        assert report["arms"]["filtered"]["unlabelled_in_windows"] == 0

    def test_errored_rows_are_excluded_from_every_arm(self) -> None:
        # An errored row must not dilute a recall rate — it is not a miss.
        rows = [
            _row(
                filtered_window_parents=["ku.a"],
                thin_draw_window_parents=["ku.a"],
                unfiltered_window_parents=["ku.a"],
            ),
            _row(error="draw failed"),
        ]
        report = summarize(rows, self._set(), None)
        assert report["errors"] == 1
        assert report["query_count"] == 1
        assert report["arms"]["filtered"]["recall_at_k"] == 1.0

    def test_filtered_intent_queries_counts_only_mapped_intents(self) -> None:
        # The guard against a false clean bill: with zero filtered-intent rows
        # the arms are identical BY CONSTRUCTION, so the count must be reported
        # or a +0.0% delta reads as "the filter is harmless" when in fact the
        # filter never ran. Measured 2026-08-30: 0 of 23 on the live corpus.
        rows = [_row(filter_types=None), _row(filter_types=["definition"])]
        assert summarize(rows, self._set(), None)["filtered_intent_queries"] == 1

    def test_no_mapped_intent_is_reported_as_zero(self) -> None:
        rows = [_row(filter_types=None), _row(filter_types=None)]
        assert summarize(rows, self._set(), None)["filtered_intent_queries"] == 0

    def test_viewer_uid_is_recorded(self) -> None:
        # The audience is the difference between a curriculum-only draw and one
        # that sees the asking user's vault notes (ADR-085 G8) — it must ride
        # into the record or two runs are not comparable.
        assert summarize([], self._set(), "user_mike")["viewer_uid"] == "user_mike"
