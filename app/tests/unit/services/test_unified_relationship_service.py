# mypy: disable-error-code="attr-defined"
"""
Unit tests for UnifiedRelationshipService orchestration methods.

Tests focus on:
- Config-validation guard (get_related_uids, has_relationship reject unknown keys)
- Convenience link methods (link_to_knowledge, link_to_goal, link_to_principle try multiple keys)

Fixture strategy: object.__new__() bypasses the complex __init__ (which requires backend,
DomainRelationshipConfig, RelationshipCreator, etc.). Sub-attributes are mocked
directly — the same pattern used for LessonService in Phase 2.
"""

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest

from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.relationships.unified_relationship_service import UnifiedRelationshipService

# ---------------------------------------------------------------------------
# Helpers — build a minimal UnifiedRelationshipService without __init__
# ---------------------------------------------------------------------------


def _make_spec(method_key: str) -> Mock:
    """Return a minimal relationship spec mock for a given method key."""
    spec = Mock()
    spec.relationship = Mock(value="KNOWS")
    spec.direction = "outgoing"
    spec.method_key = method_key
    return spec


def _make_service(
    known_keys: list[str] | None = None,
    execute_query_return: Result | None = None,
    get_related_uids_return: Result | None = None,
    count_related_return: Result | None = None,
    create_relationship_return: Result | None = None,
) -> "UnifiedRelationshipService":
    """
    Build a UnifiedRelationshipService instance without calling __init__.

    Args:
        known_keys: Relationship keys the mock config will recognise.
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

    def _get_rel(key: str) -> Mock | None:
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
# TestLinkToKnowledge
# ---------------------------------------------------------------------------


class TestLinkToKnowledge:
    @pytest.mark.asyncio
    async def test_uses_first_matching_knowledge_key(self) -> None:
        """link_to_knowledge picks first configured key (knowledge > prerequisite_knowledge)."""
        service = _make_service(
            known_keys=["knowledge"],
            create_relationship_return=Result.ok(True),
        )

        result = await service.link_to_knowledge("task_abc", "ku_python_xyz")

        assert result.is_ok
        service.create_relationship.assert_called_once_with(
            relationship_key="knowledge",
            from_uid="task_abc",
            to_uid="ku_python_xyz",
            properties=None,
        )

    @pytest.mark.asyncio
    async def test_falls_back_to_prerequisite_knowledge_key(self) -> None:
        """link_to_knowledge uses prerequisite_knowledge when knowledge key absent."""
        service = _make_service(
            known_keys=["prerequisite_knowledge"],
            create_relationship_return=Result.ok(True),
        )

        result = await service.link_to_knowledge("task_abc", "ku_math_xyz")

        assert result.is_ok
        service.create_relationship.assert_called_once()
        call_args = service.create_relationship.call_args[1]
        assert call_args["relationship_key"] == "prerequisite_knowledge"

    @pytest.mark.asyncio
    async def test_no_knowledge_key_configured_returns_validation_error(self) -> None:
        """link_to_knowledge returns validation error when no knowledge key is configured."""
        service = _make_service(known_keys=["principles"])  # Only principles, no knowledge

        result = await service.link_to_knowledge("task_abc", "ku_python_xyz")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_extra_properties_forwarded(self) -> None:
        """link_to_knowledge passes extra kwargs as properties dict."""
        service = _make_service(
            known_keys=["knowledge"],
            create_relationship_return=Result.ok(True),
        )

        await service.link_to_knowledge("task_abc", "ku_python_xyz", knowledge_score_required=0.8)

        call_args = service.create_relationship.call_args[1]
        assert call_args["properties"] == {"knowledge_score_required": 0.8}


# ---------------------------------------------------------------------------
# TestLinkToGoal
# ---------------------------------------------------------------------------


class TestLinkToGoal:
    @pytest.mark.asyncio
    async def test_uses_first_matching_goal_key(self) -> None:
        """link_to_goal picks first configured goal key."""
        service = _make_service(
            known_keys=["contributes_to_goal"],
            create_relationship_return=Result.ok(True),
        )

        result = await service.link_to_goal("task_abc", "goal_xyz")

        assert result.is_ok
        service.create_relationship.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_goal_key_returns_validation_error(self) -> None:
        """link_to_goal returns validation error when no goal key configured."""
        service = _make_service(known_keys=["knowledge"])

        result = await service.link_to_goal("task_abc", "goal_xyz")

        assert result.is_error


# ---------------------------------------------------------------------------
# TestLinkToPrinciple
# ---------------------------------------------------------------------------


class TestLinkToPrinciple:
    @pytest.mark.asyncio
    async def test_uses_first_matching_principle_key(self) -> None:
        """link_to_principle picks first configured principle key."""
        service = _make_service(
            known_keys=["principles"],
            create_relationship_return=Result.ok(True),
        )

        result = await service.link_to_principle("goal_abc", "principle_xyz")

        assert result.is_ok

    @pytest.mark.asyncio
    async def test_no_principle_key_returns_validation_error(self) -> None:
        """link_to_principle returns validation error when no principle key configured."""
        service = _make_service(known_keys=["knowledge"])

        result = await service.link_to_principle("goal_abc", "principle_xyz")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_extra_properties_forwarded(self) -> None:
        """link_to_principle passes extra kwargs as properties dict."""
        service = _make_service(
            known_keys=["principles"],
            create_relationship_return=Result.ok(True),
        )

        await service.link_to_principle("goal_abc", "principle_xyz", alignment_strength=0.9)

        call_args = service.create_relationship.call_args[1]
        assert call_args["properties"] == {"alignment_strength": 0.9}
