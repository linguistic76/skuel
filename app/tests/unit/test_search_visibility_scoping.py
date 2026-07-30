"""
Search Visibility Scoping — the advanced_search ownership mechanism
====================================================================

Unit coverage for the SearchVisibility mechanism (the #512 follow-up):

1. ``build_search_visibility_clause`` — THE single Cypher composition
   point for every search strategy.
2. Query builders (text / graph / tags) compose the clause with correct
   parenthesization — the #512 OR-precedence lesson, now structural.
3. ``DomainConfig.get_search_visibility`` derivation + the live domain
   declarations (Exercise SCOPE_AWARE, PS PUBLIC, Tasks OWNER_ONLY).
4. ``SearchRouter.advanced_search`` — fail-closed skip without a user,
   ``request.user_uid`` forwarded to every strategy, and string
   entity_types normalized back to enums (the ``use_enum_values`` 500).
5. ``/api/search/unified`` passes the authenticated caller's uid into
   the SearchRequest.
6. ``parse_enum_field`` case-insensitive fallback (vault-authored
   uppercase enum values made curriculum exercises unconvertible).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.persistence.neo4j.query.cypher import build_search_visibility_clause
from adapters.persistence.neo4j.query.cypher.crud_queries import (
    build_array_any_match_query,
    build_graph_aware_search_query,
    build_text_search_query,
)
from core.models.dto_helpers import parse_enum_field
from core.models.enums import LearningLevel, SearchVisibility, SELCategory
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.models.search.search_router import SearchRouter
from core.models.search_request import SearchRequest
from core.models.task.task import Task
from core.services.domain_config import DomainConfig
from core.utils.result_simplified import Result

# ============================================================================
# 1. Clause builder
# ============================================================================


class TestVisibilityClause:
    def test_public_has_no_clause(self) -> None:
        assert build_search_visibility_clause(SearchVisibility.PUBLIC, has_user=True) is None
        assert build_search_visibility_clause(SearchVisibility.PUBLIC, has_user=False) is None

    def test_owner_only_property_scope(self) -> None:
        clause, params = build_search_visibility_clause(SearchVisibility.OWNER_ONLY, has_user=True)
        assert clause == "(n.user_uid = $user_uid)"
        assert params == {}

    def test_owner_only_without_user_applies_no_clause(self) -> None:
        # External surfaces (SearchRouter) fail-closed skip instead;
        # internal callers keep pre-#512 semantics.
        assert build_search_visibility_clause(SearchVisibility.OWNER_ONLY, has_user=False) is None

    def test_scope_aware_with_user_covers_all_access_paths(self) -> None:
        scope = build_search_visibility_clause(SearchVisibility.SCOPE_AWARE, has_user=True)
        assert scope is not None
        clause, params = scope
        assert clause.startswith("(") and clause.endswith(")")
        # Scope value rides as a parameter, never a string literal (SKUEL021).
        assert "n.scope = $visibility_curriculum_scope" in clause
        assert params == {"visibility_curriculum_scope": "curriculum"}
        assert "-[:OWNS]->" in clause
        assert "-[:SHARES_WITH]->" in clause
        assert "-[:MEMBER_OF]->" in clause
        assert "<-[:SHARED_WITH_GROUP]-" in clause
        # The owner_uid half of the OWNS dual write. Exercise.create() persists
        # the node and only warns when the OWNS edge fails, so an owner can hold
        # a create that reported success with no edge — the edge alone would
        # hide that entity from its own owner.
        assert "n.owner_uid = $user_uid" in clause

    def test_scope_aware_without_user_is_curriculum_only(self) -> None:
        clause, params = build_search_visibility_clause(
            SearchVisibility.SCOPE_AWARE, has_user=False
        )
        assert clause == "(n.scope = $visibility_curriculum_scope)"
        assert params == {"visibility_curriculum_scope": "curriculum"}

    def test_none_with_user_defaults_to_owner_only(self) -> None:
        # Scoping-by-default: a caller passing a user gets a scoped query
        # unless the domain explicitly declares PUBLIC.
        clause, _params = build_search_visibility_clause(None, has_user=True)
        assert clause == "(n.user_uid = $user_uid)"
        assert build_search_visibility_clause(None, has_user=False) is None

    def test_entity_alias_is_respected_and_validated(self) -> None:
        clause, _params = build_search_visibility_clause(
            SearchVisibility.OWNER_ONLY, entity_alias="target", has_user=True
        )
        assert clause == "(target.user_uid = $user_uid)"
        with pytest.raises(ValueError):
            build_search_visibility_clause(
                SearchVisibility.OWNER_ONLY, entity_alias="n) MATCH (m", has_user=True
            )


# ============================================================================
# 2. Query builder composition (the #512 parenthesization lesson)
# ============================================================================


class TestQueryBuilderComposition:
    def test_text_search_owner_scope_binds_before_or_chain(self) -> None:
        cypher, params = build_text_search_query(
            Task,
            "alpha",
            search_fields=("title", "description"),
            label="Task",
            visibility=SearchVisibility.OWNER_ONLY,
            user_uid="user_a",
        )
        assert "(n.user_uid = $user_uid) AND (" in cypher
        assert params["user_uid"] == "user_a"

    def test_text_search_public_is_unscoped(self) -> None:
        cypher, params = build_text_search_query(
            Task,
            "alpha",
            search_fields=("title",),
            label="Task",
            visibility=SearchVisibility.PUBLIC,
            user_uid="user_a",
        )
        assert "user_uid" not in cypher
        assert "user_uid" not in params

    def test_graph_aware_search_scopes_target_alias(self) -> None:
        cypher, params = build_graph_aware_search_query(
            Task,
            query="alpha",
            source_uid="goal_1",
            relationship_type=RelationshipName.FULFILLS_GOAL.value,
            search_fields=("title",),
            label="Task",
            direction="incoming",
            visibility=SearchVisibility.OWNER_ONLY,
            user_uid="user_a",
        )
        assert "(target.user_uid = $user_uid) AND (" in cypher
        assert params["user_uid"] == "user_a"

    def test_array_match_scopes_and_parenthesizes(self) -> None:
        cypher, params = build_array_any_match_query(
            label=NeoLabel.TASK,
            field="tags",
            values=["alpha"],
            visibility=SearchVisibility.OWNER_ONLY,
            user_uid="user_a",
        )
        assert "(n.user_uid = $user_uid) AND ANY(" in cypher
        assert params["user_uid"] == "user_a"

    def test_scope_aware_without_user_still_filters_to_curriculum(self) -> None:
        cypher, params = build_text_search_query(
            Task,  # any dataclass with title works for the builder
            "alpha",
            search_fields=("title",),
            label="Entity",
            visibility=SearchVisibility.SCOPE_AWARE,
            user_uid=None,
        )
        assert "(n.scope = $visibility_curriculum_scope) AND (" in cypher
        assert params["visibility_curriculum_scope"] == "curriculum"
        assert "user_uid" not in params


# ============================================================================
# 3. DomainConfig derivation + live declarations
# ============================================================================


class _FakeDTO:
    @classmethod
    def from_dict(cls, _data: dict) -> _FakeDTO:
        return cls()


class TestDomainConfigDerivation:
    def test_ownership_relationship_derives_owner_only(self) -> None:
        config = DomainConfig(dto_class=_FakeDTO, model_class=Task)
        assert config.get_search_visibility() is SearchVisibility.OWNER_ONLY

    def test_no_ownership_derives_public(self) -> None:
        config = DomainConfig(
            dto_class=_FakeDTO, model_class=Task, user_ownership_relationship=None
        )
        assert config.get_search_visibility() is SearchVisibility.PUBLIC

    def test_explicit_declaration_wins(self) -> None:
        config = DomainConfig(
            dto_class=_FakeDTO,
            model_class=Task,
            user_ownership_relationship=RelationshipName.OWNS,
            search_visibility=SearchVisibility.SCOPE_AWARE,
        )
        assert config.get_search_visibility() is SearchVisibility.SCOPE_AWARE

    def test_live_domain_declarations(self) -> None:
        from core.services.exercises.exercise_service import ExerciseService
        from core.services.ps.ps_search_service import PsSearchService
        from core.services.tasks.tasks_search_service import TasksSearchService
        from core.services.user_entry.user_entry_service import UserEntryService

        assert ExerciseService._config.get_search_visibility() is SearchVisibility.SCOPE_AWARE
        assert PsSearchService._config.get_search_visibility() is SearchVisibility.PUBLIC
        assert TasksSearchService._config.get_search_visibility() is SearchVisibility.OWNER_ONLY
        assert UserEntryService._config.get_search_visibility() is SearchVisibility.OWNER_ONLY


# ============================================================================
# 4. SearchRouter.advanced_search
# ============================================================================


def _fake_entity(uid: str, title: str) -> SimpleNamespace:
    return SimpleNamespace(uid=uid, title=title)


def _mock_task_service() -> MagicMock:
    service = MagicMock()
    service.search = AsyncMock(return_value=Result.ok([_fake_entity("task_1", "Alpha")]))
    service.search_by_tags = AsyncMock(return_value=Result.ok([_fake_entity("task_1", "Alpha")]))
    service.search_connected_to = AsyncMock(
        return_value=Result.ok([_fake_entity("task_1", "Alpha")])
    )
    return service


@pytest.fixture
def router() -> tuple[SearchRouter, MagicMock]:
    service = _mock_task_service()
    return SearchRouter(services=SimpleNamespace(tasks=service)), service


class TestAdvancedSearchScoping:
    @pytest.mark.asyncio
    async def test_no_user_skips_user_owned_domains(self, router) -> None:
        """Fail-closed: without a requesting user, user-owned domains
        contribute nothing and their services are never called."""
        search_router, service = router
        request = SearchRequest(query_text="Alpha", entity_types=[EntityType.TASK])

        result = await search_router.advanced_search(request)

        assert result.is_ok, result.expect_error()
        assert result.value.total_count == 0
        service.search.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_text_strategy_forwards_user_uid(self, router) -> None:
        search_router, service = router
        request = SearchRequest(
            query_text="Alpha", entity_types=[EntityType.TASK], user_uid="user_a"
        )

        result = await search_router.advanced_search(request)

        assert result.is_ok, result.expect_error()
        assert result.value.total_count == 1
        assert service.search.await_args.kwargs["user_uid"] == "user_a"

    @pytest.mark.asyncio
    async def test_tags_strategy_forwards_user_uid(self, router) -> None:
        search_router, service = router
        request = SearchRequest(
            query_text="Alpha",
            entity_types=[EntityType.TASK],
            tags_contain=["alphatag"],
            user_uid="user_a",
        )

        result = await search_router.advanced_search(request)

        assert result.is_ok, result.expect_error()
        assert service.search_by_tags.await_args.kwargs["user_uid"] == "user_a"

    @pytest.mark.asyncio
    async def test_graph_strategy_forwards_user_uid(self, router) -> None:
        search_router, service = router
        request = SearchRequest(
            query_text="Alpha",
            entity_types=[EntityType.TASK],
            connected_to_uid="goal_1",
            connected_relationship=RelationshipName.FULFILLS_GOAL,
            connected_direction="incoming",
            user_uid="user_a",
        )

        result = await search_router.advanced_search(request)

        assert result.is_ok, result.expect_error()
        assert service.search_connected_to.await_args.kwargs["user_uid"] == "user_a"

    @pytest.mark.asyncio
    async def test_skipped_domains_do_not_eat_the_limit_budget(self) -> None:
        """Kody (PR #513): a mixed [TASK, EXERCISE] request without a user
        skips TASK fail-closed — EXERCISE must get the FULL limit budget,
        not half of it."""
        exercise_service = _mock_task_service()
        search_router = SearchRouter(
            services=SimpleNamespace(tasks=_mock_task_service(), exercises=exercise_service)
        )
        request = SearchRequest(
            query_text="Alpha",
            entity_types=[EntityType.TASK, EntityType.EXERCISE],
            limit=50,
        )

        result = await search_router.advanced_search(request)

        assert result.is_ok, result.expect_error()
        # Strategy 3 signature: search(query, limit_per_domain, user_uid=...)
        assert exercise_service.search.await_args.args[1] == 50

    @pytest.mark.asyncio
    async def test_string_entity_types_normalize_and_serialize(self, router) -> None:
        """use_enum_values leaves raw strings in entity_types — the filtered
        path must map them back to enum members so SearchResultItem.to_dict()
        (``entity_type.value``) doesn't 500 the unified API."""
        search_router, _service = router
        request = SearchRequest(query_text="Alpha", entity_types=["task"], user_uid="user_a")

        result = await search_router.advanced_search(request)

        assert result.is_ok, result.expect_error()
        assert EntityType.TASK in result.value.results_by_domain
        items = result.value.results_by_domain[EntityType.TASK]
        assert items[0].to_dict()["entity_type"] == "task"


# ============================================================================
# 5. /api/search/unified passes the authenticated caller's uid
# ============================================================================


class _RouteRegistry:
    def __init__(self) -> None:
        self.handlers: dict[tuple[str, str], Any] = {}

    def __call__(self, path: str, methods: list[str] | None = None):
        method = (methods[0] if methods else "GET").upper()

        def decorator(func):
            self.handlers[(path, method)] = func
            return func

        return decorator


class TestUnifiedRouteUserScope:
    @pytest.mark.asyncio
    async def test_route_builds_request_with_caller_uid(self, monkeypatch) -> None:
        monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "false")
        from adapters.inbound.search_routes import create_search_api_routes

        registry = _RouteRegistry()
        search_router = MagicMock()
        search_router.advanced_search = AsyncMock(
            return_value=Result.ok(
                SimpleNamespace(query="Alpha", total_count=0, results_by_domain={}, top_results=[])
            )
        )
        create_search_api_routes(app=MagicMock(), rt=registry, search_router=search_router)
        handler = registry.handlers[("/api/search/unified", "POST")]

        fake_request = SimpleNamespace(
            method="POST",  # csrf_protected passes: enforcement disabled above
            session={"user_uid": "user_caller"},
            url=SimpleNamespace(path="/api/search/unified"),
            headers={},
        )
        response = await handler(fake_request, query="Alpha")

        assert isinstance(response, dict) and not response.get("error"), response
        sent_request = search_router.advanced_search.await_args.args[0]
        assert sent_request.user_uid == "user_caller"


# ============================================================================
# 6. parse_enum_field case-insensitive read boundary
# ============================================================================


class TestEnumReadBoundaryCaseFallback:
    def test_uppercase_persisted_values_parse(self) -> None:
        data = {"learning_level": "BEGINNER", "sel_category": "RESPONSIBLE_DECISION_MAKING"}
        parse_enum_field(data, "learning_level", LearningLevel)
        parse_enum_field(data, "sel_category", SELCategory)
        assert data["learning_level"] is LearningLevel.BEGINNER
        assert data["sel_category"] is SELCategory.RESPONSIBLE_DECISION_MAKING

    def test_genuinely_invalid_value_still_raises(self) -> None:
        data = {"learning_level": "GALACTIC"}
        with pytest.raises(ValueError):
            parse_enum_field(data, "learning_level", LearningLevel)

    def test_authored_none_marker_means_absence(self) -> None:
        """`sel_category: none` (NOUS anchor Kus, rawness principle) parses to
        None instead of killing the whole Ku search sweep with ValueError."""
        data = {"sel_category": "none"}
        parse_enum_field(data, "sel_category", SELCategory)
        assert data["sel_category"] is None

    def test_enum_with_real_none_member_keeps_it(self) -> None:
        """Enums that define NONE = 'none' (Pipeline, RecurrencePattern) parse
        strictly and never hit the absence fallback."""
        from core.models.enums.scheduling_enums import RecurrencePattern

        data = {"recurrence_pattern": "none"}
        parse_enum_field(data, "recurrence_pattern", RecurrencePattern)
        assert data["recurrence_pattern"] is RecurrencePattern.NONE

    def test_uppercase_none_on_real_none_member_enum_keeps_it(self) -> None:
        """Persisted 'NONE' must round-trip to the enum member, not Python
        None — the absence fallback fires only after the case-insensitive
        parse also fails (Kody, PR #536)."""
        from core.models.enums.scheduling_enums import RecurrencePattern

        data = {"recurrence_pattern": "NONE"}
        parse_enum_field(data, "recurrence_pattern", RecurrencePattern)
        assert data["recurrence_pattern"] is RecurrencePattern.NONE

    def test_uppercase_none_marker_means_absence(self) -> None:
        data = {"sel_category": "NONE"}
        parse_enum_field(data, "sel_category", SELCategory)
        assert data["sel_category"] is None
