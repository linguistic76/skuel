"""
NOUS category wiring tests
==========================

Covers the query-layer mechanics behind the `nous` topic facet:
- `has` operator: exact match on scalar fields, element membership on
  list/tuple-annotated fields (Ku/PS `nous`)
- `contains` operator: tuple-annotated fields (frozen models) take the
  membership branch, not string CONTAINS (regression: origin check missed
  tuple)
- distinct-values query: array properties UNWIND to per-element values
- SearchRequest: the `nous` facet lands in property filters under the real
  property name
- Ku model: list-authored `nous` normalizes to tuple
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.persistence.neo4j.query.cypher.crud_queries import (
    build_distinct_values_query,
    build_search_query,
)
from core.models.enums import SearchVisibility
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.ku.ku import Ku
from core.models.pathways.path_step import PathStep
from core.models.search_request import SearchRequest
from core.models.task.task import Task
from core.orchestrator.search_router import SearchRouter
from core.utils.result_simplified import Result


class TestHasOperator:
    def test_has_on_scalar_field_is_exact_match(self):
        cypher, params = build_search_query(Task, {"priority__has": "high"}, label="Entity")

        assert "n.priority = $priority_has" in cypher
        assert params["priority_has"] == "high"
        assert "CONTAINS" not in cypher

    def test_has_on_tuple_field_is_membership(self):
        cypher, params = build_search_query(Ku, {"nous__has": "body"}, label="Ku")

        assert "$nous_has IN n.nous" in cypher
        assert params["nous_has"] == "body"

    def test_contains_on_tuple_field_is_membership(self):
        # Frozen models annotate array fields as tuple[str, ...] — the
        # membership branch must trigger for tuple, not only list.
        cypher, params = build_search_query(Ku, {"tags__contains": "yoga"}, label="Ku")

        assert "$tags_contains IN n.tags" in cypher
        assert params["tags_contains"] == "yoga"


class TestDistinctValuesArrayAware:
    def test_array_properties_unwind_to_elements(self):
        cypher, params = build_distinct_values_query(label=NeoLabel.KU, field="nous")

        assert "UNWIND" in cypher
        assert "IS :: LIST<ANY>" in cypher
        assert "RETURN value, count(*) AS count" in cypher
        assert params == {}

    def test_user_scope_preserved(self):
        cypher, params = build_distinct_values_query(
            label=NeoLabel.TASK, field="priority", user_uid="user_mike"
        )

        assert "n.user_uid = $user_uid" in cypher
        assert "UNWIND" in cypher
        assert params["user_uid"] == "user_mike"


class TestSearchRequestNousFacet:
    def test_nous_facet_maps_to_real_property_name(self):
        request = SearchRequest(nous="body")

        assert request.to_property_filters()["nous"] == "body"

    def test_form_params_normalize_empty_nous(self):
        request = SearchRequest.from_form_params(query="breath", nous="")

        assert request.nous is None
        assert "nous" not in request.to_property_filters()


class TestKuNousField:
    def test_list_authored_nous_normalizes_to_tuple(self):
        ku = Ku(uid="ku_test_123", title="Test", nous=["body", "self-awareness"])

        assert ku.nous == ("body", "self-awareness")

    def test_default_nous_is_empty(self):
        ku = Ku(uid="ku_test_456", title="Unassigned")

        assert ku.nous == ()

    def test_path_step_list_authored_nous_normalizes_to_tuple(self):
        # Frozen dataclass must not retain a mutable list (Kody, PR #534)
        ps = PathStep(uid="ps.test.step", title="Step", nous=["body"])

        assert ps.nous == ("body",)


class TestFacetedSweepInterleave:
    @pytest.mark.asyncio
    async def test_round_robin_prevents_domain_starvation(self):
        """A high-yield early domain must not consume the whole limit —
        faceted results carry no score, so truncation is round-robin
        interleaved across domains (Kody, PR #534)."""

        def _svc(records):
            service = MagicMock()
            service.graph_aware_faceted_search = AsyncMock(return_value=Result.ok(records))
            # Protocol isinstance uses getattr_static (Py 3.12+) — the
            # SupportsGraphAwareSearch members must be REAL attributes, not
            # MagicMock lazy ones, or _resolve_graph_aware_service skips the mock.
            service.search_visibility = SearchVisibility.PUBLIC
            return service

        ps_records = [{"uid": f"ps_{i}", "title": f"PS {i}", "_domain": "ps"} for i in range(5)]
        lp_records = [{"uid": "lp_1", "title": "LP 1", "_domain": "lp"}]
        router = SearchRouter(ps=_svc(ps_records), lp=_svc(lp_records))
        request = SearchRequest(nous="body", limit=3)

        results = await router._faceted_sweep(
            request, "user_mike", [EntityType.PATH_STEP, EntityType.LEARNING_PATH]
        )

        assert len(results) == 3
        assert "lp" in [r["_domain"] for r in results]
