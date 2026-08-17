"""SearchRouter's hybrid fulltext+vector rung — eligibility and fallback.

The rung is label-wide: ``hybrid_search`` composes no ``user_uid``, so an
OWNER_ONLY domain reaching it would return every user's nodes. Eligibility is
therefore belt-and-braces — an explicit curriculum allowlist AND a live
``search_visibility`` read — and both halves are asserted here independently,
because either one alone would admit a domain the other refuses.

The rung also must never turn a working search into a broken one: every
ineligible/empty/failed path falls through to the domain's CONTAINS search.

``TestRealServicesQualify`` is the half doubles cannot cover: every test above
builds a service that satisfies the protocol BY CONSTRUCTION, so all of them
would still pass if the real Ku/PS/LP services stopped qualifying and the rung
went quietly dead.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config.unified_config import VectorSearchConfig
from core.models.enums import SearchVisibility
from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.search_request import SearchRequest
from core.orchestrator.search_router import SearchResultItem, SearchRouter
from core.ports.search_protocols import SupportsVisibilityDeclaration
from core.services.ku.ku_search_service import KuSearchService
from core.services.lp.lp_search_service import LpSearchService
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
from core.services.ps.ps_search_service import PsSearchService
from core.utils.result_simplified import Errors, Result

# Realistic RRF output for the default k=60 / 50-50 weighting. `alpha` is
# ranked first by BOTH halves (0.5/61 + 0.5/61, the theoretical ceiling);
# `beta` by one half only, so it scores exactly half as much. Using arbitrary
# larger numbers here would silently exercise the clamp instead of the scale.
HYBRID_ROWS: list[dict[str, Any]] = [
    {
        "node": {"uid": "ps.alpha", "title": "Alpha"},
        "score": 1.0 / 61,
        "matched_vector": True,
        "matched_fulltext": True,
    },
    {
        "node": {"uid": "ps.beta", "title": "Beta"},
        "score": 0.5 / 61,
        "matched_vector": False,
        "matched_fulltext": True,
    },
]


def _search_service(
    visibility: SearchVisibility = SearchVisibility.PUBLIC,
    contains_rows: list[Any] | None = None,
) -> SimpleNamespace:
    """A domain search sub-service double: CONTAINS search + visibility declaration."""
    return SimpleNamespace(
        search=AsyncMock(return_value=Result.ok(contains_rows or [])),
        search_visibility=visibility,
    )


def _vector_search(
    result: Result[list[dict[str, Any]]] | None = None,
    embedding: Result[list[float]] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        hybrid_search_with_metrics=AsyncMock(
            return_value=(result if result is not None else Result.ok(HYBRID_ROWS), None)
        ),
        embed_query=AsyncMock(
            return_value=embedding if embedding is not None else Result.ok([0.1, 0.2, 0.3])
        ),
        # The real property — a hand-picked constant here would let the router
        # and the service drift apart without any test noticing.
        max_rrf_score=Neo4jVectorSearchService(
            backend=MagicMock(), config=VectorSearchConfig()
        ).max_rrf_score,
    )


def _router(vector_search: Any = None) -> SearchRouter:
    return SearchRouter(vector_search_service=vector_search)


async def _run(
    router: SearchRouter, service: Any, entity_type: EntityType, query: str = "photosynthesis"
) -> list[Any]:
    return await router._hybrid_curriculum_search(
        search_service=service,
        entity_type=entity_type,
        request=SearchRequest(query_text=query),
        limit=10,
    )


class TestEligibility:
    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "entity_type",
        [EntityType.KU, EntityType.PATH_STEP, EntityType.LEARNING_PATH],
    )
    async def test_public_curriculum_domains_use_the_rung(self, entity_type: EntityType) -> None:
        vector_search = _vector_search()
        items = await _run(_router(vector_search), _search_service(), entity_type)

        assert [item.uid for item in items] == ["ps.alpha", "ps.beta"]
        vector_search.hybrid_search_with_metrics.assert_awaited_once()

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "entity_type",
        [EntityType.TASK, EntityType.GOAL, EntityType.HABIT, EntityType.USER_ENTRY],
    )
    async def test_owner_owned_domains_never_reach_the_rung(self, entity_type: EntityType) -> None:
        """The allowlist half: hybrid_search has no user_uid to scope with."""
        vector_search = _vector_search()
        items = await _run(_router(vector_search), _search_service(), entity_type)

        assert items == []
        vector_search.hybrid_search_with_metrics.assert_not_awaited()

    @pytest.mark.anyio
    async def test_non_public_visibility_is_refused_even_when_allowlisted(self) -> None:
        """The live-read half: a domain whose declaration changes stops qualifying."""
        vector_search = _vector_search()
        service = _search_service(visibility=SearchVisibility.OWNER_ONLY)

        items = await _run(_router(vector_search), service, EntityType.KU)

        assert items == []
        vector_search.hybrid_search_with_metrics.assert_not_awaited()

    @pytest.mark.anyio
    async def test_service_without_a_visibility_declaration_is_refused(self) -> None:
        """Fail closed: no declaration to read means no proof the domain is public."""
        vector_search = _vector_search()
        service = SimpleNamespace(search=AsyncMock(return_value=Result.ok([])))

        items = await _run(_router(vector_search), service, EntityType.KU)

        assert items == []
        vector_search.hybrid_search_with_metrics.assert_not_awaited()

    @pytest.mark.anyio
    async def test_core_tier_falls_through(self) -> None:
        """No vector service (INTELLIGENCE_TIER=core) — D3 keeps CORE on CONTAINS."""
        items = await _run(_router(vector_search=None), _search_service(), EntityType.KU)

        assert items == []

    @pytest.mark.anyio
    async def test_empty_query_text_falls_through(self) -> None:
        vector_search = _vector_search()
        items = await _run(
            _router(vector_search),
            _search_service(),
            EntityType.KU,
            query="x",
        )
        # Sanity: a non-empty query DOES reach it (guards the assertion below).
        assert items
        vector_search.hybrid_search_with_metrics.reset_mock()

        result = await _router(vector_search)._hybrid_curriculum_search(
            search_service=_search_service(),
            entity_type=EntityType.KU,
            request=SearchRequest(domain=None),
            limit=10,
        )

        assert result == []
        vector_search.hybrid_search_with_metrics.assert_not_awaited()


class TestFallback:
    @pytest.mark.anyio
    async def test_hybrid_failure_falls_through(self) -> None:
        failed: Result[list[dict[str, Any]]] = Result.fail(
            Errors.database(operation="hybrid_search", message="index unavailable")
        )
        items = await _run(_router(_vector_search(failed)), _search_service(), EntityType.KU)

        assert items == []

    @pytest.mark.anyio
    async def test_empty_hybrid_result_falls_through(self) -> None:
        items = await _run(_router(_vector_search(Result.ok([]))), _search_service(), EntityType.KU)

        assert items == []

    @pytest.mark.anyio
    async def test_strategy_3_runs_contains_when_the_rung_declines(self) -> None:
        """End of the ladder: an ineligible domain still gets its normal search."""
        service = _search_service(
            visibility=SearchVisibility.OWNER_ONLY,
            contains_rows=[SimpleNamespace(uid="task_1", title="Water the plants", tags=())],
        )
        router = _router(_vector_search())

        items = await router._execute_advanced_search(
            search_service=service,
            entity_type=EntityType.TASK,
            request=SearchRequest(query_text="plants"),
            limit_per_domain=10,
        )

        service.search.assert_awaited_once()
        assert [item.uid for item in items] == ["task_1"]

    @pytest.mark.anyio
    async def test_a_full_hybrid_page_short_circuits_contains(self) -> None:
        """A rung result that already fills the budget does not also run CONTAINS."""
        service = _search_service()
        router = _router(_vector_search())

        items = await router._execute_advanced_search(
            search_service=service,
            entity_type=EntityType.KU,
            request=SearchRequest(query_text="photosynthesis"),
            limit_per_domain=len(HYBRID_ROWS),
        )

        service.search.assert_not_awaited()
        assert [item.uid for item in items] == ["ps.alpha", "ps.beta"]


class TestContainsBackfill:
    """A SHORT hybrid page is topped up, because Lucene and CONTAINS miss differently.

    Lucene matches whole tokens, so a partial word ("photosyn") finds nothing
    where a substring scan finds the entity. Returning early on ANY hybrid hit
    dropped those matches — the regression this class pins.
    """

    @pytest.mark.anyio
    async def test_substring_only_match_survives_a_partial_hybrid_hit(self) -> None:
        """The regression: a hybrid hit must not hide the substring match beside it."""
        service = _search_service(
            contains_rows=[
                SimpleNamespace(uid="ps.alpha", title="Alpha"),  # already ranked
                SimpleNamespace(uid="ps.gamma", title="Running technique"),  # Lucene missed
            ]
        )
        router = _router(_vector_search())

        items = await router._execute_advanced_search(
            search_service=service,
            entity_type=EntityType.KU,
            request=SearchRequest(query_text="run"),
            limit_per_domain=10,
        )

        service.search.assert_awaited_once()
        # Hybrid keeps the lead and its order; the substring-only hit is recovered
        # exactly once — `ps.alpha` came back from both halves.
        assert [item.uid for item in items] == ["ps.alpha", "ps.beta", "ps.gamma"]

    @pytest.mark.anyio
    async def test_backfilled_hits_never_outrank_relevance_ranked_ones(self) -> None:
        """Recall is recovered without a substring match jumping the ranking."""
        service = _search_service(
            contains_rows=[SimpleNamespace(uid="ps.gamma", title="Running technique")]
        )
        router = _router(_vector_search())

        items = await router._execute_advanced_search(
            search_service=service,
            entity_type=EntityType.KU,
            request=SearchRequest(query_text="run"),
            limit_per_domain=10,
        )

        by_uid = {item.uid: item for item in items}
        assert by_uid["ps.gamma"].relevance_score == 0.0
        assert by_uid["ps.gamma"].combined_score < by_uid["ps.beta"].combined_score

    @pytest.mark.anyio
    async def test_backfill_respects_the_per_domain_budget(self) -> None:
        """The rung's two hits plus one filler is the whole budget — no overflow."""
        service = _search_service(
            contains_rows=[
                SimpleNamespace(uid=f"ps.fill{n}", title=f"Filler {n}") for n in range(5)
            ]
        )
        router = _router(_vector_search())

        items = await router._execute_advanced_search(
            search_service=service,
            entity_type=EntityType.KU,
            request=SearchRequest(query_text="run"),
            limit_per_domain=3,
        )

        assert len(items) == 3
        assert [item.uid for item in items] == ["ps.alpha", "ps.beta", "ps.fill0"]

    @pytest.mark.anyio
    async def test_an_empty_rung_still_yields_plain_contains_results(self) -> None:
        """The ineligible/empty path is unchanged — backfill is not a new gate."""
        service = _search_service(
            contains_rows=[SimpleNamespace(uid="ps.only", title="Only match")]
        )
        router = _router(_vector_search(Result.ok([])))

        items = await router._execute_advanced_search(
            search_service=service,
            entity_type=EntityType.KU,
            request=SearchRequest(query_text="run"),
            limit_per_domain=10,
        )

        assert [item.uid for item in items] == ["ps.only"]

    @pytest.mark.anyio
    async def test_heavy_overlap_still_fills_the_page(self) -> None:
        """The fetch budget is sufficient without over-fetching for overlap.

        The domain applies its LIMIT before the dedupe, so most of the fetched
        page can be rows the rung already returned. That cannot starve the
        backfill: overlaps can never exceed the hybrid count, so at least
        `limit - len(hybrid)` fresh rows survive — exactly the budget left.
        Asserted here at the tightest ratio (2 of 3 fetched rows are overlaps).
        """
        service = _search_service(
            contains_rows=[
                SimpleNamespace(uid="ps.alpha", title="Alpha"),  # overlap
                SimpleNamespace(uid="ps.beta", title="Beta"),  # overlap
                SimpleNamespace(uid="ps.gamma", title="Running technique"),
            ]
        )
        router = _router(_vector_search())

        items = await router._execute_advanced_search(
            search_service=service,
            entity_type=EntityType.KU,
            request=SearchRequest(query_text="run"),
            limit_per_domain=3,
        )

        assert service.search.await_args is not None
        assert service.search.await_args.args[1] == 3, "no over-fetch needed"
        assert [item.uid for item in items] == ["ps.alpha", "ps.beta", "ps.gamma"]

    def test_a_falsy_uid_is_kept_rather_than_deduped_away(self) -> None:
        """A degraded node property must not cost a result."""
        merged = SearchRouter._backfill_with_contains(
            [SearchResultItem(entity={}, entity_type=EntityType.KU, uid="", title="Hybrid")],
            [SearchResultItem(entity={}, entity_type=EntityType.KU, uid="", title="Contains")],
            limit=10,
        )

        assert [item.title for item in merged] == ["Hybrid", "Contains"]


class TestResultMapping:
    @pytest.mark.anyio
    async def test_rrf_scores_are_normalized_onto_the_shared_ceiling(self) -> None:
        """RRF emits 0.001-0.05; every other rung emits ~0-1, and get_top_results
        compares combined scores ACROSS domains — unnormalized, hybrid always sinks.

        The divisor is the theoretical max (1/(k+1)), not this batch's max, so
        the score means the same thing in every domain.
        """
        items = await _run(_router(_vector_search()), _search_service(), EntityType.KU)

        ceiling = 1.0 / (VectorSearchConfig().rrf_k + 1)
        assert items[0].relevance_score == pytest.approx(HYBRID_ROWS[0]["score"] / ceiling)
        assert items[1].relevance_score == pytest.approx(HYBRID_ROWS[1]["score"] / ceiling)

    @pytest.mark.anyio
    async def test_a_weaker_domains_best_hit_does_not_score_1_point_0(self) -> None:
        """The per-batch-max bug: every domain's leader scored exactly 1.0, so
        Ku/PathStep/LearningPath tied at the top and iteration order decided the
        merged ranking — discarding the both-halves-agree signal entirely."""
        strong = [{"node": {"uid": "ku.top", "title": "Top"}, "score": 1.0 / 61}]
        weak = [{"node": {"uid": "ps.weak", "title": "Weak"}, "score": 0.5 / 61}]

        strong_items = await _run(
            _router(_vector_search(Result.ok(strong))), _search_service(), EntityType.KU
        )
        weak_items = await _run(
            _router(_vector_search(Result.ok(weak))), _search_service(), EntityType.PATH_STEP
        )

        assert strong_items[0].relevance_score == pytest.approx(1.0)
        assert weak_items[0].relevance_score == pytest.approx(0.5)
        assert weak_items[0].relevance_score < strong_items[0].relevance_score

    @pytest.mark.anyio
    async def test_odd_neo4j_property_types_degrade_rather_than_leak(self) -> None:
        """A Neo4j property map is heterogeneous — str/int/float/list/date/None.

        Typing the hit shape (Codex P1) exposed that uid/title/priority_score
        were being passed through unnarrowed. A non-string uid must become ""
        rather than reach the API as some other type.
        """
        rows: list[dict[str, Any]] = [
            {
                "node": {"uid": 12345, "title": ["a", "list"], "priority_score": "high"},
                "score": 0.5 / 61,
                "matched_vector": True,
                "matched_fulltext": True,
            }
        ]
        items = await _run(
            _router(_vector_search(Result.ok(rows))), _search_service(), EntityType.KU
        )

        assert items[0].uid == ""
        assert items[0].title == ""
        assert items[0].priority_score == 0.0

    @pytest.mark.anyio
    async def test_integer_priority_score_is_coerced_not_dropped(self) -> None:
        """Neo4j returns whole numbers as int; that IS a usable priority."""
        rows: list[dict[str, Any]] = [
            {
                "node": {"uid": "ku.a", "title": "A", "priority_score": 3},
                "score": 0.5 / 61,
                "matched_vector": True,
                "matched_fulltext": True,
            }
        ]
        items = await _run(
            _router(_vector_search(Result.ok(rows))), _search_service(), EntityType.KU
        )

        assert items[0].priority_score == 3.0

    @pytest.mark.anyio
    async def test_scores_are_clamped_to_one(self) -> None:
        """A score above the theoretical ceiling would be a bug upstream, but
        must not leak a >1 relevance into cross-domain comparison."""
        rows = [{"node": {"uid": "ku.a", "title": "A"}, "score": 99.0}]
        items = await _run(
            _router(_vector_search(Result.ok(rows))), _search_service(), EntityType.KU
        )

        assert items[0].relevance_score == 1.0

    @pytest.mark.anyio
    async def test_uid_and_title_survive_the_dict_shape(self) -> None:
        """Hybrid returns node DICTS — a getattr-based wrapper would blank both."""
        items = await _run(_router(_vector_search()), _search_service(), EntityType.KU)

        assert items[0].uid == "ps.alpha"
        assert items[0].title == "Alpha"
        assert items[0].entity_type is EntityType.KU

    @pytest.mark.anyio
    async def test_match_reason_reflects_which_half_matched(self) -> None:
        """RRF output carries no vector_score/semantic_boost — the vector rung's
        reason builder would silently produce an empty string here — and a fixed
        string would claim semantic understanding for a Lucene-only hit."""
        items = await _run(_router(_vector_search()), _search_service(), EntityType.KU)

        assert items[0].match_reason == "Keyword + semantic match"  # both halves
        assert items[1].match_reason == "Keyword match"  # fulltext only

    @pytest.mark.anyio
    async def test_fulltext_only_results_do_not_claim_semantic_matching(self) -> None:
        """The shipped LearningPath case: no vector index until the next FULL-tier
        boot, so every LP hit is Lucene's alone."""
        rows: list[dict[str, Any]] = [
            {
                "node": {"uid": "lp.a", "title": "A"},
                "score": 0.5 / 61,
                "matched_vector": False,
                "matched_fulltext": True,
            }
        ]
        items = await _run(
            _router(_vector_search(Result.ok(rows))), _search_service(), EntityType.LEARNING_PATH
        )

        assert items[0].match_reason == "Keyword match"
        assert "semantic" not in items[0].match_reason.lower()

    @pytest.mark.anyio
    async def test_vector_only_results_say_so(self) -> None:
        """The mirror case: a term Lucene missed but the embedding caught."""
        rows: list[dict[str, Any]] = [
            {
                "node": {"uid": "ku.a", "title": "A"},
                "score": 0.5 / 61,
                "matched_vector": True,
                "matched_fulltext": False,
            }
        ]
        items = await _run(
            _router(_vector_search(Result.ok(rows))), _search_service(), EntityType.KU
        )

        assert items[0].match_reason == "Semantic match"

    @pytest.mark.anyio
    async def test_zero_scores_do_not_divide_by_zero(self) -> None:
        rows = [{"node": {"uid": "ku.a", "title": "A"}, "score": 0.0}]
        items = await _run(
            _router(_vector_search(Result.ok(rows))), _search_service(), EntityType.KU
        )

        assert items[0].relevance_score == 0.0


class TestLabelDerivation:
    @pytest.mark.anyio
    async def test_multi_word_label_is_not_flattened(self) -> None:
        """`.capitalize()` produced "Path_step", which matches no index at all."""
        vector_search = _vector_search()
        await _run(_router(vector_search), _search_service(), EntityType.PATH_STEP)

        kwargs = vector_search.hybrid_search_with_metrics.await_args.kwargs
        assert kwargs["label"] == "PathStep"

    @pytest.mark.anyio
    async def test_learning_path_label(self) -> None:
        vector_search = _vector_search()
        await _run(_router(vector_search), _search_service(), EntityType.LEARNING_PATH)

        kwargs = vector_search.hybrid_search_with_metrics.await_args.kwargs
        assert kwargs["label"] == "LearningPath"


class TestQueryEmbeddingReuse:
    """One paid embed per request, not one per domain.

    `EmbeddingsService.create_embedding` is uncached, so an unfiltered sweep —
    which runs the rung for Ku, PathStep AND LearningPath — would otherwise
    issue the identical embedding request three times, sequentially (Codex,
    PR #1074).
    """

    @pytest.mark.anyio
    async def test_embedding_is_computed_once_for_all_eligible_domains(self) -> None:
        vector_search = _vector_search()
        router = _router(vector_search)
        request = SearchRequest(query_text="photosynthesis")
        domains = [EntityType.KU, EntityType.PATH_STEP, EntityType.LEARNING_PATH]

        embedding = await router._embed_query_for_hybrid_rung(request, domains)
        for entity_type in domains:
            await router._hybrid_curriculum_search(
                search_service=_search_service(),
                entity_type=entity_type,
                request=request,
                limit=10,
                query_embedding=embedding,
            )

        assert vector_search.embed_query.await_count == 1
        assert vector_search.hybrid_search_with_metrics.await_count == 3
        for call in vector_search.hybrid_search_with_metrics.await_args_list:
            assert call.kwargs["query_embedding"] == [0.1, 0.2, 0.3]

    @pytest.mark.anyio
    async def test_no_embed_when_no_domain_is_eligible(self) -> None:
        """Never pay for a rung that cannot fire."""
        vector_search = _vector_search()
        router = _router(vector_search)

        embedding = await router._embed_query_for_hybrid_rung(
            SearchRequest(query_text="urgent"), [EntityType.TASK, EntityType.GOAL]
        )

        assert embedding is None
        vector_search.embed_query.assert_not_awaited()

    @pytest.mark.anyio
    async def test_no_embed_when_a_filter_takes_another_strategy(self) -> None:
        """A graph or tag filter routes to Strategy 1/2; the rung lives in
        Strategy 3's `else`, so embedding for it would buy an unread vector."""
        vector_search = _vector_search()
        router = _router(vector_search)

        tagged = await router._embed_query_for_hybrid_rung(
            SearchRequest(query_text="photosynthesis", tags_contain=["biology"]),
            [EntityType.KU],
        )
        graphed = await router._embed_query_for_hybrid_rung(
            SearchRequest(
                query_text="photosynthesis",
                connected_to_uid="ku.plants",
                connected_relationship=RelationshipName.ENABLES_KNOWLEDGE,
            ),
            [EntityType.KU],
        )

        assert tagged is None
        assert graphed is None
        vector_search.embed_query.assert_not_awaited()

    @pytest.mark.anyio
    async def test_no_embed_when_strategy_0_will_run(self) -> None:
        """Semantic-boost / learning-aware take Strategy 0, which embeds for
        itself and returns early on a hit — pre-embedding pays twice and uses
        neither."""
        vector_search = _vector_search()
        router = _router(vector_search)

        boosted = await router._embed_query_for_hybrid_rung(
            SearchRequest(
                query_text="photosynthesis",
                enable_semantic_boost=True,
                context_uids=["ku.plants"],
            ),
            [EntityType.KU],
        )
        learning = await router._embed_query_for_hybrid_rung(
            SearchRequest(
                query_text="photosynthesis",
                enable_learning_aware=True,
                user_uid="user_probe",
            ),
            [EntityType.KU],
        )

        assert boosted is None
        assert learning is None
        vector_search.embed_query.assert_not_awaited()

    @pytest.mark.anyio
    async def test_no_embed_on_core_tier(self) -> None:
        embedding = await _router(vector_search=None)._embed_query_for_hybrid_rung(
            SearchRequest(query_text="photosynthesis"), [EntityType.KU]
        )

        assert embedding is None

    @pytest.mark.anyio
    async def test_no_embed_without_query_text(self) -> None:
        vector_search = _vector_search()

        embedding = await _router(vector_search)._embed_query_for_hybrid_rung(
            SearchRequest(domain=None), [EntityType.KU]
        )

        assert embedding is None
        vector_search.embed_query.assert_not_awaited()

    @pytest.mark.anyio
    async def test_embedding_failure_degrades_rather_than_breaking(self) -> None:
        """A failed embed must not take the whole search down — hybrid_search
        re-embeds for itself and degrades to fulltext-only if that fails too."""
        failed: Result[list[float]] = Result.fail(
            Errors.database(operation="embed_query", message="provider down")
        )
        vector_search = _vector_search(embedding=failed)
        router = _router(vector_search)

        embedding = await router._embed_query_for_hybrid_rung(
            SearchRequest(query_text="photosynthesis"), [EntityType.KU]
        )
        assert embedding is None

        items = await router._hybrid_curriculum_search(
            search_service=_search_service(),
            entity_type=EntityType.KU,
            request=SearchRequest(query_text="photosynthesis"),
            limit=10,
            query_embedding=embedding,
        )
        assert [item.uid for item in items] == ["ps.alpha", "ps.beta"]

    @pytest.mark.anyio
    async def test_advanced_search_threads_the_embedding_to_the_rung(self) -> None:
        """The wiring itself: the value computed in advanced_search reaches the rung."""
        vector_search = _vector_search()
        router = _router(vector_search)

        await router._execute_advanced_search(
            search_service=_search_service(),
            entity_type=EntityType.KU,
            request=SearchRequest(query_text="photosynthesis"),
            limit_per_domain=10,
            query_embedding=[0.9, 0.8],
        )

        kwargs = vector_search.hybrid_search_with_metrics.await_args.kwargs
        assert kwargs["query_embedding"] == [0.9, 0.8]

    @pytest.mark.anyio
    async def test_a_real_advanced_search_sweep_embeds_once(self) -> None:
        """Through `advanced_search` itself, not its helpers.

        The helper-level tests above pass the embedding in by hand, so they
        stay green even if `advanced_search` stops computing it — which is the
        whole optimization. This drives the public entry across all three
        curriculum domains and counts the paid calls.
        """
        vector_search = _vector_search()
        router = SearchRouter(
            ku=SimpleNamespace(search=_search_service()),
            ps=SimpleNamespace(search=_search_service()),
            lp=SimpleNamespace(search=_search_service()),
            vector_search_service=vector_search,
        )

        result = await router.advanced_search(
            SearchRequest(
                query_text="photosynthesis",
                entity_types=[
                    EntityType.KU,
                    EntityType.PATH_STEP,
                    EntityType.LEARNING_PATH,
                ],
            )
        )

        assert result.is_ok, f"sweep failed: {result}"
        assert vector_search.hybrid_search_with_metrics.await_count == 3, (
            "the rung did not run for all three curriculum domains"
        )
        assert vector_search.embed_query.await_count == 1, (
            "the query was embedded once per domain — the paid call must be made once per request"
        )


class TestRealServicesQualify:
    """The rung's liveness, checked against the real services rather than doubles.

    Every other test here builds a service that satisfies the protocol by
    construction. If `KuSearchService` stopped exposing `search_visibility`, or
    a DomainConfig gained a `user_ownership_relationship` (deriving OWNER_ONLY),
    the rung would silently stop firing in production and all of them would
    still pass — construction is not liveness (#1073).
    """

    @pytest.mark.parametrize(
        ("name", "service_class"),
        [("ku", KuSearchService), ("ps", PsSearchService), ("lp", LpSearchService)],
    )
    def test_service_satisfies_the_protocol_and_declares_public(
        self, name: str, service_class: type
    ) -> None:
        service = service_class(backend=MagicMock())

        assert isinstance(service, SupportsVisibilityDeclaration), (
            f"{name} no longer exposes search_visibility — the rung's isinstance "
            "narrowing fails and it falls through to CONTAINS forever"
        )
        assert service.search_visibility is SearchVisibility.PUBLIC, (
            f"{name} declares {service.search_visibility}, not PUBLIC — the rung "
            "refuses it. Either the domain changed (drop it from the allowlist) "
            "or a config regressed"
        )

    def test_the_allowlist_matches_the_domains_that_qualify(self) -> None:
        """Allowlist and reality agree — a stale entry is a rung that never fires."""
        allowlist = set(SearchRouter._HYBRID_TEXT_DOMAIN_VALUES)
        assert allowlist == {
            EntityType.KU.value,
            EntityType.PATH_STEP.value,
            EntityType.LEARNING_PATH.value,
        }

    def test_exercise_is_deliberately_absent(self) -> None:
        """Exercise is SCOPE_AWARE — admitting it needs user_uid threading (D1(b))."""
        assert EntityType.EXERCISE.value not in SearchRouter._HYBRID_TEXT_DOMAIN_VALUES
