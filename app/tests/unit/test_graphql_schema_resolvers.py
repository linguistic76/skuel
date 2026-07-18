# mypy: disable-error-code="call-arg,misc"
# Strawberry decorators generate __init__ dynamically; mypy can't see the
# inferred constructor args. Mirrors the adapters.inbound.graphql.* override.
"""
Unit Tests for GraphQL Schema Resolvers
========================================

Tests all Query resolvers, helper functions, and schema factory in
``adapters/inbound/graphql/schema.py`` using mocked services and DataLoaders.

No Neo4j required — everything is stubbed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import strawberry
from strawberry.types import Info

from adapters.inbound.graphql.config import validate_list_limit, validate_query_depth
from adapters.inbound.graphql.context import GraphQLContext, _batch_load, create_graphql_context
from adapters.inbound.graphql.query_helpers import unwrap_list, unwrap_optional, unwrap_result
from adapters.inbound.graphql.schema import (
    Query,
    build_low_progress_blocker,
    build_missing_prerequisite_blocker,
    check_deprecated_content,
    create_graphql_schema,
)
from adapters.inbound.graphql.types import Blocker, KnowledgeNode
from core.models.type_hints import UserUID

# ============================================================================
# Stubs and helpers
# ============================================================================


class FakeDomain(StrEnum):
    TECH = "tech"
    BUSINESS = "business"
    PERSONAL = "personal"
    KNOWLEDGE = "knowledge"


class FakeStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


@dataclass
class FakeKU:
    uid: str = "ku_test_1"
    title: str = "Test KU"
    summary: str | None = "A summary"
    domain: FakeDomain = FakeDomain.TECH
    tags: list[str] | None = None
    quality_score: float = 0.9
    metadata: dict[str, Any] | None = None


@dataclass
class FakeTask:
    uid: str = "task_test_1"
    title: str = "Test Task"
    description: str | None = "Task desc"
    status: FakeStatus = FakeStatus.ACTIVE
    priority: str | None = "high"


@dataclass
class FakeLearningPath:
    uid: str = "lp_test_1"
    title: str = "Test Path"
    description: str | None = "Path desc"
    estimated_hours: float | None = 5.0


@dataclass
class FakePathStep:
    uid: str = "ls_test_1"
    title: str = "Test Step"
    knowledge_uids: tuple[str, ...] = ("ku_test_1",)
    mastery_threshold: float = 0.8
    estimated_hours: float = 2.5


@dataclass
class FakeResult:
    """Minimal Result[T] stub."""

    value: Any = None
    error: Any = None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    @property
    def is_ok(self) -> bool:
        return self.error is None


@dataclass
class FakeKnowledgeProfile:
    mastered_uids: set[str] = field(default_factory=set)
    in_progress_uids: set[str] = field(default_factory=set)
    in_progress_knowledge: list[Any] = field(default_factory=list)


@dataclass
class FakeInProgressEntry:
    knowledge_uid: str = "ku_test_1"
    progress: float = 0.2


@dataclass
class FakeSearchResponse:
    results: list[dict[str, Any]] = field(default_factory=list)


def _make_loader(return_map: dict[str, Any] | None = None) -> MagicMock:
    """Create a mock DataLoader that resolves from a dict."""
    loader = MagicMock()
    _map = return_map or {}

    async def _load(key: str) -> Any:
        return _map.get(key)

    loader.load = AsyncMock(side_effect=_load)
    return loader


def _make_context(
    *,
    services: Any = None,
    search_router: Any = None,
    knowledge_loader: Any = None,
    task_loader: Any = None,
    lp_loader: Any = None,
    ls_loader: Any = None,
    user_uid: str = "user_test",
) -> GraphQLContext:
    return GraphQLContext(
        services=services or MagicMock(),
        search_router=search_router,
        knowledge_loader=knowledge_loader or _make_loader(),
        task_loader=task_loader or _make_loader(),
        learning_path_loader=lp_loader or _make_loader(),
        path_step_loader=ls_loader or _make_loader(),
        user_uid=user_uid,
    )


def _make_info(context: GraphQLContext) -> Info[GraphQLContext, Any]:
    info = MagicMock(spec=Info)
    info.context = context
    return info


# ============================================================================
# Helper function tests (module-level in schema.py)
# ============================================================================


class TestBuildMissingPrerequisiteBlocker:
    def test_single_prereq(self) -> None:
        step = FakePathStep(title="Advanced Python")
        unmet = [FakeKU(uid="ku_prereq", title="Python Basics")]

        blocker = build_missing_prerequisite_blocker(step, "ku_step_1", unmet)

        assert isinstance(blocker, Blocker)
        assert blocker.blocker_type == "missing_prerequisite"
        assert blocker.knowledge_uid == "ku_step_1"
        assert blocker.knowledge_title == "Advanced Python"
        assert blocker.severity == "warning"
        assert "1 prerequisite" in blocker.description
        assert "Python Basics" in blocker.description

    def test_multiple_prereqs_truncated(self) -> None:
        unmet = [FakeKU(title=f"Prereq {i}") for i in range(5)]
        step = FakePathStep(title="Step X")

        blocker = build_missing_prerequisite_blocker(step, "ku_x", unmet)

        assert "5 prerequisite" in blocker.description
        assert "(+2 more)" in blocker.description

    def test_exactly_three_prereqs_no_truncation(self) -> None:
        unmet = [FakeKU(title=f"P{i}") for i in range(3)]
        step = FakePathStep(title="Step Y")

        blocker = build_missing_prerequisite_blocker(step, "ku_y", unmet)

        assert "(+" not in blocker.description


class TestBuildLowProgressBlocker:
    def test_basic(self) -> None:
        step = FakePathStep(title="Data Structures")

        blocker = build_low_progress_blocker(step, "ku_ds", 0.15)

        assert blocker.blocker_type == "low_progress"
        assert blocker.severity == "info"
        assert "15%" in blocker.description
        assert blocker.knowledge_title == "Data Structures"

    def test_zero_progress(self) -> None:
        step = FakePathStep(title="Intro")
        blocker = build_low_progress_blocker(step, "ku_intro", 0.0)
        assert "0%" in blocker.description


class TestCheckDeprecatedContent:
    def test_deprecated(self) -> None:
        ku = FakeKU(metadata={"deprecated": True, "outdated": False})
        is_dep, is_out = check_deprecated_content(ku)
        assert is_dep is True
        assert is_out is False

    def test_outdated(self) -> None:
        ku = FakeKU(metadata={"deprecated": False, "outdated": True})
        is_dep, is_out = check_deprecated_content(ku)
        assert is_dep is False
        assert is_out is True

    def test_both(self) -> None:
        ku = FakeKU(metadata={"deprecated": True, "outdated": True})
        is_dep, is_out = check_deprecated_content(ku)
        assert is_dep is True
        assert is_out is True

    def test_none_metadata(self) -> None:
        ku = FakeKU(metadata=None)
        is_dep, is_out = check_deprecated_content(ku)
        assert is_dep is False
        assert is_out is False

    def test_empty_metadata(self) -> None:
        ku = FakeKU(metadata={})
        is_dep, is_out = check_deprecated_content(ku)
        assert is_dep is False
        assert is_out is False


# ============================================================================
# query_helpers.py tests
# ============================================================================


class TestUnwrapResult:
    def test_ok_with_value(self) -> None:
        assert unwrap_result(FakeResult(value="hello"), "fallback") == "hello"

    def test_error_returns_fallback(self) -> None:
        assert unwrap_result(FakeResult(error="boom"), "fallback") == "fallback"

    def test_none_value_returns_fallback(self) -> None:
        assert unwrap_result(FakeResult(value=None), "fallback") == "fallback"


class TestUnwrapList:
    def test_ok_with_items(self) -> None:
        assert unwrap_list(FakeResult(value=[1, 2, 3])) == [1, 2, 3]

    def test_error_returns_empty(self) -> None:
        assert unwrap_list(FakeResult(error="boom")) == []

    def test_none_returns_empty(self) -> None:
        assert unwrap_list(FakeResult(value=None)) == []

    def test_empty_list_returns_empty(self) -> None:
        assert unwrap_list(FakeResult(value=[])) == []


class TestUnwrapOptional:
    def test_ok_with_value(self) -> None:
        assert unwrap_optional(FakeResult(value="x")) == "x"

    def test_error_returns_none(self) -> None:
        assert unwrap_optional(FakeResult(error="boom")) is None

    def test_none_value(self) -> None:
        assert unwrap_optional(FakeResult(value=None)) is None


# ============================================================================
# config.py tests
# ============================================================================


class TestValidateListLimit:
    def test_none_returns_default(self) -> None:
        assert validate_list_limit(None) == 20

    def test_valid_limit(self) -> None:
        assert validate_list_limit(50) == 50

    def test_exceeds_max_capped(self) -> None:
        assert validate_list_limit(999) == 100

    def test_zero_returns_default(self) -> None:
        assert validate_list_limit(0) == 20

    def test_negative_returns_default(self) -> None:
        assert validate_list_limit(-5) == 20

    def test_custom_default(self) -> None:
        assert validate_list_limit(None, default=10) == 10

    def test_one_is_valid(self) -> None:
        assert validate_list_limit(1) == 1


class TestValidateQueryDepth:
    def test_none_returns_default(self) -> None:
        assert validate_query_depth(None) == 2

    def test_valid_depth(self) -> None:
        assert validate_query_depth(3) == 3

    def test_exceeds_max_capped(self) -> None:
        assert validate_query_depth(99) == 5

    def test_negative_returns_zero(self) -> None:
        assert validate_query_depth(-1) == 0

    def test_custom_default(self) -> None:
        assert validate_query_depth(None, default=4) == 4


# ============================================================================
# auth.py tests
# ============================================================================


class TestRequireUserUid:
    def test_returns_uid(self) -> None:
        from adapters.inbound.graphql.auth import require_user_uid

        ctx = _make_context(user_uid="user_abc")
        info = _make_info(ctx)
        assert require_user_uid(info) == "user_abc"

    def test_raises_on_empty(self) -> None:
        from adapters.inbound.graphql.auth import require_user_uid

        ctx = _make_context(user_uid="")
        info = _make_info(ctx)
        with pytest.raises(ValueError, match="missing user_uid"):
            require_user_uid(info)


class TestResolveTargetUser:
    @pytest.mark.asyncio
    async def test_no_override_returns_caller(self) -> None:
        from adapters.inbound.graphql.auth import resolve_target_user

        ctx = _make_context(user_uid="user_caller")
        info = _make_info(ctx)
        result = await resolve_target_user(info, None)
        assert result == "user_caller"

    @pytest.mark.asyncio
    async def test_override_requires_admin(self) -> None:
        from adapters.inbound.graphql.auth import resolve_target_user

        user_service = AsyncMock()
        caller_user = MagicMock()
        caller_user.has_permission.return_value = False
        user_service.get_user.return_value = FakeResult(value=caller_user)

        services = MagicMock()
        services.user = user_service

        ctx = _make_context(services=services, user_uid="user_caller")
        info = _make_info(ctx)

        with pytest.raises(PermissionError, match="Admin role required"):
            await resolve_target_user(info, "user_other")

    @pytest.mark.asyncio
    async def test_override_allowed_for_admin(self) -> None:
        from adapters.inbound.graphql.auth import resolve_target_user

        user_service = AsyncMock()
        caller_user = MagicMock()
        caller_user.has_permission.return_value = True
        user_service.get_user.return_value = FakeResult(value=caller_user)

        services = MagicMock()
        services.user = user_service

        ctx = _make_context(services=services, user_uid="user_admin")
        info = _make_info(ctx)

        result = await resolve_target_user(info, "user_target")
        assert result == "user_target"

    @pytest.mark.asyncio
    async def test_override_no_user_service_raises(self) -> None:
        from adapters.inbound.graphql.auth import resolve_target_user

        services = MagicMock()
        services.user = None

        ctx = _make_context(services=services, user_uid="user_caller")
        info = _make_info(ctx)

        with pytest.raises(PermissionError, match="User service unavailable"):
            await resolve_target_user(info, "user_other")


# ============================================================================
# context.py tests
# ============================================================================


class TestBatchLoad:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        batch_fn = AsyncMock(return_value=FakeResult(value=["a", "b"]))
        result = await _batch_load(["k1", "k2"], batch_fn, "test")
        assert result == ["a", "b"]
        batch_fn.assert_called_once_with(["k1", "k2"])

    @pytest.mark.asyncio
    async def test_error_returns_nones(self) -> None:
        batch_fn = AsyncMock(return_value=FakeResult(error="DB error"))
        result = await _batch_load(["k1", "k2", "k3"], batch_fn, "test")
        assert result == [None, None, None]


class TestCreateGraphqlContext:
    def test_creates_context_with_loaders(self) -> None:
        services = MagicMock()
        ctx = create_graphql_context(services, search_router=None, user_uid=UserUID("user_x"))

        assert ctx.user_uid == "user_x"
        assert ctx.services is services
        assert ctx.knowledge_loader is not None
        assert ctx.task_loader is not None
        assert ctx.learning_path_loader is not None
        assert ctx.path_step_loader is not None


# ============================================================================
# Query resolver tests
# ============================================================================


class TestKnowledgeUnitResolver:
    @pytest.mark.asyncio
    async def test_found(self) -> None:
        ku = FakeKU(uid="ku_1", title="Found KU")
        ctx = _make_context(knowledge_loader=_make_loader({"ku_1": ku}))
        info = _make_info(ctx)

        query = Query()
        result = await query.knowledge_unit(info, uid="ku_1")

        assert result is not None
        assert result.uid == "ku_1"
        assert result.title == "Found KU"
        assert isinstance(result, KnowledgeNode)

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        ctx = _make_context(knowledge_loader=_make_loader({}))
        info = _make_info(ctx)

        result = await Query().knowledge_unit(info, uid="ku_missing")
        assert result is None


class TestKnowledgeUnitsResolver:
    @pytest.mark.asyncio
    async def test_returns_list(self) -> None:
        services = MagicMock()
        core = AsyncMock()
        core.list.return_value = FakeResult(value=([FakeKU(uid="ku_a"), FakeKU(uid="ku_b")], 2))
        services.ps.core = core

        ctx = _make_context(services=services)
        info = _make_info(ctx)

        result = await Query().knowledge_units(info)
        assert len(result) == 2
        assert result[0].uid == "ku_a"

    @pytest.mark.asyncio
    async def test_invalid_domain_returns_empty(self) -> None:
        services = MagicMock()
        ctx = _make_context(services=services)
        info = _make_info(ctx)

        result = await Query().knowledge_units(info, domain="INVALID_DOMAIN_XYZ")
        assert result == []

    @pytest.mark.asyncio
    async def test_no_ps_service_returns_empty(self) -> None:
        services = MagicMock()
        services.ps = None
        ctx = _make_context(services=services)
        info = _make_info(ctx)

        result = await Query().knowledge_units(info)
        assert result == []


class TestSearchKnowledgeResolver:
    @pytest.mark.asyncio
    async def test_returns_results(self) -> None:
        from adapters.inbound.graphql.types import SearchInput

        search_router = AsyncMock()
        search_response = FakeSearchResponse(
            results=[
                {"uid": "ku_s1", "title": "Result 1", "_score": 0.95, "explanation": "good match"},
            ]
        )
        search_router.faceted_search.return_value = FakeResult(value=search_response)

        ctx = _make_context(search_router=search_router, user_uid="user_test")
        info = _make_info(ctx)

        input_obj = SearchInput(query="python", limit=10)
        result = await Query().search_knowledge(info, input=input_obj)

        assert len(result) == 1
        assert result[0].knowledge.uid == "ku_s1"
        assert result[0].relevance == 0.95

    @pytest.mark.asyncio
    async def test_no_router_returns_empty(self) -> None:
        from adapters.inbound.graphql.types import SearchInput

        ctx = _make_context(search_router=None, user_uid="user_test")
        info = _make_info(ctx)

        result = await Query().search_knowledge(info, input=SearchInput(query="test"))
        assert result == []

    @pytest.mark.asyncio
    async def test_error_returns_empty(self) -> None:
        from adapters.inbound.graphql.types import SearchInput

        search_router = AsyncMock()
        search_router.faceted_search.return_value = FakeResult(error="search failed")

        ctx = _make_context(search_router=search_router, user_uid="user_test")
        info = _make_info(ctx)

        result = await Query().search_knowledge(info, input=SearchInput(query="test"))
        assert result == []


class TestTaskResolver:
    @pytest.mark.asyncio
    async def test_found(self) -> None:
        task = FakeTask(uid="task_1", title="My Task")
        ctx = _make_context(task_loader=_make_loader({"task_1": task}))
        info = _make_info(ctx)

        result = await Query().task(info, uid="task_1")
        assert result is not None
        assert result.uid == "task_1"
        assert result.title == "My Task"

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        ctx = _make_context(task_loader=_make_loader({}))
        info = _make_info(ctx)

        result = await Query().task(info, uid="task_missing")
        assert result is None


class TestTasksResolver:
    @pytest.mark.asyncio
    async def test_returns_active_tasks(self) -> None:
        services = MagicMock()
        services.tasks.get_filtered_context = AsyncMock(
            return_value=FakeResult(
                value={
                    "entities": [FakeTask(uid="t1"), FakeTask(uid="t2")],
                    "stats": {},
                }
            )
        )

        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        result = await Query().tasks(info, include_completed=False)
        assert len(result) == 2
        assert result[0].uid == "t1"

    @pytest.mark.asyncio
    async def test_no_tasks_service_returns_empty(self) -> None:
        services = MagicMock()
        services.tasks = None
        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        result = await Query().tasks(info)
        assert result == []


class TestLearningPathResolver:
    @pytest.mark.asyncio
    async def test_found(self) -> None:
        lp = FakeLearningPath(uid="lp_1", title="My Path")
        ctx = _make_context(lp_loader=_make_loader({"lp_1": lp}))
        info = _make_info(ctx)

        result = await Query().learning_path(info, uid="lp_1")
        assert result is not None
        assert result.uid == "lp_1"
        assert result.name == "My Path"

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        ctx = _make_context(lp_loader=_make_loader({}))
        info = _make_info(ctx)

        result = await Query().learning_path(info, uid="lp_missing")
        assert result is None


class TestLearningPathsResolver:
    @pytest.mark.asyncio
    async def test_user_paths(self) -> None:
        services = MagicMock()
        services.lp.list_user_paths = AsyncMock(
            return_value=FakeResult(value=[FakeLearningPath(uid="lp_1")])
        )

        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        result = await Query().learning_paths(info)
        assert len(result) == 1
        assert result[0].uid == "lp_1"

    @pytest.mark.asyncio
    async def test_all_paths(self) -> None:
        services = MagicMock()
        services.lp.list_all_paths = AsyncMock(
            return_value=FakeResult(
                value=[FakeLearningPath(uid="lp_a"), FakeLearningPath(uid="lp_b")]
            )
        )

        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        result = await Query().learning_paths(info, all_paths=True)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_no_lp_service_returns_empty(self) -> None:
        services = MagicMock()
        services.lp = None
        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        result = await Query().learning_paths(info)
        assert result == []


class TestUserDashboardResolver:
    @pytest.mark.asyncio
    async def test_aggregates_counts(self) -> None:
        services = MagicMock()
        services.tasks.get_user_tasks = AsyncMock(
            return_value=FakeResult(value=[FakeTask() for _ in range(3)])
        )
        services.lp.list_user_paths = AsyncMock(return_value=FakeResult(value=[FakeLearningPath()]))
        services.habits.get_user_habits = AsyncMock(
            return_value=FakeResult(value=[MagicMock(), MagicMock()])
        )

        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        result = await Query().user_dashboard(info)
        assert result.tasks_count == 3
        assert result.paths_count == 1
        assert result.habits_count == 2

    @pytest.mark.asyncio
    async def test_handles_missing_services(self) -> None:
        services = MagicMock()
        services.tasks = None
        services.lp = None
        services.habits = None

        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        result = await Query().user_dashboard(info)
        assert result.tasks_count == 0
        assert result.paths_count == 0
        assert result.habits_count == 0


class TestLearningPathWithContextResolver:
    @pytest.mark.asyncio
    async def test_returns_context_with_progress(self) -> None:
        lp = FakeLearningPath(uid="lp_ctx", title="Context Path")
        steps = [
            FakePathStep(uid="ls_1", knowledge_uids=("ku_1",)),
            FakePathStep(uid="ls_2", knowledge_uids=("ku_2",)),
        ]

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(return_value=FakeResult(value=steps))

        profile = FakeKnowledgeProfile(mastered_uids={"ku_1"})
        services.user_progress.build_user_knowledge_profile = AsyncMock(
            return_value=FakeResult(value=profile)
        )
        services.ps = None  # Skip prerequisite checking

        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({"lp_ctx": lp}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_with_context(info, path_uid="lp_ctx")

        assert result is not None
        assert result.path.uid == "lp_ctx"
        assert result.completed_steps == 1
        assert result.completion_percentage == 50.0
        assert result.current_step_number == 2
        assert result.prerequisites_met is True  # No blockers since lesson service is None

    @pytest.mark.asyncio
    async def test_path_not_found(self) -> None:
        services = MagicMock()
        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_with_context(info, path_uid="lp_missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_lp_service(self) -> None:
        services = MagicMock()
        services.lp = None
        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        result = await Query().learning_path_with_context(info, path_uid="lp_x")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_progress_service(self) -> None:
        lp = FakeLearningPath(uid="lp_np")
        steps = [FakePathStep(uid="ls_1")]

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(return_value=FakeResult(value=steps))
        services.user_progress = None
        services.ps = None

        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({"lp_np": lp}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_with_context(info, path_uid="lp_np")
        assert result is not None
        assert result.completed_steps == 0
        assert result.completion_percentage == 0.0

    @pytest.mark.asyncio
    async def test_blocker_detection_low_progress(self) -> None:
        lp = FakeLearningPath(uid="lp_blk")
        steps = [FakePathStep(uid="ls_1", knowledge_uids=("ku_1",))]

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(return_value=FakeResult(value=steps))

        in_progress_entry = FakeInProgressEntry(knowledge_uid="ku_1", progress=0.1)
        profile = FakeKnowledgeProfile(
            mastered_uids=set(),
            in_progress_uids={"ku_1"},
            in_progress_knowledge=[in_progress_entry],
        )
        services.user_progress.build_user_knowledge_profile = AsyncMock(
            return_value=FakeResult(value=profile)
        )
        services.ps.get_prerequisites = AsyncMock(return_value=FakeResult(value=[]))

        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({"lp_blk": lp}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_with_context(info, path_uid="lp_blk")

        assert result is not None
        assert len(result.blockers) == 1
        assert result.blockers[0].blocker_type == "low_progress"
        assert result.prerequisites_met is False

    @pytest.mark.asyncio
    async def test_blocker_detection_missing_prerequisite(self) -> None:
        lp = FakeLearningPath(uid="lp_prereq")
        steps = [FakePathStep(uid="ls_1", knowledge_uids=("ku_adv",))]

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(return_value=FakeResult(value=steps))

        profile = FakeKnowledgeProfile(mastered_uids=set())
        services.user_progress.build_user_knowledge_profile = AsyncMock(
            return_value=FakeResult(value=profile)
        )

        prereq_ku = FakeKU(uid="ku_basic", title="Basics")
        services.ps.get_prerequisites = AsyncMock(return_value=FakeResult(value=[prereq_ku]))

        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({"lp_prereq": lp}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_with_context(info, path_uid="lp_prereq")

        assert result is not None
        assert len(result.blockers) >= 1
        assert any(b.blocker_type == "missing_prerequisite" for b in result.blockers)


class TestPrerequisiteChainResolver:
    @pytest.mark.asyncio
    async def test_returns_graph(self) -> None:
        target_ku = FakeKU(uid="ku_target", title="Target")
        prereq_ku = FakeKU(uid="ku_prereq", title="Prereq")

        services = MagicMock()
        # First call: prereqs for target -> [prereq_ku]
        # Second call: prereqs for prereq -> []
        services.ps.get_prerequisites = AsyncMock(
            side_effect=[
                FakeResult(value=[prereq_ku]),
                FakeResult(value=[]),
            ]
        )
        services.user_progress.build_user_knowledge_profile = AsyncMock(
            return_value=FakeResult(value=FakeKnowledgeProfile(mastered_uids={"ku_prereq"}))
        )

        ctx = _make_context(
            services=services,
            knowledge_loader=_make_loader({"ku_target": target_ku}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().prerequisite_chain(info, knowledge_uid="ku_target")

        assert result is not None
        assert result.target.uid == "ku_target"
        assert result.total_prerequisites == 1
        assert result.prerequisites_mastered == 1
        assert result.estimated_total_hours == 2.0
        assert len(result.prerequisite_tree) == 1
        assert result.prerequisite_tree[0].is_mastered is True

    @pytest.mark.asyncio
    async def test_ku_not_found(self) -> None:
        services = MagicMock()
        ctx = _make_context(
            services=services,
            knowledge_loader=_make_loader({}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().prerequisite_chain(info, knowledge_uid="ku_missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_ps_service(self) -> None:
        services = MagicMock()
        services.ps = None
        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        result = await Query().prerequisite_chain(info, knowledge_uid="ku_x")
        assert result is None

    @pytest.mark.asyncio
    async def test_cycle_detection(self) -> None:
        """Prerequisite chain should not loop infinitely on cycles."""
        ku_a = FakeKU(uid="ku_a", title="A")
        ku_b = FakeKU(uid="ku_b", title="B")

        services = MagicMock()
        # A requires B, B requires A (cycle)
        services.ps.get_prerequisites = AsyncMock(
            side_effect=[
                FakeResult(value=[ku_b]),  # prereqs of ku_a
                FakeResult(value=[ku_a]),  # prereqs of ku_b — cycle!
            ]
        )
        services.user_progress.build_user_knowledge_profile = AsyncMock(
            return_value=FakeResult(value=FakeKnowledgeProfile())
        )

        ctx = _make_context(
            services=services,
            knowledge_loader=_make_loader({"ku_a": ku_a}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().prerequisite_chain(info, knowledge_uid="ku_a")

        assert result is not None
        # Should terminate — ku_a is visited, so A's recursive children are empty.
        # But B (depth 1) and A (depth 2, leaf) are both counted as prereqs.
        assert result.total_prerequisites == 2
        # Tree: B -> [A (no children because visited)]
        assert len(result.prerequisite_tree) == 1  # Only B at top level
        assert (
            result.prerequisite_tree[0].children[0].children == []
        )  # A has no children (cycle stopped)

    @pytest.mark.asyncio
    async def test_max_depth_respected(self) -> None:
        """Deep chains should be capped at max_depth."""
        ku = FakeKU(uid="ku_root", title="Root")

        services = MagicMock()
        # Always return a prereq to create an infinite chain
        services.ps.get_prerequisites = AsyncMock(
            return_value=FakeResult(value=[FakeKU(uid="ku_deep", title="Deep")])
        )
        services.user_progress.build_user_knowledge_profile = AsyncMock(
            return_value=FakeResult(value=FakeKnowledgeProfile())
        )

        ctx = _make_context(
            services=services,
            knowledge_loader=_make_loader({"ku_root": ku}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        # max_depth=1 should only traverse one level
        result = await Query().prerequisite_chain(info, knowledge_uid="ku_root", max_depth=1)

        assert result is not None
        assert result.total_prerequisites == 1


class TestKnowledgeDependenciesResolver:
    @pytest.mark.asyncio
    async def test_returns_graph(self) -> None:
        center = FakeKU(uid="ku_center", title="Center")
        prereq = FakeKU(uid="ku_prereq", title="Prereq")
        enabled = FakeKU(uid="ku_enabled", title="Enabled")

        services = MagicMock()
        services.ps.get_prerequisites = AsyncMock(return_value=FakeResult(value=[prereq]))
        services.ps.get_enables = AsyncMock(return_value=FakeResult(value=[enabled]))

        ctx = _make_context(
            services=services,
            knowledge_loader=_make_loader({"ku_center": center}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().knowledge_dependencies(info, knowledge_uid="ku_center")

        assert result is not None
        assert result.center.uid == "ku_center"
        assert len(result.nodes) == 3  # center + prereq + enabled
        assert len(result.edges) == 2
        assert result.depth == 2

        edge_types = {e.relationship_type for e in result.edges}
        assert "REQUIRES" in edge_types
        assert "ENABLES" in edge_types

    @pytest.mark.asyncio
    async def test_ku_not_found(self) -> None:
        services = MagicMock()
        ctx = _make_context(
            services=services,
            knowledge_loader=_make_loader({}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().knowledge_dependencies(info, knowledge_uid="ku_gone")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_ps_service(self) -> None:
        services = MagicMock()
        services.ps = None
        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        result = await Query().knowledge_dependencies(info, knowledge_uid="ku_x")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_relationships(self) -> None:
        center = FakeKU(uid="ku_alone", title="Alone")
        services = MagicMock()
        services.ps.get_prerequisites = AsyncMock(return_value=FakeResult(value=[]))
        services.ps.get_enables = AsyncMock(return_value=FakeResult(value=[]))

        ctx = _make_context(
            services=services,
            knowledge_loader=_make_loader({"ku_alone": center}),
        )
        info = _make_info(ctx)

        result = await Query().knowledge_dependencies(info, knowledge_uid="ku_alone")
        assert result is not None
        assert len(result.nodes) == 1
        assert len(result.edges) == 0


class TestLearningPathBlockersResolver:
    @pytest.mark.asyncio
    async def test_missing_content_blocker(self) -> None:
        lp = FakeLearningPath(uid="lp_blk")
        steps = [FakePathStep(uid="ls_1", knowledge_uids=("ku_gone",))]

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(return_value=FakeResult(value=steps))
        services.ps = MagicMock()  # exists but KU loader returns None

        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({"lp_blk": lp}),
            knowledge_loader=_make_loader({}),  # ku_gone not found
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_blockers(info, path_uid="lp_blk")
        assert len(result) == 1
        assert result[0].blocker_type == "missing_content"
        assert result[0].severity == "critical"

    @pytest.mark.asyncio
    async def test_deprecated_content_blocker(self) -> None:
        lp = FakeLearningPath(uid="lp_dep")
        steps = [FakePathStep(uid="ls_1", knowledge_uids=("ku_old",))]

        deprecated_ku = FakeKU(
            uid="ku_old",
            title="Old KU",
            metadata={"deprecated": True},
        )

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(return_value=FakeResult(value=steps))
        services.ps.get_prerequisites = AsyncMock(return_value=FakeResult(value=[]))
        services.user = None  # Skip mastery checks

        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({"lp_dep": lp}),
            knowledge_loader=_make_loader({"ku_old": deprecated_ku}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_blockers(info, path_uid="lp_dep")
        assert any(b.blocker_type == "deprecated_content" for b in result)

    @pytest.mark.asyncio
    async def test_circular_dependency_blocker(self) -> None:
        lp = FakeLearningPath(uid="lp_circ")
        step1 = FakePathStep(uid="ls_1", knowledge_uids=("ku_1",))
        step2 = FakePathStep(uid="ls_2", knowledge_uids=("ku_2",))

        ku1 = FakeKU(uid="ku_1", title="KU 1")
        ku2 = FakeKU(uid="ku_2", title="KU 2")

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(return_value=FakeResult(value=[step1, step2]))
        # Step 1 requires ku_2 (which is step 2's knowledge) → circular
        prereq_ku2 = FakeKU(uid="ku_2", title="KU 2")
        services.ps.get_prerequisites = AsyncMock(
            side_effect=[
                FakeResult(value=[prereq_ku2]),  # step1 prereqs
                FakeResult(value=[]),  # step2 prereqs
            ]
        )
        services.user = None

        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({"lp_circ": lp}),
            knowledge_loader=_make_loader({"ku_1": ku1, "ku_2": ku2}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_blockers(info, path_uid="lp_circ")
        circular = [b for b in result if b.blocker_type == "circular_dependency"]
        assert len(circular) == 1
        assert "circular" in circular[0].description.lower()

    @pytest.mark.asyncio
    async def test_path_not_found(self) -> None:
        services = MagicMock()
        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_blockers(info, path_uid="lp_missing")
        assert result == []

    @pytest.mark.asyncio
    async def test_no_services(self) -> None:
        services = MagicMock()
        services.lp = None
        services.ps = None
        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        result = await Query().learning_path_blockers(info, path_uid="lp_x")
        assert result == []

    @pytest.mark.asyncio
    async def test_outdated_content_blocker(self) -> None:
        lp = FakeLearningPath(uid="lp_out")
        steps = [FakePathStep(uid="ls_1", knowledge_uids=("ku_stale",))]

        stale_ku = FakeKU(
            uid="ku_stale",
            title="Stale KU",
            metadata={"deprecated": False, "outdated": True},
        )

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(return_value=FakeResult(value=steps))
        services.ps.get_prerequisites = AsyncMock(return_value=FakeResult(value=[]))
        services.user = None

        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({"lp_out": lp}),
            knowledge_loader=_make_loader({"ku_stale": stale_ku}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_blockers(info, path_uid="lp_out")
        assert any(b.blocker_type == "outdated_content" for b in result)

    @pytest.mark.asyncio
    async def test_step_with_no_knowledge_uid_skipped(self) -> None:
        lp = FakeLearningPath(uid="lp_skip")
        steps = [FakePathStep(uid="ls_1", knowledge_uids=())]

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(return_value=FakeResult(value=steps))
        services.ps = MagicMock()

        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({"lp_skip": lp}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_blockers(info, path_uid="lp_skip")
        assert result == []


class TestDiscoverCrossDomainResolver:
    @pytest.mark.asyncio
    async def test_no_cross_domain_service(self) -> None:
        services = MagicMock()
        services.cross_domain = None
        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        result = await Query().discover_cross_domain(info, user_knowledge=["ku_1"])
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_opportunities(self) -> None:
        services = MagicMock()
        services.cross_domain.discover_cross_domain_opportunities = MagicMock(
            return_value=FakeResult(value=[])
        )

        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        result = await Query().discover_cross_domain(info, user_knowledge=["ku_1"])
        assert result == []

    @pytest.mark.asyncio
    async def test_with_opportunities(self) -> None:
        opp = MagicMock()
        opp.source_knowledge_uids = ["ku_src"]
        opp.target_knowledge_uids = ["ku_tgt"]
        opp.source_domain.value = "tech"
        opp.target_domain.value = "business"
        opp.application_type = "skill_transfer"
        opp.skill_transfer_potential = 0.8
        opp.estimated_difficulty = 5
        opp.description = "Apply tech skills to business"
        opp.practical_projects = ["Project A"]
        opp.success_patterns = None
        opp.supporting_examples = None

        services = MagicMock()
        services.cross_domain.discover_cross_domain_opportunities = MagicMock(
            return_value=FakeResult(value=[opp])
        )

        src_ku = FakeKU(uid="ku_src", title="Tech KU")
        tgt_ku = FakeKU(uid="ku_tgt", title="Biz KU")

        ctx = _make_context(
            services=services,
            knowledge_loader=_make_loader({"ku_src": src_ku, "ku_tgt": tgt_ku}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().discover_cross_domain(info, user_knowledge=["ku_src"])
        assert len(result) == 1
        assert result[0].source.uid == "ku_src"
        assert result[0].target.uid == "ku_tgt"
        assert result[0].transferability == 0.8

    @pytest.mark.asyncio
    async def test_fallback_nodes_when_kus_not_found(self) -> None:
        opp = MagicMock()
        opp.source_knowledge_uids = []  # No specific KU
        opp.target_knowledge_uids = []
        opp.source_domain.value = "tech"
        opp.target_domain.value = "personal"
        opp.application_type = "bridge"
        opp.skill_transfer_potential = 0.5
        opp.estimated_difficulty = 3
        opp.description = "Bridge"
        opp.practical_projects = None
        opp.success_patterns = None
        opp.supporting_examples = None

        services = MagicMock()
        services.cross_domain.discover_cross_domain_opportunities = MagicMock(
            return_value=FakeResult(value=[opp])
        )

        ctx = _make_context(
            services=services,
            knowledge_loader=_make_loader({}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().discover_cross_domain(info, user_knowledge=[])
        assert len(result) == 1
        # Fallback nodes created with domain prefix
        assert result[0].source.uid == "domain.tech"
        assert result[0].target.uid == "domain.personal"


# ============================================================================
# Mutation & Subscription tests
# ============================================================================


class TestMutationPlaceholder:
    @pytest.mark.asyncio
    async def test_placeholder(self) -> None:
        from adapters.inbound.graphql.schema import Mutation

        result = Mutation().placeholder()
        assert "REST API" in result


# ============================================================================
# Schema factory test
# ============================================================================


class TestCreateGraphqlSchema:
    def test_creates_schema(self) -> None:
        schema = create_graphql_schema()
        assert isinstance(schema, strawberry.Schema)

    def test_schema_has_query_type(self) -> None:
        schema = create_graphql_schema()
        # Strawberry schema should have query type
        sdl = schema.as_str()
        assert "type Query" in sdl
        assert "knowledgeUnit" in sdl
        assert "tasks" in sdl
        assert "learningPath" in sdl
        assert "userDashboard" in sdl

    def test_schema_has_mutation_type(self) -> None:
        schema = create_graphql_schema()
        sdl = schema.as_str()
        assert "type Mutation" in sdl

    def test_schema_has_subscription_type(self) -> None:
        schema = create_graphql_schema()
        sdl = schema.as_str()
        assert "type Subscription" in sdl
        assert "learningProgress" in sdl


# ============================================================================
# GraphQLQueryHelpers tests
# ============================================================================


class TestGraphQLQueryHelpers:
    @pytest.mark.asyncio
    async def test_get_prerequisites(self) -> None:
        from adapters.inbound.graphql.query_helpers import GraphQLQueryHelpers

        services = MagicMock()
        services.ps.get_prerequisites = AsyncMock(
            return_value=FakeResult(value=[FakeKU(uid="ku_prereq", title="Prereq")])
        )
        ctx = _make_context(services=services)

        result = await GraphQLQueryHelpers.get_prerequisites(ctx, "ku_1")
        assert len(result) == 1
        assert result[0].uid == "ku_prereq"

    @pytest.mark.asyncio
    async def test_get_prerequisites_no_service(self) -> None:
        from adapters.inbound.graphql.query_helpers import GraphQLQueryHelpers

        services = MagicMock()
        services.ps = None
        ctx = _make_context(services=services)

        result = await GraphQLQueryHelpers.get_prerequisites(ctx, "ku_1")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_enables(self) -> None:
        from adapters.inbound.graphql.query_helpers import GraphQLQueryHelpers

        services = MagicMock()
        services.ps.get_enables = AsyncMock(
            return_value=FakeResult(value=[FakeKU(uid="ku_en", title="Enabled")])
        )
        ctx = _make_context(services=services)

        result = await GraphQLQueryHelpers.get_enables(ctx, "ku_1")
        assert len(result) == 1
        assert result[0].uid == "ku_en"

    @pytest.mark.asyncio
    async def test_get_enables_no_service(self) -> None:
        from adapters.inbound.graphql.query_helpers import GraphQLQueryHelpers

        services = MagicMock()
        services.ps = None
        ctx = _make_context(services=services)

        result = await GraphQLQueryHelpers.get_enables(ctx, "ku_1")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_task_knowledge_returns_none(self) -> None:
        from adapters.inbound.graphql.query_helpers import GraphQLQueryHelpers

        ctx = _make_context()
        result = GraphQLQueryHelpers.get_task_knowledge(ctx, "task_1")
        assert result is None


# ============================================================================
# Type resolver tests (nested field resolvers on types.py)
# ============================================================================


class TestKnowledgeNodeResolvers:
    @pytest.mark.asyncio
    async def test_prerequisites_resolver(self) -> None:
        services = MagicMock()
        services.ps.get_prerequisites = AsyncMock(
            return_value=FakeResult(value=[FakeKU(uid="ku_p1")])
        )
        ctx = _make_context(services=services)
        info = _make_info(ctx)

        node = KnowledgeNode(
            uid="ku_center",
            title="Center",
            summary="",
            domain="tech",
            tags=[],
            quality_score=0.9,
        )
        result = await node.prerequisites(info)
        assert len(result) == 1
        assert result[0].uid == "ku_p1"

    @pytest.mark.asyncio
    async def test_enables_resolver(self) -> None:
        services = MagicMock()
        services.ps.get_enables = AsyncMock(return_value=FakeResult(value=[FakeKU(uid="ku_e1")]))
        ctx = _make_context(services=services)
        info = _make_info(ctx)

        node = KnowledgeNode(
            uid="ku_center",
            title="Center",
            summary="",
            domain="tech",
            tags=[],
            quality_score=0.9,
        )
        result = await node.enables(info)
        assert len(result) == 1
        assert result[0].uid == "ku_e1"


class TestTaskKnowledgeResolver:
    @pytest.mark.asyncio
    async def test_returns_none(self) -> None:
        from adapters.inbound.graphql.types import Task

        ctx = _make_context()
        info = _make_info(ctx)

        task = Task(uid="t1", title="T", description="", status="active", priority="high")
        result = task.knowledge(info)
        assert result is None


class TestLearningPathStepsResolver:
    @pytest.mark.asyncio
    async def test_returns_steps(self) -> None:
        from adapters.inbound.graphql.types import LearningPath

        steps = [
            FakePathStep(uid="ls_1", title="Step 1"),
            FakePathStep(uid="ls_2", title="Step 2"),
        ]

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(return_value=FakeResult(value=steps))

        ctx = _make_context(services=services)
        info = _make_info(ctx)

        lp = LearningPath(uid="lp_1", name="Path", goal="Learn", total_steps=2, estimated_hours=5.0)
        result = await lp.steps(info)
        assert len(result) == 2
        assert result[0].step_number == 1
        assert result[1].step_number == 2

    @pytest.mark.asyncio
    async def test_no_lp_service(self) -> None:
        from adapters.inbound.graphql.types import LearningPath

        services = MagicMock()
        services.lp = None
        ctx = _make_context(services=services)
        info = _make_info(ctx)

        lp = LearningPath(uid="lp_1", name="P", goal="", total_steps=0, estimated_hours=0.0)
        result = await lp.steps(info)
        assert result == []


class TestPathStepKnowledgeResolver:
    @pytest.mark.asyncio
    async def test_found(self) -> None:
        from adapters.inbound.graphql.types import PathStep

        ku = FakeKU(uid="ku_1", title="Found")
        ctx = _make_context(knowledge_loader=_make_loader({"ku_1": ku}))
        info = _make_info(ctx)

        step = PathStep(
            step_number=1,
            uid="ls_1",
            title="S",
            knowledge_uid="ku_1",
            mastery_threshold=0.8,
            estimated_time=2.0,
        )
        result = await step.knowledge(info)
        assert result is not None
        assert result.uid == "ku_1"

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        from adapters.inbound.graphql.types import PathStep

        ctx = _make_context(knowledge_loader=_make_loader({}))
        info = _make_info(ctx)

        step = PathStep(
            step_number=1,
            uid="ls_1",
            title="S",
            knowledge_uid="ku_gone",
            mastery_threshold=0.8,
            estimated_time=2.0,
        )
        result = await step.knowledge(info)
        assert result is None


# ============================================================================
# Coverage gap tests — remaining uncovered lines in schema.py
# ============================================================================


class TestDiscoverCrossDomainTargetDomains:
    """Cover lines 366-372: target_domains parsing with valid and invalid domains."""

    @pytest.mark.asyncio
    async def test_valid_target_domains_parsed(self) -> None:
        opp = MagicMock()
        opp.source_knowledge_uids = []
        opp.target_knowledge_uids = []
        opp.source_domain.value = "tech"
        opp.target_domain.value = "business"
        opp.application_type = "transfer"
        opp.skill_transfer_potential = 0.6
        opp.estimated_difficulty = 4
        opp.description = "Cross-domain"
        opp.practical_projects = None
        opp.success_patterns = None
        opp.supporting_examples = None

        services = MagicMock()
        services.cross_domain.discover_cross_domain_opportunities = MagicMock(
            return_value=FakeResult(value=[opp])
        )

        ctx = _make_context(
            services=services,
            knowledge_loader=_make_loader({}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        # Pass target_domains — exercises the parsing loop (lines 366-372)
        result = await Query().discover_cross_domain(
            info,
            user_knowledge=["ku_1"],
            target_domains=["TECH", "BUSINESS"],
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_invalid_target_domains_skipped(self) -> None:
        opp = MagicMock()
        opp.source_knowledge_uids = []
        opp.target_knowledge_uids = []
        opp.source_domain.value = "tech"
        opp.target_domain.value = "tech"
        opp.application_type = "bridge"
        opp.skill_transfer_potential = 0.5
        opp.estimated_difficulty = 3
        opp.description = "Test"
        opp.practical_projects = None
        opp.success_patterns = None
        opp.supporting_examples = None

        services = MagicMock()
        services.cross_domain.discover_cross_domain_opportunities = MagicMock(
            return_value=FakeResult(value=[opp])
        )

        ctx = _make_context(
            services=services,
            knowledge_loader=_make_loader({}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        # Mix of valid and invalid domains — invalid ones skipped (line 371-372)
        result = await Query().discover_cross_domain(
            info,
            user_knowledge=[],
            target_domains=["INVALID_XYZ", "TECH"],
        )
        assert len(result) == 1


class TestLearningPathWithContextStepNoKuUid:
    """Cover line 558: step with no knowledge_uids skipped in blocker check."""

    @pytest.mark.asyncio
    async def test_step_with_empty_ku_uids_skipped(self) -> None:
        lp = FakeLearningPath(uid="lp_empty_ku")
        # Step has no knowledge UIDs — should be skipped in blocker analysis
        step_no_ku = FakePathStep(uid="ls_no_ku", knowledge_uids=())
        step_with_ku = FakePathStep(uid="ls_with_ku", knowledge_uids=("ku_1",))

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(
            return_value=FakeResult(value=[step_no_ku, step_with_ku])
        )

        # Profile: ku_1 is mastered, so no blockers for it
        profile = FakeKnowledgeProfile(mastered_uids={"ku_1"})
        services.user_progress.build_user_knowledge_profile = AsyncMock(
            return_value=FakeResult(value=profile)
        )
        services.ps.get_prerequisites = AsyncMock(return_value=FakeResult(value=[]))

        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({"lp_empty_ku": lp}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_with_context(info, path_uid="lp_empty_ku")
        assert result is not None
        # Step with no KU should be skipped — no errors, no blockers
        assert result.prerequisites_met is True


class TestPrerequisiteChainPsNullInRecursion:
    """Cover line 692: PS service becomes None during recursive build."""

    @pytest.mark.asyncio
    async def test_ps_service_none_during_recursion(self) -> None:
        ku = FakeKU(uid="ku_root", title="Root")
        prereq = FakeKU(uid="ku_child", title="Child")

        services = MagicMock()
        # First call returns prereqs; then we set ps to None so the
        # recursive call for ku_child hits line 692
        call_count = 0

        async def get_prereqs_then_none(uid: str) -> FakeResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return FakeResult(value=[prereq])
            # Simulate lesson service becoming unavailable
            services.ps = None
            return FakeResult(value=[])

        services.ps.get_prerequisites = AsyncMock(side_effect=get_prereqs_then_none)
        services.user_progress.build_user_knowledge_profile = AsyncMock(
            return_value=FakeResult(value=FakeKnowledgeProfile())
        )

        ctx = _make_context(
            services=services,
            knowledge_loader=_make_loader({"ku_root": ku}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().prerequisite_chain(info, knowledge_uid="ku_root")
        assert result is not None
        # Root has 1 prereq (ku_child), but ku_child's recursive lookup returns empty
        # because lesson is now None
        assert result.total_prerequisites == 1


class TestLearningPathBlockersEmptySteps:
    """Cover line 879: path found but get_path_steps returns empty."""

    @pytest.mark.asyncio
    async def test_empty_steps_returns_empty_blockers(self) -> None:
        lp = FakeLearningPath(uid="lp_empty_steps")

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(
            return_value=FakeResult(value=[])  # Empty steps!
        )
        services.ps = MagicMock()

        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({"lp_empty_steps": lp}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_blockers(info, path_uid="lp_empty_steps")
        assert result == []


class TestLearningPathBlockersMasteryCheck:
    """Cover lines 917-926: mastery check via user_service.get_user_mastery."""

    @pytest.mark.asyncio
    async def test_mastered_prereqs_no_blocker(self) -> None:
        """When user has mastered all prereqs, no blocker is created."""
        lp = FakeLearningPath(uid="lp_mastery")
        steps = [FakePathStep(uid="ls_1", knowledge_uids=("ku_adv",))]
        ku_adv = FakeKU(uid="ku_adv", title="Advanced")
        prereq = FakeKU(uid="ku_basic", title="Basic")

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(return_value=FakeResult(value=steps))
        services.ps.get_prerequisites = AsyncMock(return_value=FakeResult(value=[prereq]))
        # user_service returns mastery score above threshold (0.7)
        services.user.get_user_mastery = AsyncMock(return_value=FakeResult(value=0.9))

        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({"lp_mastery": lp}),
            knowledge_loader=_make_loader({"ku_adv": ku_adv}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_blockers(info, path_uid="lp_mastery")
        # No missing_prerequisite blockers since mastery >= 0.7
        prereq_blockers = [b for b in result if b.blocker_type == "missing_prerequisite"]
        assert len(prereq_blockers) == 0

    @pytest.mark.asyncio
    async def test_low_mastery_creates_blocker(self) -> None:
        """When user mastery is below threshold, a blocker is created."""
        lp = FakeLearningPath(uid="lp_low")
        steps = [FakePathStep(uid="ls_1", knowledge_uids=("ku_adv",))]
        ku_adv = FakeKU(uid="ku_adv", title="Advanced")
        prereq = FakeKU(uid="ku_basic", title="Basic")

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(return_value=FakeResult(value=steps))
        services.ps.get_prerequisites = AsyncMock(return_value=FakeResult(value=[prereq]))
        # user_service returns mastery score below threshold
        services.user.get_user_mastery = AsyncMock(return_value=FakeResult(value=0.3))

        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({"lp_low": lp}),
            knowledge_loader=_make_loader({"ku_adv": ku_adv}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_blockers(info, path_uid="lp_low")
        prereq_blockers = [b for b in result if b.blocker_type == "missing_prerequisite"]
        assert len(prereq_blockers) == 1
        assert "Basic" in prereq_blockers[0].description

    @pytest.mark.asyncio
    async def test_mastery_error_treated_as_not_mastered(self) -> None:
        """When get_user_mastery returns error, treat as not mastered (line 924-926)."""
        lp = FakeLearningPath(uid="lp_err")
        steps = [FakePathStep(uid="ls_1", knowledge_uids=("ku_adv",))]
        ku_adv = FakeKU(uid="ku_adv", title="Advanced")
        prereq = FakeKU(uid="ku_basic", title="Basic")

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(return_value=FakeResult(value=steps))
        services.ps.get_prerequisites = AsyncMock(return_value=FakeResult(value=[prereq]))
        # user_service returns error
        services.user.get_user_mastery = AsyncMock(return_value=FakeResult(error="DB error"))

        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({"lp_err": lp}),
            knowledge_loader=_make_loader({"ku_adv": ku_adv}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_blockers(info, path_uid="lp_err")
        prereq_blockers = [b for b in result if b.blocker_type == "missing_prerequisite"]
        assert len(prereq_blockers) == 1


class TestLearningPathBlockersPrereqTruncation:
    """Cover line 938: more than 3 unmet prereqs triggers truncation."""

    @pytest.mark.asyncio
    async def test_four_plus_prereqs_truncated(self) -> None:
        lp = FakeLearningPath(uid="lp_trunc")
        steps = [FakePathStep(uid="ls_1", knowledge_uids=("ku_main",))]
        ku_main = FakeKU(uid="ku_main", title="Main")

        # 5 unmet prerequisites
        prereqs = [FakeKU(uid=f"ku_p{i}", title=f"Prereq {i}") for i in range(5)]

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(return_value=FakeResult(value=steps))
        services.ps.get_prerequisites = AsyncMock(return_value=FakeResult(value=prereqs))
        # All prereqs not mastered
        services.user.get_user_mastery = AsyncMock(return_value=FakeResult(value=0.1))

        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({"lp_trunc": lp}),
            knowledge_loader=_make_loader({"ku_main": ku_main}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_blockers(info, path_uid="lp_trunc")
        prereq_blockers = [b for b in result if b.blocker_type == "missing_prerequisite"]
        assert len(prereq_blockers) == 1
        assert "(+2 more)" in prereq_blockers[0].description
        assert "5 prerequisite" in prereq_blockers[0].description


class TestLearningPathBlockersLaterStepNoKuUid:
    """Cover line 961: later step with no knowledge_uids in circular dep check."""

    @pytest.mark.asyncio
    async def test_later_step_no_ku_uid_skipped(self) -> None:
        lp = FakeLearningPath(uid="lp_later_no_ku")
        step1 = FakePathStep(uid="ls_1", knowledge_uids=("ku_1",))
        step2 = FakePathStep(uid="ls_2", knowledge_uids=())  # No KU UID

        ku1 = FakeKU(uid="ku_1", title="KU 1")

        services = MagicMock()
        services.lp.get_path_steps = AsyncMock(return_value=FakeResult(value=[step1, step2]))
        services.ps.get_prerequisites = AsyncMock(return_value=FakeResult(value=[]))
        services.user = None

        ctx = _make_context(
            services=services,
            lp_loader=_make_loader({"lp_later_no_ku": lp}),
            knowledge_loader=_make_loader({"ku_1": ku1}),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        result = await Query().learning_path_blockers(info, path_uid="lp_later_no_ku")
        # No circular dependency blocker — later step has no KU to check
        circular = [b for b in result if b.blocker_type == "circular_dependency"]
        assert len(circular) == 0


# ============================================================================
# Subscription tests — lines 1107-1153
# ============================================================================


class TestLearningProgressSubscription:
    @pytest.mark.asyncio
    async def test_override_by_non_admin_raises(self) -> None:
        """An explicit user_uid override requires ADMIN (resolve_target_user).

        A non-admin caller is rejected before any event-bus subscription —
        fail-closed, so the resolver never leaks another user's progress.
        """
        from adapters.inbound.graphql.schema import Subscription

        user_service = AsyncMock()
        caller_user = MagicMock()
        caller_user.has_permission.return_value = False
        user_service.get_user.return_value = FakeResult(value=caller_user)

        event_bus = MagicMock()
        services = MagicMock()
        services.user = user_service
        services.event_bus = event_bus

        ctx = _make_context(services=services, user_uid="user_caller")
        info = _make_info(ctx)

        sub = Subscription()
        with pytest.raises(PermissionError, match="Admin role required"):
            async for _ in sub.learning_progress(info, path_uid="lp_1", user_uid="user_victim"):
                pass

        # Auth failed before streaming — no subscription side effect leaked.
        event_bus.subscribe.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_event_bus_yields_zero(self) -> None:
        """Line 1114-1118: no event bus yields 0.0 and returns."""
        from adapters.inbound.graphql.schema import Subscription

        services = MagicMock()
        services.event_bus = None

        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        sub = Subscription()
        values = [v async for v in sub.learning_progress(info, path_uid="lp_1")]

        assert values == [0.0]

    @pytest.mark.asyncio
    async def test_no_services_yields_zero(self) -> None:
        """Edge case: services object is falsy (line 1112)."""
        from adapters.inbound.graphql.schema import Subscription

        # Bypass _make_context default to actually pass None for services
        ctx = GraphQLContext(
            services=None,  # type: ignore[arg-type]
            search_router=None,
            knowledge_loader=_make_loader(),
            task_loader=_make_loader(),
            learning_path_loader=_make_loader(),
            path_step_loader=_make_loader(),
            user_uid="user_test",
        )
        info = _make_info(ctx)

        sub = Subscription()
        values = [v async for v in sub.learning_progress(info, path_uid="lp_1")]

        assert values == [0.0]

    @pytest.mark.asyncio
    async def test_with_event_bus_subscribes_and_yields(self) -> None:
        """Lines 1120-1142: event bus subscribes, handler filters, generator yields."""
        import asyncio

        from adapters.inbound.graphql.schema import Subscription

        event_bus = MagicMock()
        captured_handler: list[Any] = []

        def fake_subscribe(event_type: type, handler: Any) -> None:
            captured_handler.append(handler)

        event_bus.subscribe = MagicMock(side_effect=fake_subscribe)
        event_bus.unsubscribe = MagicMock()

        services = MagicMock()
        services.event_bus = event_bus

        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        sub = Subscription()
        gen = sub.learning_progress(info, path_uid="lp_1")

        # Pre-patch wait_for so the generator doesn't actually wait 30s.
        # Strategy: on each call, check if the queue has data. If yes, return it.
        # If not, raise TimeoutError (simulating the 30s timeout instantly).
        # After 2 timeouts without data, we'll close the generator.

        original_wait_for = asyncio.wait_for
        wait_call_count = 0

        async def fast_wait_for(coro: Any, timeout: float) -> float:  # noqa: ASYNC109
            nonlocal wait_call_count
            wait_call_count += 1
            # Use a very short timeout so tests don't hang
            return await original_wait_for(coro, timeout=0.1)

        values: list[float] = []

        async def consume_one() -> None:
            """Get exactly one yielded value then stop."""
            async for v in gen:
                values.append(v)
                break

        with patch("asyncio.wait_for", side_effect=fast_wait_for):
            task = asyncio.create_task(consume_one())
            # Give generator time to start and subscribe
            await asyncio.sleep(0.05)

            # Handler should be captured
            assert len(captured_handler) == 1
            handler = captured_handler[0]

            # Non-matching event — filtered (line 1126)
            event_other = MagicMock()
            event_other.user_uid = "user_other"
            event_other.path_uid = "lp_1"
            event_other.new_progress = 0.99
            handler(event_other)

            # Matching event — queued and yielded (lines 1128-1129, 1141-1142)
            event_match = MagicMock()
            event_match.user_uid = "user_test"
            event_match.path_uid = "lp_1"
            event_match.new_progress = 0.5
            handler(event_match)

            await asyncio.wait_for(task, timeout=5.0)

        # Close generator to trigger finally block (lines 1148-1153)
        await gen.aclose()

        assert values == [0.5]
        event_bus.unsubscribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_continues_loop(self) -> None:
        """Line 1143-1146: TimeoutError triggers continue (keepalive), then next value yielded."""
        import asyncio

        from adapters.inbound.graphql.schema import Subscription

        event_bus = MagicMock()
        captured_handler: list[Any] = []

        def fake_subscribe(event_type: type, handler: Any) -> None:
            captured_handler.append(handler)

        event_bus.subscribe = MagicMock(side_effect=fake_subscribe)
        event_bus.unsubscribe = MagicMock()

        services = MagicMock()
        services.event_bus = event_bus

        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        sub = Subscription()
        gen = sub.learning_progress(info, path_uid="lp_1")

        original_wait_for = asyncio.wait_for
        call_count = 0

        async def mock_wait_for(coro: Any, timeout: float) -> float:  # noqa: ASYNC109
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: timeout → continue (line 1143-1146)
                # Must still await the coro to drain the queue.get()
                try:
                    return await original_wait_for(coro, timeout=0.01)
                except TimeoutError:
                    raise
            # Subsequent calls: fast timeout
            return await original_wait_for(coro, timeout=1.0)

        values: list[float] = []

        async def consume_one() -> None:
            async for v in gen:
                values.append(v)
                break

        with patch("asyncio.wait_for", side_effect=mock_wait_for):
            task = asyncio.create_task(consume_one())
            await asyncio.sleep(0.05)

            # Push event after the first timeout/continue
            handler = captured_handler[0]
            event = MagicMock()
            event.user_uid = "user_test"
            event.path_uid = "lp_1"
            event.new_progress = 0.42
            handler(event)

            await asyncio.wait_for(task, timeout=5.0)

        await gen.aclose()

        assert values == [0.42]
        # call_count >= 2 means the first call timed out and we continued
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_unsubscribe_error_suppressed(self) -> None:
        """Line 1150-1153: exception in unsubscribe is silently caught."""
        import asyncio

        from adapters.inbound.graphql.schema import Subscription

        event_bus = MagicMock()
        captured_handler: list[Any] = []

        def fake_subscribe(event_type: type, handler: Any) -> None:
            captured_handler.append(handler)

        event_bus.subscribe = MagicMock(side_effect=fake_subscribe)
        # Unsubscribe raises — the finally block should catch and suppress
        event_bus.unsubscribe = MagicMock(side_effect=RuntimeError("unsubscribe failed"))

        services = MagicMock()
        services.event_bus = event_bus

        ctx = _make_context(services=services, user_uid="user_test")
        info = _make_info(ctx)

        sub = Subscription()
        gen = sub.learning_progress(info, path_uid="lp_1")

        original_wait_for = asyncio.wait_for

        async def fast_wait_for(coro: Any, timeout: float) -> float:  # noqa: ASYNC109
            return await original_wait_for(coro, timeout=0.1)

        values: list[float] = []

        async def consume_one() -> None:
            async for v in gen:
                values.append(v)
                break

        with patch("asyncio.wait_for", side_effect=fast_wait_for):
            task = asyncio.create_task(consume_one())
            await asyncio.sleep(0.05)

            # Push a matching event so the consumer can break
            handler = captured_handler[0]
            event = MagicMock()
            event.user_uid = "user_test"
            event.path_uid = "lp_1"
            event.new_progress = 0.7
            handler(event)

            await asyncio.wait_for(task, timeout=5.0)

        # Close the generator — this triggers the finally block where
        # unsubscribe raises RuntimeError, which should be suppressed
        await gen.aclose()

        assert values == [0.7]
        # Unsubscribe was called (and its error was suppressed)
        event_bus.unsubscribe.assert_called_once()
