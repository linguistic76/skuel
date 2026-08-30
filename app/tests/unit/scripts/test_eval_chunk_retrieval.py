"""Tests for the chunk-retrieval eval's pure parts: set validation and scoring.

The instrument's DB half is deliberately untested here (it drives the live
production path — that's the point of the tool); what must never be wrong
silently is the query-set gate and the rank arithmetic, because a mis-scored
run would masquerade as a baseline.

These tests deliberately do NOT read the checked-in query-set YAML: CI's
``py`` path filter would not re-run them on a YAML-only edit, so a green run
against the file would be stale evidence. The script validates the real file
on every invocation instead — that is the file's gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ has no __init__.py, and this directory is itself named `scripts`,
# so it shadows the real package under pytest's prepend import mode.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from eval_chunk_retrieval import (  # type: ignore[import-not-found]
    EvalQuery,
    QueryRow,
    QuerySet,
    load_query_set,
    score_query,
    summarize,
)

VALID_SET = """
version: 1
ratified: null
k: 5
queries:
  - query: breath
    kind: real_usage
    expect: [ps.mindfulness.breath-awareness-basics]
    note: real query
  - query: how trees share resources underground
    kind: body_paraphrase
    expect: [ku.nature.forests, ku.nature.weather]
"""


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "queries.yaml"
    path.write_text(content, encoding="utf-8")
    return path


class TestLoadQuerySet:
    def test_valid_set_parses(self, tmp_path: Path) -> None:
        qs = load_query_set(_write(tmp_path, VALID_SET))
        assert qs.version == 1
        assert qs.ratified is None
        assert qs.k == 5
        assert len(qs.queries) == 2
        assert qs.queries[0].kind == "real_usage"
        assert qs.queries[1].expect == ("ku.nature.forests", "ku.nature.weather")
        assert qs.queries[1].note == ""  # note is optional

    def test_ratified_date_becomes_string(self, tmp_path: Path) -> None:
        content = VALID_SET.replace("ratified: null", "ratified: 2026-09-01")
        qs = load_query_set(_write(tmp_path, content))
        assert qs.ratified == "2026-09-01"

    @pytest.mark.parametrize(
        ("mutation", "fragment"),
        [
            (("version: 1", "version: '1'"), "'version' must be an integer"),
            (("k: 5", "k: 0"), "'k' must be a positive integer"),
            (("kind: real_usage", "kind: vibes"), "'kind' must be one of"),
            (
                ("expect: [ps.mindfulness.breath-awareness-basics]", "expect: []"),
                "'expect' must be a non-empty list",
            ),
            (
                (
                    "expect: [ku.nature.forests, ku.nature.weather]",
                    "expect: [ku.nature.forests, ku.nature.forests]",
                ),
                "duplicate uids in 'expect'",
            ),
            (("query: breath", "query: ''"), "'query' must be a non-empty string"),
        ],
    )
    def test_defects_raise_loudly(
        self, tmp_path: Path, mutation: tuple[str, str], fragment: str
    ) -> None:
        old, new = mutation
        assert old in VALID_SET
        with pytest.raises(ValueError, match=fragment):
            load_query_set(_write(tmp_path, VALID_SET.replace(old, new)))

    @pytest.mark.parametrize("value", ["false", "yes", "not-a-date", "[2026]", "{d: 1}"])
    def test_ratified_rejects_non_dates(self, tmp_path: Path, value: str) -> None:
        # `ratified: false` once coerced to the truthy string "False" — a typo
        # would have certified a draft set as the baseline (Codex, PR #1197).
        content = VALID_SET.replace("ratified: null", f"ratified: {value}")
        with pytest.raises(ValueError, match="'ratified' must be null or an ISO date"):
            load_query_set(_write(tmp_path, content))

    def test_ratified_quoted_iso_string_ok(self, tmp_path: Path) -> None:
        content = VALID_SET.replace("ratified: null", "ratified: '2026-09-01'")
        assert load_query_set(_write(tmp_path, content)).ratified == "2026-09-01"

    def test_duplicate_query_text_raises(self, tmp_path: Path) -> None:
        content = VALID_SET.replace("query: how trees share resources underground", "query: breath")
        with pytest.raises(ValueError, match="duplicate query text"):
            load_query_set(_write(tmp_path, content))

    def test_empty_queries_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="'queries' must be a non-empty list"):
            load_query_set(_write(tmp_path, "version: 1\nratified: null\nk: 5\nqueries: []\n"))


def _query(expect: tuple[str, ...] = ("ku.a", "ku.b")) -> EvalQuery:
    return EvalQuery(query="q", kind="body_paraphrase", expect=expect, note="")


class TestScoreQuery:
    def test_hit_at_rank_one_via_frontmatter(self) -> None:
        row = score_query(_query(), ["ku.a", "ku.x"], body_uids=set(), k=5)
        assert row.hit and row.best_rank == 1 and row.matched_uid == "ku.a"
        assert not row.via_body
        assert row.expected_missing == ["ku.b"]

    def test_best_of_several_expected_wins(self) -> None:
        row = score_query(_query(), ["ku.x", "ku.b", "ku.a"], body_uids={"ku.b"}, k=5)
        assert row.hit and row.best_rank == 2 and row.matched_uid == "ku.b"
        assert row.via_body  # the rank-2 card came from the body fold

    def test_present_but_below_k_is_a_miss_with_rank(self) -> None:
        uids = [f"ku.f{i}" for i in range(6)] + ["ku.a"]
        row = score_query(_query(), uids, body_uids={"ku.a"}, k=5)
        assert not row.hit
        assert row.best_rank == 7  # the trace PR-2 needs: found, but crowded out
        assert not row.via_body  # via_body describes the HIT, and there is none

    def test_absent_entirely(self) -> None:
        row = score_query(_query(), ["ku.x", "ku.y"], body_uids=set(), k=5)
        assert not row.hit and row.best_rank is None and row.matched_uid is None
        assert row.expected_missing == ["ku.a", "ku.b"]

    def test_counts_reflect_result_lists(self) -> None:
        row = score_query(_query(), ["ku.a", "ku.x", "ku.y"], body_uids={"ku.y"}, k=5)
        assert row.result_count == 3
        assert row.body_result_count == 1

    def test_chunk_candidates_passthrough(self) -> None:
        # The probe's candidate count rides the row into the report — the
        # per-query proof that body search ran (and how much it had to offer).
        row = score_query(_query(), ["ku.a"], body_uids=set(), k=5, chunk_candidates=12)
        assert row.chunk_candidates == 12
        assert row.to_dict()["chunk_candidates"] == 12


class TestSummarize:
    def _set(self) -> QuerySet:
        return QuerySet(
            version=1,
            ratified=None,
            k=5,
            queries=(_query(("ku.a",)), _query(("ku.b",))),
        )

    def test_aggregates_by_kind_and_body_attribution(self) -> None:
        rows = [
            QueryRow("q1", "real_usage", True, 1, "ku.a", False, 5, 0, []),
            QueryRow("q2", "body_paraphrase", True, 3, "ku.b", True, 8, 2, []),
            QueryRow("q3", "body_paraphrase", False, None, None, False, 4, 1, ["ku.c"]),
        ]
        report = summarize(rows, self._set())
        assert report["query_count"] == 3
        assert report["hits"] == 2
        assert report["hit_at_k"] == round(2 / 3, 4)
        assert report["hits_via_body"] == 1
        assert report["by_kind"]["body_paraphrase"] == {
            "queries": 2,
            "hits": 1,
            "hit_at_k": 0.5,
            "hits_via_body": 1,
        }
        assert report["errors"] == 0

    def test_errored_rows_counted_and_excluded_from_hits(self) -> None:
        rows = [
            QueryRow("q1", "real_usage", False, None, None, False, 0, 0, ["ku.a"], error="boom"),
            QueryRow("q2", "real_usage", True, 2, "ku.b", False, 5, 0, []),
        ]
        report = summarize(rows, self._set())
        assert report["errors"] == 1
        assert report["hits"] == 1
        assert report["by_kind"]["real_usage"]["queries"] == 2
        assert report["by_kind"]["real_usage"]["hits"] == 1
