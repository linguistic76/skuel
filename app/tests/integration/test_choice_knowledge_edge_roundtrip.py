"""Real-Neo4j round-trip test for ``ChoicesCoreService.create_choice``.

This guards a class of bug that a mocked unit test structurally cannot catch:
``create_choice`` previously created its knowledge edges by calling
``self.relationship_service.create_choice_relationships(...)``. That method does
not exist on any relationship service, *and* ``relationship_service`` was never
injected into ``ChoicesCoreService`` (the factory builds the core service with
``backend`` + ``event_bus`` only). So the branch was doubly dead — guarded by a
``None`` it could never escape, calling a method that was never defined. A choice
created with ``informed_by_knowledge_uids`` silently dropped every knowledge edge,
even though the ``KnowledgeInformedChoice`` substance event still fired.

The fix routes the edge through ``backend.create_relationships_batch`` (the same
proven path Tasks use for ``APPLIES_KNOWLEDGE``) with an explicit
``RelationshipName.INFORMED_BY_KNOWLEDGE`` value. The only way to prove that
round-trips is to create the edge against a real Neo4j and read it back — which
is exactly what this test does. Against the broken code no edge was ever created;
against the fix it persists.

Reader on the other side: ``PsService.find_choices_informed_by_knowledge``.
"""

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.choice.choice import Choice
from core.models.choice.choice_request import ChoiceCreateRequest
from core.models.enums import Domain, Priority
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.services.choices.choices_core_service import ChoicesCoreService


@pytest.mark.asyncio
class TestChoiceKnowledgeEdgeRoundTrip:
    """End-to-end (real Neo4j) coverage for the INFORMED_BY_KNOWLEDGE edge."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def choices_backend(self, neo4j_driver, clean_neo4j):
        # Multi-label (:Choice:Entity) to match production — the relationship
        # registry keys INFORMED_BY_KNOWLEDGE validation off the :Choice label.
        return UniversalNeo4jBackend[Choice](
            neo4j_driver, NeoLabel.CHOICE, Choice, base_label=NeoLabel.ENTITY
        )

    @pytest_asyncio.fixture
    async def choices_service(self, choices_backend, event_bus):
        return ChoicesCoreService(backend=choices_backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def test_user_uid(self, neo4j_driver, clean_neo4j):
        uid = "user_test_choice_knowledge"
        async with neo4j_driver.session() as session:
            await session.run(
                "MERGE (u:User {uid: $uid}) ON CREATE SET u.created_at = datetime()",
                uid=uid,
            )
        return uid

    async def _create_ku(self, neo4j_driver, uid: str, title: str) -> None:
        """Persist a minimal :Entity:Ku node so the edge target validates."""
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (k:Entity:Ku {uid: $uid})
                ON CREATE SET k.entity_type = 'ku', k.title = $title
                RETURN k
                """,
                uid=uid,
                title=title,
            )

    async def test_create_choice_persists_informed_by_knowledge_edges(
        self, choices_service, neo4j_driver, test_user_uid
    ):
        """create_choice writes real ``(Choice)-[:INFORMED_BY_KNOWLEDGE]->(Ku)`` edges."""
        await self._create_ku(neo4j_driver, "ku_decision_theory_abc", "Decision Theory")
        await self._create_ku(neo4j_driver, "ku_opportunity_cost_def", "Opportunity Cost")

        request = ChoiceCreateRequest(
            title="Pick a database",
            description="Choose the primary datastore for the new service",
            domain=Domain.TECH,
            priority=Priority.HIGH,
            informed_by_knowledge_uids=["ku_decision_theory_abc", "ku_opportunity_cost_def"],
        )

        # ACT: the path that previously called the non-existent relationship method.
        result = await choices_service.create_choice(request, test_user_uid)
        assert result.is_ok, f"create_choice failed: {result}"
        choice = result.value

        # ASSERT: both knowledge edges round-trip out of real Neo4j.
        edges = await choices_service.backend.get_relationships(
            choice.uid,
            rel_type=RelationshipName.INFORMED_BY_KNOWLEDGE,
            direction="outgoing",
        )
        assert edges.is_ok
        target_uids = sorted(r["target_uid"] for r in edges.value)
        assert target_uids == ["ku_decision_theory_abc", "ku_opportunity_cost_def"]
        assert {r["type"] for r in edges.value} == {"INFORMED_BY_KNOWLEDGE"}

    async def test_create_choice_admits_only_existing_kus(
        self, choices_service, neo4j_driver, test_user_uid, event_bus
    ):
        """A dangling uid and a non-Ku are refused; the valid Ku still lands.

        The real batch writer is all-or-nothing, so without admission the dangling uid
        would refuse the whole batch and the valid link would vanish on a create that
        reports success. Substance is credited for the edge written, not the request.
        """
        from core.events.knowledge_substance_events import (
            KnowledgeBulkInformedChoice,
            KnowledgeInformedChoice,
        )

        await self._create_ku(neo4j_driver, "ku_decision_theory_abc", "Decision Theory")
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (t:Entity:Task {uid: $uid})
                ON CREATE SET t.entity_type = 'task', t.title = 'Compare vendors',
                              t.user_uid = $user_uid
                """,
                uid="task_compare_vendors_xyz",
                user_uid=test_user_uid,
            )

        request = ChoiceCreateRequest(
            title="Pick a database",
            description="Choose the primary datastore for the new service",
            domain=Domain.TECH,
            priority=Priority.HIGH,
            informed_by_knowledge_uids=[
                "ku_decision_theory_abc",
                "ku_does_not_exist_000",
                "task_compare_vendors_xyz",
            ],
        )

        result = await choices_service.create_choice(request, test_user_uid)
        assert result.is_ok, f"create_choice failed: {result}"
        choice = result.value

        edges = await choices_service.backend.get_relationships(
            choice.uid,
            rel_type=RelationshipName.INFORMED_BY_KNOWLEDGE,
            direction="outgoing",
        )
        assert edges.is_ok
        assert [r["target_uid"] for r in edges.value] == ["ku_decision_theory_abc"]

        substance = [
            e
            for e in event_bus.get_event_history()
            if isinstance(e, KnowledgeInformedChoice | KnowledgeBulkInformedChoice)
        ]
        assert len(substance) == 1
        assert isinstance(substance[0], KnowledgeInformedChoice)
        assert substance[0].knowledge_uid == "ku_decision_theory_abc"

    async def test_create_choice_without_knowledge_creates_no_edges(
        self, choices_service, test_user_uid
    ):
        """A choice with no ``informed_by_knowledge_uids`` creates zero knowledge edges."""
        request = ChoiceCreateRequest(
            title="Pick a logo color",
            description="Decide the primary brand color",
            domain=Domain.PERSONAL,
        )

        result = await choices_service.create_choice(request, test_user_uid)
        assert result.is_ok, f"create_choice failed: {result}"
        choice = result.value

        edges = await choices_service.backend.get_relationships(
            choice.uid,
            rel_type=RelationshipName.INFORMED_BY_KNOWLEDGE,
            direction="outgoing",
        )
        assert edges.is_ok
        assert edges.value == []
