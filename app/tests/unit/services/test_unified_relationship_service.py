# mypy: disable-error-code="attr-defined"
"""
Unit tests for UnifiedRelationshipService orchestration methods.

Tests focus on:
- Config-validation guard (the keyed readers reject unknown and shared-neighbour keys)
- What a keyed reader carries to the backend: the definition's tier and far-end kind

Cross-domain linking goes through ``create_relationship("<explicit key>", ...)`` straight
from the facades (no candidate-list wrappers); its registry-validation guard is covered by
the ``create_relationship`` path and tests/test_cross_domain_link_keys.py.

Fixture strategy: object.__new__() bypasses the complex __init__ (which requires backend,
DomainRelationshipConfig, SemanticRelationshipLinker, etc.). Sub-attributes are mocked
directly — the same pattern used for LessonService in Phase 2.
"""

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import (
    SharedNeighborConfig,
    UnifiedRelationshipDefinition,
)
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.relationships.unified_relationship_service import UnifiedRelationshipService

# ---------------------------------------------------------------------------
# Helpers — build a minimal UnifiedRelationshipService without __init__
# ---------------------------------------------------------------------------


def _make_spec(method_key: str) -> UnifiedRelationshipDefinition:
    """Return a minimal, untiered relationship definition reaching every kind."""
    return UnifiedRelationshipDefinition(
        relationship=RelationshipName.APPLIES_KNOWLEDGE,
        target_label=NeoLabel.ENTITY,
        direction="outgoing",
        context_field_name=method_key,
        method_key=method_key,
    )


def _make_service(
    known_keys: list[str] | None = None,
    specs: dict[str, UnifiedRelationshipDefinition] | None = None,
    execute_query_return: Result | None = None,
    get_related_uids_return: Result | None = None,
    count_related_return: Result | None = None,
    create_relationship_return: Result | None = None,
) -> UnifiedRelationshipService:
    """
    Build a UnifiedRelationshipService instance without calling __init__.

    Args:
        known_keys: Relationship keys the mock config will recognise.
        specs: Definitions the mock config resolves by key, beside ``known_keys``.
        execute_query_return: What backend.execute_query should return.
        get_related_uids_return: What backend.get_related_uids should return.
        count_related_return: What backend.count_related should return.
        create_relationship_return: What service.create_relationship should return.

    Returns:
        A partially-initialised UnifiedRelationshipService.
    """
    from core.services.relationships.unified_relationship_service import UnifiedRelationshipService

    service = object.__new__(UnifiedRelationshipService)

    # Config mock: get_relationship_by_method returns a spec for known keys, None otherwise
    config = Mock()
    config.entity_label = "Task"
    config.domain = Mock(value="tasks")

    def _get_rel(key: str) -> UnifiedRelationshipDefinition | None:
        if specs and key in specs:
            return specs[key]
        if known_keys and key in known_keys:
            return _make_spec(key)
        return None

    config.get_relationship_by_method = Mock(side_effect=_get_rel)
    service.config = config

    # Backend mock
    backend = Mock()
    backend.get_related_uids = AsyncMock(
        return_value=get_related_uids_return or Result.ok(["uid_1", "uid_2"])
    )
    backend.count_related = AsyncMock(return_value=count_related_return or Result.ok(1))
    backend.batch_get_related_uids = AsyncMock(return_value=Result.ok({"task_abc": ["uid_1"]}))
    backend.execute_query = AsyncMock(
        return_value=execute_query_return or Result.ok([{"success": True}])
    )
    service.backend = backend

    # Logger
    service.logger = Mock()

    # create_relationship: override at service level (bypasses backend)
    service.create_relationship = AsyncMock(
        return_value=create_relationship_return or Result.ok(True)
    )

    return service


# ---------------------------------------------------------------------------
# TestGetRelatedUids
# ---------------------------------------------------------------------------


class TestGetRelatedUids:
    @pytest.mark.asyncio
    async def test_unknown_key_returns_validation_error(self) -> None:
        """get_related_uids fails with validation error when key is not in config."""
        service = _make_service(known_keys=["knowledge"])

        result = await service.get_related_uids("not_a_real_key", "task_abc")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_known_key_delegates_to_backend(self) -> None:
        """get_related_uids delegates to backend.get_related_uids for valid key."""
        service = _make_service(known_keys=["knowledge"])

        result = await service.get_related_uids("knowledge", "task_abc")

        assert result.is_ok
        service.backend.get_related_uids.assert_called_once()

    @pytest.mark.asyncio
    async def test_backend_error_is_propagated(self) -> None:
        """Backend failure from get_related_uids is propagated as-is."""
        service = _make_service(
            known_keys=["knowledge"],
            get_related_uids_return=Result.fail(Errors.database("get", "DB down")),
        )

        result = await service.get_related_uids("knowledge", "task_abc")

        assert result.is_error


# ---------------------------------------------------------------------------
# TestHasRelationship
# ---------------------------------------------------------------------------


class TestHasRelationship:
    @pytest.mark.asyncio
    async def test_unknown_key_returns_validation_error(self) -> None:
        """has_relationship fails with validation error for unknown key."""
        service = _make_service(known_keys=["knowledge"])

        result = await service.has_relationship("unknown_key", "task_abc")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_count_zero_returns_false(self) -> None:
        """has_relationship returns False when count_related returns 0."""
        service = _make_service(
            known_keys=["knowledge"],
            count_related_return=Result.ok(0),
        )

        result = await service.has_relationship("knowledge", "task_abc")

        assert result.is_ok
        assert result.value is False

    @pytest.mark.asyncio
    async def test_count_nonzero_returns_true(self) -> None:
        """has_relationship returns True when count_related returns > 0."""
        service = _make_service(
            known_keys=["knowledge"],
            count_related_return=Result.ok(3),
        )

        result = await service.has_relationship("knowledge", "task_abc")

        assert result.is_ok
        assert result.value is True

    @pytest.mark.asyncio
    async def test_backend_count_error_is_propagated(self) -> None:
        """Backend failure from count_related propagates as Result.fail."""
        service = _make_service(
            known_keys=["knowledge"],
            count_related_return=Result.fail(Errors.database("count", "DB error")),
        )

        result = await service.has_relationship("knowledge", "task_abc")

        assert result.is_error


# ---------------------------------------------------------------------------
# TestKeyedReadCarriesTheDefinition
# ---------------------------------------------------------------------------

TIERED_HABITS = UnifiedRelationshipDefinition(
    relationship=RelationshipName.SUPPORTS_GOAL,
    target_label=NeoLabel.HABIT,
    direction="incoming",
    context_field_name="tiered_habits",
    method_key="tiered_habits",
    filter_property="essentiality",
    filter_value="essential",
)

SHARED_NEIGHBOUR = UnifiedRelationshipDefinition(
    relationship=RelationshipName.APPLIES_KNOWLEDGE,
    target_label=NeoLabel.TASK,
    direction="both",
    context_field_name="related_tasks",
    method_key="related_tasks",
    shared_neighbor_config=SharedNeighborConfig(
        intermediate_relationships=(RelationshipName.APPLIES_KNOWLEDGE,),
        target_label=NeoLabel.TASK,
        result_alias="related_tasks",
    ),
)

# (reader, the backend method it reaches, the anchor argument)
KEYED_READERS = [
    ("get_related_uids", "get_related_uids", "task_abc"),
    ("has_relationship", "count_related", "task_abc"),
    ("batch_get_related_uids", "batch_get_related_uids", ["task_abc"]),
]


class TestKeyedReadCarriesTheDefinition:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("reader", "backend_method", "anchor"), KEYED_READERS)
    async def test_the_tier_and_the_far_end_kind_reach_the_backend(
        self, reader: str, backend_method: str, anchor: object
    ) -> None:
        service = _make_service(specs={"tiered_habits": TIERED_HABITS})

        result = await getattr(service, reader)("tiered_habits", anchor)

        assert result.is_ok
        kwargs = getattr(service.backend, backend_method).call_args.kwargs
        assert kwargs["relationship_type"] == RelationshipName.SUPPORTS_GOAL
        assert kwargs["direction"] == "incoming"
        assert kwargs["properties"] == {"essentiality": "essential"}
        assert kwargs["target_label"] == NeoLabel.HABIT

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("reader", "backend_method", "anchor"), KEYED_READERS)
    async def test_an_entity_far_end_names_no_kind(
        self, reader: str, backend_method: str, anchor: object
    ) -> None:
        service = _make_service(known_keys=["knowledge"])

        await getattr(service, reader)("knowledge", anchor)

        kwargs = getattr(service.backend, backend_method).call_args.kwargs
        assert kwargs["properties"] is None
        assert kwargs["target_label"] is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("reader", "backend_method", "anchor"), KEYED_READERS)
    async def test_a_shared_neighbour_key_is_refused(
        self, reader: str, backend_method: str, anchor: object
    ) -> None:
        service = _make_service(specs={"related_tasks": SHARED_NEIGHBOUR})

        result = await getattr(service, reader)("related_tasks", anchor)

        assert result.is_error
        getattr(service.backend, backend_method).assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("reader", "backend_method", "anchor"), KEYED_READERS)
    async def test_an_unknown_key_is_refused(
        self, reader: str, backend_method: str, anchor: object
    ) -> None:
        service = _make_service(known_keys=["knowledge"])

        result = await getattr(service, reader)("not_a_real_key", anchor)

        assert result.is_error
        getattr(service.backend, backend_method).assert_not_called()
