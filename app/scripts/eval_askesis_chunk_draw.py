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
import contextlib
import json
import sys
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

# Sibling script: sys.path[0] is scripts/ when run as `python scripts/...`,
# which is how ./dev invokes it. The query set is shared ON PURPOSE — one
# reviewable set of query→expected-hit claims, two retrieval paths.
from eval_chunk_retrieval import (  # type: ignore[import-not-found]
    DEFAULT_QUERY_SET,
    QuerySet,
    load_query_set,
)

if TYPE_CHECKING:
    from core.ports.query_types import SemanticSearchChunkResult
    from core.services.askesis.intent_classifier import IntentClassification, IntentClassifier


# ContextRetriever._find_similar_chunks, verbatim — the production draw this
# comparison must reproduce, not an idealized one.
ASKESIS_LIMIT = 5
ASKESIS_MIN_SCORE = 0.6

# ...and `retrieve_relevant_context` then keeps `relevant_chunks[:3]`, which is
# what `llm_service` inlines into the prompt. Recall is scored at THIS window,
# not at the draw limit: a parent reached only at draw rank 4 is retrieved and
# then thrown away, so counting it as a production hit overstates what Askesis
# can ground an answer in. Starvation is measured against it for the mirror
# reason — a 4-chunk draw still fills the prompt and has lost nothing.
ASKESIS_PROMPT_WINDOW = 3

ARMS = ("filtered", "thin_draw", "unfiltered")


@cache
def labelled_parent_types() -> frozenset[str]:
    """The parent types the shared query set actually labels.

    A --user run admits the asking user's UserEntry passages too (ADR-085
    audience) — production-faithful, but unlabelled, so they compete for the
    prompt window without being able to score. Counted, never filtered out:
    dropping them would stop the comparison reproducing the production draw,
    which is its whole point.

    Derived from ``EntityType``, never re-spelled: this set gates the caveat
    that qualifies the whole experiment, so a renamed discriminator must break
    loudly rather than silently reclassify curriculum passages as noise.
    Imported lazily to keep the module importable (and ``--help`` usable)
    without loading the app.
    """
    from core.models.enums.entity_enums import EntityType

    return frozenset({EntityType.KU.value, EntityType.PATH_STEP.value})


def unlabelled_in_window(hits: list["SemanticSearchChunkResult"]) -> int:
    """Chunks in one arm's prompt window whose parent the query set cannot label.

    Per ARM, never once for the run: when the intent filter is live the three
    arms hold DIFFERENT windows, so an unlabelled note can occupy the unfiltered
    top three alone — depressing that arm's recall while the other two are
    clean. Counting only one arm would leave that delta looking attributable to
    filtering (Codex, PR #1198).
    """
    return sum(
        1
        for hit in hits[:ASKESIS_PROMPT_WINDOW]
        if str(hit.get("parent_entity_type") or "") not in labelled_parent_types()
    )


class ArmReport(TypedDict):
    """One arm's aggregate outcome."""

    hits: int
    recall_at_k: float
    mean_chunks_drawn: float
    starved_queries: int
    unlabelled_in_windows: int


class RowReport(TypedDict):
    """One query's outcome across all three arms."""

    query: str
    kind: str
    intent: str
    # The best average exemplar similarity behind `intent`. Reported because a
    # bare SPECIFIC cannot distinguish "genuinely ambiguous query" from
    # "threshold nothing can reach" — the distinction the ruling turns on.
    intent_score: float
    filter_types: list[str] | None
    filtered_chunks: int
    filtered_hit: bool
    thin_draw_chunks: int
    thin_draw_hit: bool
    thin_draw_backfilled: int
    unfiltered_chunks: int
    unfiltered_hit: bool
    filtered_unlabelled: int
    thin_draw_unlabelled: int
    unfiltered_unlabelled: int
    error: str | None


class ComparisonReport(TypedDict):
    """The full comparison — the JSON contract of a recorded run."""

    query_set_version: int
    ratified: str | None
    k: int
    viewer_uid: str | None
    draw_limit: int
    query_count: int
    errors: int
    # The confidence gate, and the best score any query reached against it. A
    # max well below the gate is the evidence that no query CAN be classified —
    # without it, `filtered_intent_queries: 0` is indistinguishable from an
    # embedding outage that silently classified everything as SPECIFIC.
    intent_threshold: float
    max_intent_score: float
    # Chunks drawn from parents OUTSIDE the query set's label vocabulary — the
    # asking user's own UserEntry passages, admitted by --user. They are real
    # production competition for the prompt window, but the set labels only
    # published Ku/PathStep parents, so they can only ever displace a labelled
    # hit and never score as one. Reported so a --user run's recall is read as
    # a curriculum-recall proxy, not as production answer quality.
    unlabelled_chunks_drawn: int
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
    intent_score: float
    filter_types: list[str] | None
    # Parents of the chunks that REACH THE PROMPT — derived from the chunk list
    # already sliced to ASKESIS_PROMPT_WINDOW, never from a deduped parent list
    # sliced afterwards. Those are different: chunks [A, A, A, expected] dedupe
    # to parents [A, expected], and slicing THAT at 3 would score `expected` as
    # a hit although production truncated it away with the fourth chunk.
    filtered_window_parents: list[str] = field(default_factory=list)
    unfiltered_window_parents: list[str] = field(default_factory=list)
    thin_draw_window_parents: list[str] = field(default_factory=list)
    filtered_chunks: int = 0
    unfiltered_chunks: int = 0
    thin_draw_chunks: int = 0
    thin_draw_backfilled: int = 0
    filtered_unlabelled: int = 0
    unfiltered_unlabelled: int = 0
    thin_draw_unlabelled: int = 0
    expect: tuple[str, ...] = ()
    error: str | None = None

    def hit(self, window_parents: list[str]) -> bool:
        """True when an expected parent is among those reaching the prompt.

        Takes an ALREADY window-scoped parent list — see the field comments.
        """
        return any(uid in window_parents for uid in self.expect)

    def to_dict(self) -> RowReport:
        return {
            "query": self.query,
            "kind": self.kind,
            "intent": self.intent,
            "intent_score": round(self.intent_score, 4),
            "filter_types": self.filter_types,
            "filtered_chunks": self.filtered_chunks,
            "filtered_hit": self.hit(self.filtered_window_parents),
            "thin_draw_chunks": self.thin_draw_chunks,
            "thin_draw_hit": self.hit(self.thin_draw_window_parents),
            "thin_draw_backfilled": self.thin_draw_backfilled,
            "unfiltered_chunks": self.unfiltered_chunks,
            "unfiltered_hit": self.hit(self.unfiltered_window_parents),
            "filtered_unlabelled": self.filtered_unlabelled,
            "thin_draw_unlabelled": self.thin_draw_unlabelled,
            "unfiltered_unlabelled": self.unfiltered_unlabelled,
            "error": self.error,
        }


def backfill(
    filtered: list["SemanticSearchChunkResult"],
    unfiltered: list["SemanticSearchChunkResult"],
    k: int,
) -> tuple[list["SemanticSearchChunkResult"], int]:
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


def parents_of(hits: list["SemanticSearchChunkResult"]) -> list[str]:
    """Distinct parent uids in draw order (pure, DB-free).

    Callers must slice the CHUNK list to the prompt window BEFORE calling this —
    deduping first and slicing after promotes a parent that production truncated
    away.
    """
    ordered: list[str] = []
    for hit in hits:
        parent = str(hit.get("parent_uid") or "")
        if parent and parent not in ordered:
            ordered.append(parent)
    return ordered


def summarize(rows: list[DrawRow], query_set: QuerySet, viewer_uid: str | None) -> ComparisonReport:
    """Aggregate per-query rows into the report dict (pure, DB-free)."""
    from core.constants import IntelligenceThreshold

    scored = [row for row in rows if row.error is None]
    total = len(scored)

    def arm(parents_attr: str, chunks_attr: str, unlabelled_attr: str) -> ArmReport:
        """One arm's aggregate. `parents_attr` names a WINDOW-scoped parent list."""
        hits = sum(1 for row in scored if row.hit(getattr(row, parents_attr)))
        drawn = [getattr(row, chunks_attr) for row in scored]
        return {
            "hits": hits,
            "recall_at_k": round(hits / total, 4) if total else 0.0,
            "mean_chunks_drawn": round(sum(drawn) / total, 2) if total else 0.0,
            # A draw too thin to fill the PROMPT window — the starvation that
            # actually costs Askesis context. A draw of 4 is not starved: the
            # prompt only ever receives 3.
            "starved_queries": sum(1 for n in drawn if n < ASKESIS_PROMPT_WINDOW),
            "unlabelled_in_windows": sum(getattr(row, unlabelled_attr) for row in scored),
        }

    return {
        "query_set_version": query_set.version,
        "ratified": query_set.ratified,
        "k": ASKESIS_PROMPT_WINDOW,
        "draw_limit": ASKESIS_LIMIT,
        "viewer_uid": viewer_uid,
        "query_count": total,
        "errors": len(rows) - total,
        # Any arm's unlabelled chunk must raise the caveat — a note that sits
        # in only ONE arm's window is exactly the case that biases a delta.
        "unlabelled_chunks_drawn": sum(
            row.filtered_unlabelled + row.thin_draw_unlabelled + row.unfiltered_unlabelled
            for row in scored
        ),
        "intent_threshold": IntelligenceThreshold.INTENT_CLASSIFICATION,
        "max_intent_score": round(max((row.intent_score for row in scored), default=0.0), 4),
        "filtered_intent_queries": sum(1 for row in scored if row.filter_types is not None),
        "arms": {
            "filtered": arm("filtered_window_parents", "filtered_chunks", "filtered_unlabelled"),
            "thin_draw": arm(
                "thin_draw_window_parents", "thin_draw_chunks", "thin_draw_unlabelled"
            ),
            "unfiltered": arm(
                "unfiltered_window_parents", "unfiltered_chunks", "unfiltered_unlabelled"
            ),
        },
        "rows": [row.to_dict() for row in rows],
    }


async def measure_classification(
    classifier: "IntentClassifier", query: str
) -> "IntentClassification | str":
    """Classify one query through the OBSERVABLE classifier API.

    Not ``classify_intent``: that one is fail-soft in exactly the way this
    comparison must never score. It catches an embedding outage and returns
    ``Result.ok(SPECIFIC)``, byte-identical to a genuine low-confidence
    classification — so a provider blip would yield three identical unfiltered
    arms, ``errors = 0`` and ``filtered_intent_queries = 0``: the precise shape
    of the finding this script exists to test, manufactured out of an outage
    (Codex, PR #1198). ``classify_intent_scored`` fails loudly instead, and
    carries the score, so a run says WHY every query is SPECIFIC rather than
    only that it is.

    Returns the classification, or an error string that invalidates the row.
    """
    scored = await classifier.classify_intent_scored(query)
    if scored.is_error:
        return f"intent classification failed: {scored.expect_error()}"
    return scored.value


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
            measured = await measure_classification(classifier, eval_query.query)
            if isinstance(measured, str):
                # Classification could not be MEASURED. Scoring the row would
                # manufacture the very finding this script tests, so invalidate.
                rows.append(
                    DrawRow(
                        query=eval_query.query,
                        kind=eval_query.kind,
                        intent="unmeasured",
                        intent_score=0.0,
                        filter_types=None,
                        expect=eval_query.expect,
                        error=measured,
                    )
                )
                continue
            filter_types = _intent_to_chunk_types(measured.intent)
            row = DrawRow(
                query=eval_query.query,
                kind=eval_query.kind,
                intent=measured.intent.value,
                intent_score=measured.score,
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
            # Slice the CHUNK list to the prompt window first — production
            # truncates chunks, not parents (context_retriever.py:299).
            row.filtered_window_parents = parents_of(filtered_hits[:ASKESIS_PROMPT_WINDOW])
            row.unfiltered_window_parents = parents_of(
                list(unfiltered.value)[:ASKESIS_PROMPT_WINDOW]
            )
            row.thin_draw_window_parents = parents_of(merged[:ASKESIS_PROMPT_WINDOW])
            row.filtered_unlabelled = unlabelled_in_window(filtered_hits)
            row.unfiltered_unlabelled = unlabelled_in_window(list(unfiltered.value))
            row.thin_draw_unlabelled = unlabelled_in_window(merged)
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
    print(
        f"Queries: {report['query_count']}   recall@{report['k']} (prompt window)   "
        f"draw limit {report['draw_limit']}   min_score={ASKESIS_MIN_SCORE}"
    )
    if report["viewer_uid"] and report["unlabelled_chunks_drawn"]:
        print(
            f"\n!! {report['unlabelled_chunks_drawn']} chunk(s), summed across the arms'\n"
            f"!! scored windows, come from UNLABELLED parents (this viewer's own notes).\n"
            f"!! They are real production competition, but the set labels only published\n"
            f"!! Ku/PathStep, so they can displace a hit and never score as one. See the\n"
            f"!! per-arm 'unlabelled' column: a count that differs BETWEEN arms biases the\n"
            f"!! delta. Read recall as a curriculum-recall proxy; run without --user for\n"
            f"!! the label-consistent number."
        )
    if report["errors"]:
        print(f"ERRORS: {report['errors']}")

    if report["query_count"] and not report["filtered_intent_queries"]:
        print(
            f"\n!! NO QUERY IN THIS SET REACHED A FILTERED INTENT — every one\n"
            f"!! classified to an unmapped intent, so all three arms ran the SAME\n"
            f"!! unfiltered draw. The equal recall below is an identity, not a\n"
            f"!! finding about filtering.\n"
            f"!! Best similarity reached by any query here: "
            f"{report['max_intent_score']:.3f} vs a {report['intent_threshold']:.2f} gate.\n"
            f"!! That is a fact about THIS set. Whether the gate is reachable AT ALL\n"
            f"!! is a separate, set-independent question — argued from the\n"
            f"!! classifier's own exemplars in deferred-work.md § Per-Domain\n"
            f"!! Chunking Knobs (a verbatim exemplar reaches only 0.43-0.56)."
        )

    print(
        f"\n{'arm':<12} {'recall@' + str(report['k']):>9} {'hits':>6} "
        f"{'mean drawn':>11} {'starved':>8} {'unlabelled':>11}"
    )
    for name in ARMS:
        a = report["arms"][name]
        print(
            f"{name:<12} {a['recall_at_k']:>8.1%} {a['hits']:>6} "
            f"{a['mean_chunks_drawn']:>11.2f} {a['starved_queries']:>8} "
            f"{a['unlabelled_in_windows']:>11}"
        )

    print(
        f"\nPer query (F=filtered, T=thin-draw, U=unfiltered; score vs "
        f"{report['intent_threshold']:.2f} gate):"
    )
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
            f"  {marks:<4} {row['query'][:38]:<38} {row['intent']:<12} "
            f"{row['intent_score']:.3f} "
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

    if args.as_json:
        # Redirect the ENTIRE async lifecycle to stderr (same rationale as
        # eval_chunk_retrieval.py): logging binds sys.stdout at configure time,
        # so the driver's connect/close lines would otherwise sit either side of
        # the report and make the output unparseable as one JSON document.
        with contextlib.redirect_stdout(sys.stderr):
            exit_code, report = asyncio.run(
                run_comparison(query_set, viewer_uid=args.user, as_json=True)
            )
        if report is not None:
            print(json.dumps(report, indent=2))
        return exit_code

    exit_code, report = asyncio.run(run_comparison(query_set, viewer_uid=args.user, as_json=False))
    if report is not None:
        _print_human(report)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
