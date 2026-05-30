"""
Integration tests for UniversalNeo4jBackend ↔ BackendOperations conformance.

Covers behavior that a green type-check cannot prove, for the conformance fixes
that aligned the concrete backend with its protocol:

1. ``_TraversalMixin.get_relationships`` now accepts a ``rel_type`` filter and
   applies it in Cypher (the new ``WHERE $rel_type IS NULL OR type(r) = $rel_type``
   clause). It also fixes a reachable runtime bug: the sole caller
   (``RelationshipOperationsMixin.get_relationships``) already passes three
   positional args ``(uid, rel_type, direction)``, which previously mis-bound
   ``rel_type`` to ``direction`` and overflowed with a 3rd positional arg.

2. ``_CrudMixin.list`` now returns ``Result[tuple[list[T], int]]`` (page +
   total count) instead of a bare ``Result[list[T]]`` — matching the protocol,
   the service layer, ``get_user_entities``, and every tuple-unpacking caller.
"""

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.curriculum import Curriculum
from core.models.enums import Domain, EntityStatus, Priority, SELCategory
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task as Task
from core.services.tasks.tasks_core_service import TasksCoreService


@pytest.mark.asyncio
class TestBackendProtocolConformance:
    """Behavioral coverage for the backend conformance fixes."""

    @pytest_asyncio.fixture
    async def tasks_backend(self, neo4j_driver, clean_neo4j):
        """Create tasks backend with a clean database."""
        return UniversalNeo4jBackend[Task](
            neo4j_driver, "Entity", Task, default_filters={"entity_type": "task"}
        )

    @pytest_asyncio.fixture
    async def ku_backend(self, neo4j_driver):
        """Create KU backend for relationship targets."""
        return UniversalNeo4jBackend[Curriculum](neo4j_driver, "Entity", Curriculum)

    @pytest_asyncio.fixture
    async def tasks_service(self, tasks_backend):
        """Create TasksCoreService."""
        return TasksCoreService(backend=tasks_backend)

    # ==========================================================================
    # get_relationships rel_type filter (new Cypher WHERE clause)
    # ==========================================================================

    async def _seed_two_typed_relationships(self, tasks_service, tasks_backend, ku_backend):
        """Create one task with an APPLIES_KNOWLEDGE and a REQUIRES_KNOWLEDGE edge to two KUs."""
        task = Task(
            uid="task:rel_filter_source",
            title="Source Task",
            description="Has two differently-typed outgoing edges",
            user_uid="user_test",
            priority=Priority.MEDIUM,
            status=EntityStatus.DRAFT,
        )
        assert (await tasks_service.create(task)).is_ok

        for slug in ("applies-target", "requires-target"):
            ku = Curriculum(
                uid=f"ku:{slug}",
                title=slug,
                domain=Domain.TECH,
                sel_category=SELCategory.SELF_AWARENESS,
            )
            assert (await ku_backend.create(ku)).is_ok

        rel_result = await tasks_backend.create_relationships_batch(
            [
                ("task:rel_filter_source", "ku:applies-target", "APPLIES_KNOWLEDGE", None),
                ("task:rel_filter_source", "ku:requires-target", "REQUIRES_KNOWLEDGE", None),
            ]
        )
        assert rel_result.is_ok
        assert rel_result.value == 2

    async def test_get_relationships_filters_by_rel_type(
        self, tasks_service, tasks_backend, ku_backend
    ):
        """rel_type narrows the result to edges of exactly that type."""
        await self._seed_two_typed_relationships(tasks_service, tasks_backend, ku_backend)

        applies_only = await tasks_backend.get_relationships(
            "task:rel_filter_source",
            rel_type=RelationshipName.APPLIES_KNOWLEDGE,
            direction="outgoing",
        )
        assert applies_only.is_ok
        assert [r["type"] for r in applies_only.value] == ["APPLIES_KNOWLEDGE"]
        assert applies_only.value[0]["target_uid"] == "ku:applies-target"

    async def test_get_relationships_no_filter_returns_all(
        self, tasks_service, tasks_backend, ku_backend
    ):
        """rel_type=None (the default) leaves all edges in the result."""
        await self._seed_two_typed_relationships(tasks_service, tasks_backend, ku_backend)

        all_rels = await tasks_backend.get_relationships(
            "task:rel_filter_source", direction="outgoing"
        )
        assert all_rels.is_ok
        assert {r["type"] for r in all_rels.value} == {
            "APPLIES_KNOWLEDGE",
            "REQUIRES_KNOWLEDGE",
        }

    async def test_get_relationships_three_positional_args(
        self, tasks_service, tasks_backend, ku_backend
    ):
        """The (uid, rel_type, direction) positional call path no longer TypeErrors.

        Mirrors RelationshipOperationsMixin.get_relationships, which calls
        ``self.backend.get_relationships(uid, rel_type, direction)`` positionally.
        """
        await self._seed_two_typed_relationships(tasks_service, tasks_backend, ku_backend)

        result = await tasks_backend.get_relationships(
            "task:rel_filter_source", RelationshipName.REQUIRES_KNOWLEDGE, "outgoing"
        )
        assert result.is_ok
        assert [r["type"] for r in result.value] == ["REQUIRES_KNOWLEDGE"]

    # ==========================================================================
    # list() returns (page, total_count) tuple
    # ==========================================================================

    async def test_list_returns_page_and_total_count(self, tasks_service, tasks_backend):
        """backend.list() returns Result[tuple[list[T], int]] with an accurate total."""
        for i in range(5):
            task = Task(
                uid=f"task:list_count_{i}",
                title=f"List Count Task {i}",
                description="seed",
                user_uid="user_test",
                status=EntityStatus.ACTIVE,
            )
            assert (await tasks_service.create(task)).is_ok

        result = await tasks_backend.list(limit=2)
        assert result.is_ok

        value = result.value
        assert isinstance(value, tuple) and len(value) == 2
        page, total = value
        assert isinstance(page, list)
        # The page honours the limit; the total counts every matching row.
        assert len(page) == 2
        assert total == 5
