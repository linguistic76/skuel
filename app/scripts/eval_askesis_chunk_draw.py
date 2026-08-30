#!/usr/bin/env python3
"""Askesis chunk-draw comparison — does the intent chunk-type filter earn its keep?

The instrument for docs/roadmap/deferred-work.md § "Per-Domain Chunking Knobs +
Chunk-Type-Aware Retrieval" Named work **4**: chunk-type-aware retrieval already
exists on the Askesis path as a HARD ``IN`` filter (``_INTENT_CHUNK_TYPES`` →
``retrieve_scoped_chunks(chunk_types=)``), and over a fallback-dominated type
distribution it starves the narrow intents. Measured 2026-08-30 on the 925-chunk
v2 corpus: an EXPLORATORY question can draw on **66 of 925** chunks (7.1%),
PRACTICE on 137 (14.8%) — and ``introduction``, one of EXPLORATORY's three
named types, matches ZERO rows.

Three arms over the SAME queries and the same embedding, so the only variable is
the filter:

  filtered   — production today: hard ``chunk_type IN $types`` for the classified
               intent (no filter for the unmapped intents).
  thin_draw  — the proposal: keep every filtered hit, then BACKFILL from an
               unfiltered draw until k. Never loses an intent-appropriate
               passage, which a plain "unfiltered when thin" fallback can —
               the unfiltered top-k ranks on score alone, so a definition
               chunk sitting at overall rank 12 is in the filtered draw and
               NOT in the unfiltered one.
  unfiltered — the control/ceiling: no type filter at all. If this does not beat
               `filtered`, the filter costs nothing and Named work 3's weight
               table is arguing about a non-problem.

Scored as recall@k over chunk PARENTS against the same reviewable query set the
/search eval uses (scripts/eval_chunk_retrieval_queries.yaml) — a query hits when
a passage from any expected uid is drawn. This measures RETRIEVAL, not the merged
/search ordering; `eval_chunk_retrieval.py` is the instrument for that.

Production shape it reproduces (ContextRetriever._find_similar_chunks):
``SearchRequest(query_text=query, limit=5)``, ``min_score=0.6`` — note that is
NOT /search's 0.68 body-chunk floor — and ``user_uid`` as the AUDIENCE, so the
draw sees the asking user's own vault passages exactly as Askesis does
(ADR-085 G8). Pass --user to name that viewer; without it the draw is
curriculum-only and the user_entry share of the corpus is invisible.

Usage:
    uv run python scripts/eval_askesis_chunk_draw.py --user user_mike
    uv run python scripts/eval_askesis_chunk_draw.py --json

Requires INTELLIGENCE_TIER=full (query embedding + intent classification).
Read-only apart from the embedding API calls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

# Sibling script: sys.path[0] is scripts/ when run as `python scripts/...`,
# which is how ./dev invokes it. The query set is shared ON PURPOSE — one
# reviewable set of query→expected-hit claims, two retrieval paths.
from eval_chunk_retrieval import (  # type: ignore[import-not-found]
    DEFAULT_QUERY_SET,
    QuerySet,
    load_query_set,
)

if TYPE_CHECKING:
    from core.models.query_types import QueryIntent

# ContextRetriever._find_similar_chunks, verbatim — the production draw this
# comparison must reproduce, not an idealized one.
ASKESIS_LIMIT = 5
ASKESIS_MIN_SCORE = 0.6

ARMS = ("filtered", "thin_draw", "unfiltered")


class ArmReport(TypedDict):
    """One arm's aggregate outcome."""

    hits: int
    recall_at_k: float
    mean_chunks_drawn: float
    starved_queries: int


class RowReport(TypedDict):
    """One query's outcome across all three arms."""

    query: str
    kind: str
    intent: str
    filter_types: list[str] | None
    filtered_chunks: int
    filtered_hit: bool
    thin_draw_chunks: int
    thin_draw_hit: bool
    thin_draw_backfilled: int
    unfiltered_chunks: int
    unfiltered_hit: bool
    error: str | None


class ComparisonReport(TypedDict):
    """The full comparison — the JSON contract of a recorded run."""

    query_set_version: int
    ratified: str | None
    k: int
    viewer_uid: str | None
    query_count: int
    errors: int
    # Queries whose classified intent actually carries a chunk-type filter. At
    # ZERO the three arms are identical BY CONSTRUCTION and the comparison has
    # measured nothing about filtering — the instrument must say so rather than
    # let a 0.0% delta read as "the filter is fine".
    filtered_intent_queries: int
    arms: dict[str, ArmReport]
    rows: list[RowReport]


@dataclass
class DrawRow:
    """Outcome of one query across the three arms."""

    query: str
    kind: str
    intent: str
    filter_types: list[str] | None
    filtered_parents: list[str] = field(default_factory=list)
    unfiltered_parents: list[str] = field(default_factory=list)
    thin_draw_parents: list[str] = field(default_factory=list)
    filtered_chunks: int = 0
    unfiltered_chunks: int = 0
    thin_draw_chunks: int = 0
    thin_draw_backfilled: int = 0
    expect: tuple[str, ...] = ()
    error: str | None = None

    def hit(self, parents: list[str]) -> bool:
        return any(uid in parents for uid in self.expect)

    def to_dict(self) -> RowReport:
        return {
            "query": self.query,
            "kind": self.kind,
            "intent": self.intent,
            "filter_types": self.filter_types,
            "filtered_chunks": self.filtered_chunks,
            "filtered_hit": self.hit(self.filtered_parents),
            "thin_draw_chunks": self.thin_draw_chunks,
            "thin_draw_hit": self.hit(self.thin_draw_parents),
            "thin_draw_backfilled": self.thin_draw_backfilled,
            "unfiltered_chunks": self.unfiltered_chunks,
            "unfiltered_hit": self.hit(self.unfiltered_parents),
            "error": self.error,
        }


def backfill(
    filtered: list[dict[str, Any]], unfiltered: list[dict[str, Any]], k: int
) -> tuple[list[dict[str, Any]], int]:
    """Top a thin intent-filtered draw up to k from the unfiltered draw (pure, DB-free).

    Every filtered hit is KEPT and keeps its position — the intent preference is
    a preference, not something the fallback discards. Backfill rows are appended
    in unfiltered score order, skipping chunks already drawn. Returns the merged
    draw and how many rows the backfill contributed (0 when the filtered draw was
    already full, which is the no-op the fallback must be for the wide intents).
    """
    if len(filtered) >= k:
        return list(filtered), 0
    seen = {hit.get("chunk_uid") for hit in filtered}
    merged = list(filtered)
    for hit in unfiltered:
        if len(merged) >= k:
            break
        if hit.get("chunk_uid") in seen:
            continue
        merged.append(hit)
        seen.add(hit.get("chunk_uid"))
    return merged, len(merged) - len(filtered)


def parents_of(hits: list[dict[str, Any]]) -> list[str]:
    """Distinct parent uids in draw order (pure, DB-free)."""
    ordered: list[str] = []
    for hit in hits:
        parent = str(hit.get("parent_uid") or "")
        if parent and parent not in ordered:
            ordered.append(parent)
    return ordered


def summarize(rows: list[DrawRow], query_set: QuerySet, viewer_uid: str | None) -> ComparisonReport:
    """Aggregate per-query rows into the report dict (pure, DB-free)."""
    scored = [row for row in rows if row.error is None]
    total = len(scored)

    def arm(parents_attr: str, chunks_attr: str) -> ArmReport:
        hits = sum(1 for row in scored if row.hit(getattr(row, parents_attr)))
        drawn = [getattr(row, chunks_attr) for row in scored]
        return {
            "hits": hits,
            "recall_at_k": round(hits / total, 4) if total else 0.0,
            "mean_chunks_drawn": round(sum(drawn) / total, 2) if total else 0.0,
            # A draw that could not fill k — the starvation this work exists to measure.
            "starved_queries": sum(1 for n in drawn if n < ASKESIS_LIMIT),
        }

    return {
        "query_set_version": query_set.version,
        "ratified": query_set.ratified,
        "k": ASKESIS_LIMIT,
        "viewer_uid": viewer_uid,
        "query_count": total,
        "errors": len(rows) - total,
        "filtered_intent_queries": sum(1 for row in scored if row.filter_types is not None),
        "arms": {
            "filtered": arm("filtered_parents", "filtered_chunks"),
            "thin_draw": arm("thin_draw_parents", "thin_draw_chunks"),
            "unfiltered": arm("unfiltered_parents", "unfiltered_chunks"),
        },
        "rows": [row.to_dict() for row in rows],
    }


async def _classify(classifier: Any, query: str) -> "QueryIntent":
    """Classify one query, falling back to SPECIFIC exactly as production does."""
    from core.models.query_types import QueryIntent

    result = await classifier.classify_intent(query)
    return result.value if result.is_ok else QueryIntent.SPECIFIC


async def run_comparison(
    query_set: QuerySet, *, viewer_uid: str | None, as_json: bool
) -> tuple[int, ComparisonReport | None]:
    """Compose services and draw all three arms per query."""
    from adapters.infrastructure.event_bus import InMemoryEventBus
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from core.models.search_request import SearchRequest
    from core.services.askesis.context_retriever import _intent_to_chunk_types
    from core.services.askesis.intent_classifier import IntentClassifier
    from services_bootstrap import compose_services

    if not as_json:
        print("Connecting to Neo4j...", file=sys.stderr)
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        composed = await compose_services(adapter, InMemoryEventBus())
        if composed.is_error:
            print(f"ERROR: composition failed: {composed.expect_error()}", file=sys.stderr)
            return 1, None

        router = composed.value.search_router
        embeddings = composed.value.embeddings_service
        if router is None:
            print("ERROR: search router is not wired", file=sys.stderr)
            return 1, None
        if embeddings is None or composed.value.vector_search_service is None:
            # Without the Digital layer every arm draws zero and the comparison
            # would "show" three identical arms — the predictable wrong-firing
            # mode, so refuse rather than measure it.
            print(
                "ERROR: this comparison requires INTELLIGENCE_TIER=full "
                "(query embedding + intent classification). Refusing to run "
                "three empty arms.",
                file=sys.stderr,
            )
            return 2, None
        classifier = IntentClassifier(embeddings)

        rows: list[DrawRow] = []
        for eval_query in query_set.queries:
            intent = await _classify(classifier, eval_query.query)
            filter_types = _intent_to_chunk_types(intent)
            row = DrawRow(
                query=eval_query.query,
                kind=eval_query.kind,
                intent=intent.value,
                filter_types=filter_types,
                expect=eval_query.expect,
            )
            request = SearchRequest(query_text=eval_query.query, limit=ASKESIS_LIMIT)

            unfiltered = await router.retrieve_scoped_chunks(
                request, chunk_types=None, min_score=ASKESIS_MIN_SCORE, user_uid=viewer_uid
            )
            if unfiltered.is_error:
                row.error = f"unfiltered draw failed: {unfiltered.expect_error()}"
                rows.append(row)
                continue
            # An unmapped intent (SPECIFIC / AGGREGATION / GOAL_ACHIEVEMENT)
            # passes chunk_types=None, so its filtered arm IS the unfiltered
            # draw — reuse it rather than paying for an identical second call.
            if filter_types is None:
                filtered_hits = list(unfiltered.value)
            else:
                filtered = await router.retrieve_scoped_chunks(
                    request,
                    chunk_types=filter_types,
                    min_score=ASKESIS_MIN_SCORE,
                    user_uid=viewer_uid,
                )
                if filtered.is_error:
                    row.error = f"filtered draw failed: {filtered.expect_error()}"
                    rows.append(row)
                    continue
                filtered_hits = list(filtered.value)

            merged, backfilled = backfill(filtered_hits, list(unfiltered.value), ASKESIS_LIMIT)
            row.filtered_chunks = len(filtered_hits)
            row.unfiltered_chunks = len(unfiltered.value)
            row.thin_draw_chunks = len(merged)
            row.thin_draw_backfilled = backfilled
            row.filtered_parents = parents_of(filtered_hits)
            row.unfiltered_parents = parents_of(list(unfiltered.value))
            row.thin_draw_parents = parents_of(merged)
            rows.append(row)

        report = summarize(rows, query_set, viewer_uid)
        return (1 if report["errors"] else 0), report
    finally:
        await adapter.close()


def _print_human(report: ComparisonReport) -> None:
    """Render the comparison as a readable console summary."""
    print(f"\n=== Askesis Chunk-Draw Comparison (set v{report['query_set_version']}) ===")
    if not report["ratified"]:
        print("!! DRAFT query set (ratified: null) — relative arms still compare,")
        print("!! but the absolute recall numbers are not a baseline.")
    print(f"Viewer: {report['viewer_uid'] or 'NONE (curriculum-only draw)'}")
    print(f"Queries: {report['query_count']}   k={report['k']}   min_score={ASKESIS_MIN_SCORE}")
    if report["errors"]:
        print(f"ERRORS: {report['errors']}")

    if report["query_count"] and not report["filtered_intent_queries"]:
        print(
            "\n!! NO QUERY REACHED A FILTERED INTENT — every one classified to an\n"
            "!! unmapped intent, so all three arms ran the SAME unfiltered draw.\n"
            "!! The equal recall below is an identity, not a finding about\n"
            "!! filtering. Look at the intent column, then at IntentClassifier."
        )

    print(f"\n{'arm':<12} {'recall@k':>9} {'hits':>6} {'mean drawn':>11} {'starved':>8}")
    for name in ARMS:
        a = report["arms"][name]
        print(
            f"{name:<12} {a['recall_at_k']:>8.1%} {a['hits']:>6} "
            f"{a['mean_chunks_drawn']:>11.2f} {a['starved_queries']:>8}"
        )

    print("\nPer query (F=filtered, T=thin-draw, U=unfiltered):")
    for row in report["rows"]:
        if row["error"]:
            print(f"  !! {row['query'][:44]:<44} {row['error']}")
            continue
        marks = "".join(
            mark if row[key] else "·"  # type: ignore[literal-required]
            for mark, key in (
                ("F", "filtered_hit"),
                ("T", "thin_draw_hit"),
                ("U", "unfiltered_hit"),
            )
        )
        print(
            f"  {marks:<4} {row['query'][:40]:<40} {row['intent']:<14} "
            f"n={row['filtered_chunks']}→{row['thin_draw_chunks']} "
            f"(+{row['thin_draw_backfilled']})"
        )

    filtered_recall = report["arms"]["filtered"]["recall_at_k"]
    thin_recall = report["arms"]["thin_draw"]["recall_at_k"]
    print(
        f"\nThin-draw delta vs production filter: "
        f"{thin_recall - filtered_recall:+.1%} recall@{report['k']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERY_SET)
    parser.add_argument(
        "--user",
        default=None,
        help="Viewer uid — the AUDIENCE for the draw (ADR-085). Omit for curriculum-only.",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    try:
        query_set = load_query_set(args.queries)
    except (OSError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    exit_code, report = asyncio.run(
        run_comparison(query_set, viewer_uid=args.user, as_json=args.as_json)
    )
    if report is None:
        return exit_code
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        _print_human(report)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
