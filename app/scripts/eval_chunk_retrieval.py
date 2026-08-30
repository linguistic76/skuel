#!/usr/bin/env python3
"""Chunk-retrieval eval — hit@k through the ONE /search path that reaches lesson bodies.

The instrument gating the chunking-knob work in docs/roadmap/deferred-work.md
§ "Per-Domain Chunking Knobs + Chunk-Type-Aware Retrieval" (Named work 2):
before any ``chunking_params`` change, a measured baseline; after one, the same
measurement again. Its first RATIFIED run is the baseline.

What it drives — and why exactly that:
  - ``SearchRouter.faceted_search`` with ``enable_semantic_boost=True`` — the
    sole caller of ``_augment_with_body_chunks``, i.e. the only /search path on
    which a :ContentChunk can influence what a user sees. ``advanced_search``
    searches parent entities and never touches a chunk, so a baseline through
    it would be blind to every knob this instrument exists to measure.
  - ``entity_types=[KU, PATH_STEP]`` — the two body-chunk domains, so both are
    eligible for the fold; expected hits are Ku/PathStep uids.
  - ``user_uid=None`` — the /search body fold is viewer-less by design
    (ADR-085 G8): published curriculum only. Both domains are PUBLIC, so the
    anonymous sweep is the production shape.
  - ``log_event=False`` — an eval run must never write :SearchEvent telemetry;
    the real 41-row usage record stays unpolluted.

Scoring: a query is a hit when ANY of its expected uids appears in the top k
(k from the query set, default 5) of the merged result list, in the order
production returns it — frontmatter results first, body-fold parents appended.
Per-query rows record the rank and whether the hit arrived via the lesson-body
fold (``_match_reason``), which is the trace PR-2 needs to attribute a miss to
chunk grain rather than to the frontmatter path.

Query set: scripts/eval_chunk_retrieval_queries.yaml (reviewable, checked in;
it evolves under review — this script does not). Runs print a DRAFT banner
until the set carries a ``ratified:`` date.

Usage:
    uv run python scripts/eval_chunk_retrieval.py             # human summary
    uv run python scripts/eval_chunk_retrieval.py --json      # machine output
    uv run python scripts/eval_chunk_retrieval.py --queries other_set.yaml

Requires INTELLIGENCE_TIER=full (query embedding); refuses to run on CORE
rather than silently measure frontmatter CONTAINS alone. Read-only apart from
the query-embedding API calls.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TypedDict

import yaml

DEFAULT_QUERY_SET = Path(__file__).parent / "eval_chunk_retrieval_queries.yaml"

# Production /search default (SearchRequest.limit). The base results are capped
# here BEFORE body-fold parents are appended, so this shapes ranks exactly as
# the page does.
REQUEST_LIMIT = 20

VALID_KINDS = frozenset({"real_usage", "body_paraphrase", "title_control"})


class KindReport(TypedDict):
    """Per-kind aggregate in the report."""

    queries: int
    hits: int
    hit_at_k: float
    hits_via_body: int


class RowReport(TypedDict):
    """One query's outcome, as serialized into the report."""

    query: str
    kind: str
    hit: bool
    best_rank: int | None
    matched_uid: str | None
    via_body: bool
    result_count: int
    body_result_count: int
    chunk_candidates: int
    expected_missing: list[str]
    error: str | None


class EvalReport(TypedDict):
    """The full eval report — the JSON contract of a recorded run."""

    query_set_version: int
    ratified: str | None
    k: int
    query_count: int
    errors: int
    hits: int
    hit_at_k: float
    hits_via_body: int
    by_kind: dict[str, KindReport]
    rows: list[RowReport]


@dataclass(frozen=True)
class EvalQuery:
    """One reviewable query → expected-hits claim from the query set."""

    query: str
    kind: str
    expect: tuple[str, ...]
    note: str


@dataclass(frozen=True)
class QuerySet:
    """The parsed, validated query-set file."""

    version: int
    ratified: str | None
    k: int
    queries: tuple[EvalQuery, ...]


@dataclass
class QueryRow:
    """Outcome of one query against the live search path."""

    query: str
    kind: str
    hit: bool
    best_rank: int | None
    matched_uid: str | None
    via_body: bool
    result_count: int
    body_result_count: int
    expected_missing: list[str]
    chunk_candidates: int = 0
    error: str | None = None

    def to_dict(self) -> RowReport:
        return {
            "query": self.query,
            "kind": self.kind,
            "hit": self.hit,
            "best_rank": self.best_rank,
            "matched_uid": self.matched_uid,
            "via_body": self.via_body,
            "result_count": self.result_count,
            "body_result_count": self.body_result_count,
            "chunk_candidates": self.chunk_candidates,
            "expected_missing": self.expected_missing,
            "error": self.error,
        }


@dataclass
class KindSummary:
    queries: int = 0
    hits: int = 0
    hits_via_body: int = 0
    ranks: list[int] = field(default_factory=list)


def load_query_set(path: Path) -> QuerySet:
    """Parse and validate the query-set YAML; every defect is a loud ValueError.

    The set is hand-edited under review, so this validation is its only
    structural gate — precise messages over lenient parsing.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top level must be a mapping")

    version = raw.get("version")
    if not isinstance(version, int):
        raise ValueError(f"{path}: 'version' must be an integer")

    # The ratification gate must be unforgeable by a typo: the FIRST ratified
    # run becomes the baseline, so `ratified: false`/`yes`/a list must never
    # coerce into a truthy "ratified" string. Only null, a bare YAML date
    # (parsed to datetime.date), or a quoted ISO date pass.
    ratified = raw.get("ratified")
    ratified_str: str | None
    if ratified is None:
        ratified_str = None
    elif isinstance(ratified, date):
        ratified_str = ratified.isoformat()
    elif isinstance(ratified, str):
        try:
            date.fromisoformat(ratified)
        except ValueError:
            raise ValueError(
                f"{path}: 'ratified' must be null or an ISO date (YYYY-MM-DD), got {ratified!r}"
            ) from None
        ratified_str = ratified
    else:
        raise ValueError(
            f"{path}: 'ratified' must be null or an ISO date (YYYY-MM-DD), got {ratified!r}"
        )

    k = raw.get("k")
    if not isinstance(k, int) or k < 1:
        raise ValueError(f"{path}: 'k' must be a positive integer")

    entries = raw.get("queries")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path}: 'queries' must be a non-empty list")

    queries: list[EvalQuery] = []
    seen_texts: set[str] = set()
    for i, entry in enumerate(entries):
        where = f"{path}: queries[{i}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where}: must be a mapping")
        text = entry.get("query")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{where}: 'query' must be a non-empty string")
        if text in seen_texts:
            raise ValueError(f"{where}: duplicate query text {text!r}")
        seen_texts.add(text)
        kind = entry.get("kind")
        if kind not in VALID_KINDS:
            raise ValueError(f"{where}: 'kind' must be one of {sorted(VALID_KINDS)}, got {kind!r}")
        expect = entry.get("expect")
        if not isinstance(expect, list) or not expect:
            raise ValueError(f"{where}: 'expect' must be a non-empty list of uids")
        if not all(isinstance(u, str) and u.strip() for u in expect):
            raise ValueError(f"{where}: every 'expect' entry must be a non-empty string")
        if len(set(expect)) != len(expect):
            raise ValueError(f"{where}: duplicate uids in 'expect'")
        note = entry.get("note", "")
        if not isinstance(note, str):
            raise ValueError(f"{where}: 'note' must be a string")
        queries.append(EvalQuery(query=text, kind=kind, expect=tuple(expect), note=note))

    return QuerySet(version=version, ratified=ratified_str, k=k, queries=tuple(queries))


def score_query(
    eval_query: EvalQuery,
    ordered_uids: list[str],
    body_uids: set[str],
    k: int,
    chunk_candidates: int = 0,
) -> QueryRow:
    """Score one query's live results against its expected uids (pure, DB-free).

    Rank is 1-based position in the merged production ordering. The hit is the
    BEST-ranked expected uid; ``via_body`` says whether that specific card came
    from the lesson-body fold.
    """
    rank_by_uid = {uid: i + 1 for i, uid in enumerate(ordered_uids) if uid in eval_query.expect}
    best_uid: str | None = None
    best_rank: int | None = None
    for uid, rank in rank_by_uid.items():
        if best_rank is None or rank < best_rank:
            best_uid, best_rank = uid, rank
    hit = best_rank is not None and best_rank <= k
    return QueryRow(
        query=eval_query.query,
        kind=eval_query.kind,
        hit=hit,
        best_rank=best_rank,
        matched_uid=best_uid,
        via_body=hit and best_uid in body_uids,
        result_count=len(ordered_uids),
        body_result_count=len(body_uids),
        expected_missing=[u for u in eval_query.expect if u not in rank_by_uid],
        chunk_candidates=chunk_candidates,
    )


def summarize(rows: list[QueryRow], query_set: QuerySet) -> EvalReport:
    """Aggregate per-query rows into the report dict (pure, DB-free)."""
    by_kind: dict[str, KindSummary] = {}
    hits = 0
    hits_via_body = 0
    errors = 0
    for row in rows:
        summary = by_kind.setdefault(row.kind, KindSummary())
        summary.queries += 1
        if row.error is not None:
            errors += 1
            continue
        if row.hit:
            hits += 1
            summary.hits += 1
            if row.via_body:
                hits_via_body += 1
                summary.hits_via_body += 1
            if row.best_rank is not None:
                summary.ranks.append(row.best_rank)
    total = len(rows)
    return {
        "query_set_version": query_set.version,
        "ratified": query_set.ratified,
        "k": query_set.k,
        "query_count": total,
        "errors": errors,
        "hits": hits,
        "hit_at_k": round(hits / total, 4) if total else 0.0,
        "hits_via_body": hits_via_body,
        "by_kind": {
            kind: {
                "queries": s.queries,
                "hits": s.hits,
                "hit_at_k": round(s.hits / s.queries, 4) if s.queries else 0.0,
                "hits_via_body": s.hits_via_body,
            }
            for kind, s in sorted(by_kind.items())
        },
        "rows": [row.to_dict() for row in rows],
    }


async def run_eval(query_set: QuerySet, *, as_json: bool) -> tuple[int, EvalReport | None]:
    """Compose services, drive faceted_search per query, and return (exit_code, report)."""
    from adapters.infrastructure.event_bus import InMemoryEventBus
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from core.models.enums.entity_enums import EntityType
    from core.models.search_request import BODY_HIT_MATCH_REASON, SearchRequest
    from services_bootstrap import compose_services

    if not as_json:
        print("Connecting to Neo4j...")
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        composed = await compose_services(adapter, InMemoryEventBus())
        if composed.is_error:
            print(f"ERROR: composition failed: {composed.expect_error()}", file=sys.stderr)
            return 1, None

        router = composed.value.search_router
        if router is None:
            print("ERROR: search router is not wired", file=sys.stderr)
            return 1, None
        vector_search = composed.value.vector_search_service
        if vector_search is None:
            # Without vector search the body fold silently no-ops and this
            # instrument would "measure" frontmatter CONTAINS alone — the
            # predictable wrong-firing mode, so refuse instead.
            print(
                "ERROR: vector search unavailable — this eval requires "
                "INTELLIGENCE_TIER=full (query embedding). Refusing to run a "
                "chunk-blind baseline.",
                file=sys.stderr,
            )
            return 2, None

        rows: list[QueryRow] = []
        for eval_query in query_set.queries:
            request = SearchRequest(
                query_text=eval_query.query,
                entity_types=[EntityType.KU, EntityType.PATH_STEP],
                enable_semantic_boost=True,
                limit=REQUEST_LIMIT,
            )
            # Body-search canary (Codex, PR #1197): the production fold fails
            # SOFT by design — a /search user must still get frontmatter results
            # when embedding or chunk retrieval breaks — so inside faceted_search
            # a dead Digital layer is invisible and every query would quietly
            # score as a frontmatter-only run. Prove each query's body search
            # completes, with the SAME inputs the fold uses; a probe failure
            # invalidates the row (and the run, via errors → exit 1).
            probe = await vector_search.find_similar_chunks_by_text(
                text=eval_query.query,
                limit=request.limit,
                min_score=vector_search.config.body_chunk_search_min_score,
                parent_filters=request.to_property_filters(),
            )
            if probe.is_error:
                rows.append(
                    QueryRow(
                        query=eval_query.query,
                        kind=eval_query.kind,
                        hit=False,
                        best_rank=None,
                        matched_uid=None,
                        via_body=False,
                        result_count=0,
                        body_result_count=0,
                        expected_missing=list(eval_query.expect),
                        error=f"body-chunk search failed: {probe.expect_error()}",
                    )
                )
                continue

            result = await router.faceted_search(request, user_uid=None, log_event=False)
            if result.is_error:
                rows.append(
                    QueryRow(
                        query=eval_query.query,
                        kind=eval_query.kind,
                        hit=False,
                        best_rank=None,
                        matched_uid=None,
                        via_body=False,
                        result_count=0,
                        body_result_count=0,
                        expected_missing=list(eval_query.expect),
                        error=str(result.expect_error()),
                    )
                )
                continue
            cards = result.value.results
            ordered_uids = [str(card.get("uid", "")) for card in cards]
            body_uids = {
                str(card.get("uid", ""))
                for card in cards
                if card.get("_match_reason") == BODY_HIT_MATCH_REASON
            }
            rows.append(
                score_query(
                    eval_query,
                    ordered_uids,
                    body_uids,
                    query_set.k,
                    chunk_candidates=len(probe.value),
                )
            )

        report = summarize(rows, query_set)
        return (1 if report["errors"] else 0), report
    finally:
        await adapter.close()


def _print_human(report: EvalReport) -> None:
    """Render the report as a readable console summary."""
    k = report["k"]
    if report["ratified"]:
        print(
            f"\n=== Chunk-Retrieval Eval (set v{report['query_set_version']}, "
            f"ratified {report['ratified']}) ==="
        )
    else:
        print(f"\n=== Chunk-Retrieval Eval (set v{report['query_set_version']}) ===")
        print("⚠ DRAFT query set — pairs not yet ratified; this run is NOT a baseline.")
    print()

    for row in report["rows"]:
        if row["error"] is not None:
            print(f"  ✗ ERROR  {row['query']!r}: {row['error']}")
            continue
        if row["hit"]:
            via = "body-fold" if row["via_body"] else "frontmatter"
            print(f"  ✓ hit@{row['best_rank']:<3}{row['query']!r} → {row['matched_uid']} ({via})")
        else:
            ranked = (
                f"best expected rank {row['best_rank']}"
                if row["best_rank"]
                else "no expected uid returned"
            )
            print(
                f"  ✗ MISS   {row['query']!r} — {ranked} of {row['result_count']} results"
                f" ({row['chunk_candidates']} chunk candidates)"
            )

    print(
        f"\nhit@{k}: {report['hits']}/{report['query_count']}"
        f" ({report['hit_at_k']:.0%}) — {report['hits_via_body']} via lesson-body fold"
    )
    for kind, s in report["by_kind"].items():
        print(
            f"  {kind + ':':<18} {s['hits']}/{s['queries']} ({s['hit_at_k']:.0%})"
            f" — {s['hits_via_body']} via body"
        )
    if report["errors"]:
        print(f"\n⚠ {report['errors']} query(ies) errored — run is not a valid measurement.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="hit@k eval of /search chunk retrieval (deferred-work § chunking knobs)."
    )
    parser.add_argument(
        "--queries",
        type=Path,
        default=DEFAULT_QUERY_SET,
        help=f"query-set YAML (default: {DEFAULT_QUERY_SET.name})",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit the raw report as JSON instead of a summary"
    )
    args = parser.parse_args()

    try:
        query_set = load_query_set(args.queries)
    except (ValueError, OSError, yaml.YAMLError) as e:
        print(f"ERROR: invalid query set: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        # Redirect the ENTIRE async lifecycle to stderr (same rationale as
        # knowledge_health_report.py): logging binds sys.stdout at configure
        # time, so the JSON printed after the guard is the only stdout content.
        with contextlib.redirect_stdout(sys.stderr):
            code, report = asyncio.run(run_eval(query_set, as_json=True))
        if report is not None:
            print(json.dumps(report, indent=2))
        sys.exit(code)

    code, report = asyncio.run(run_eval(query_set, as_json=False))
    if report is not None:
        _print_human(report)
    sys.exit(code)


if __name__ == "__main__":
    main()
