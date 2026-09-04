"""Choice creation: the request's knowledge links become ADMITTED graph edges
============================================================================

``ChoiceCreateRequest.informed_by_knowledge_uids`` is a list of UIDs the caller chose.
``ChoicesCoreService.create_choice`` turns it into ``(choice)-[:INFORMED_BY_KNOWLEDGE]->``
edges through the same shape every other Activity Domain's create door uses:

- ``_write_link_edges`` admits each uid through ``keep_permitted_link_edges`` — it
  EXISTS, its OWNER is the creator or nobody (a Ku is owned by nobody), and its KIND is a
  Ku (``KNOWLEDGE_LABELS``: the atom, so the substance fan-out and the context reader
  agree) — then batch-writes the kept subset and returns the uids it WROTE;
- ``_publish_knowledge_substance`` announces ``KnowledgeInformedChoice`` /
  ``KnowledgeBulkInformedChoice`` from that WRITTEN list, never from the request;
- the choice is announced (``ChoiceCreated`` + the embedding request) only after the
  edges exist, and the substance events follow the announcement.

Why the admission matters for this door specifically: the registry's Choice spec for
INFORMED_BY_KNOWLEDGE names its target ``Entity``, so the batch writer's own kind check
admits any entity — and the batch is all-or-nothing, so one dangling uid refuses every
valid link in the same request as a logged warning on a create that reports success.
The write site is the only place that knows the list means Kus.

No Neo4j: the backend is stubbed and mirrors the real writer's contract (a dangling
endpoint fails the whole batch), so what is under test is the service wiring. The
real-graph half is ``tests/integration/test_choice_knowledge_edge_roundtrip.py``.
"""

from dataclasses import fields
from typing import Any

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.events.choice_events import ChoiceCreated
from core.events.embedding_events import ChoiceEmbeddingRequested
from core.events.knowledge_substance_events import (
    KnowledgeBulkInformedChoice,
    KnowledgeInformedChoice,
)
from core.models.choice.choice import Choice
from core.models.choice.choice_option import ChoiceOption
from core.models.choice.choice_request import ChoiceCreateRequest, ChoiceOptionRequest
from core.models.enums import Domain, Priority
from core.models.enums.choice_enums import ChoiceType
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import CHOICES_CONFIG
from core.services.choices.choices_core_service import ChoicesCoreService
from core.services.choices_service import ChoicesService
from core.utils.result_simplified import Errors, Result

USER_UID = "user:choice-edges"
OTHER_USER = "user:someone-else"
KU_VALID = "ku.decisions.opportunity-cost"
KU_TWO = "ku.decisions.expected-value"
KU_DANGLING = "ku.decisions.gone"
TASK_UID = "task:compare-vendors"
PATH_STEP_UID = "ps.decisions.intro"
INFORMED_BY = RelationshipName.INFORMED_BY_KNOWLEDGE.value


# ============================================================================
# STUBS
# ============================================================================


class StubBackend:
    """Round-trips create() like the real backend and records every side effect.

    Mirrors ``UniversalNeo4jBackend._create_node`` (serialize with ``to_neo4j_node``,
    return the round-tripped DOMAIN ENTITY) and the real ``create_relationships_batch``
    contract: it validates every endpoint before writing any, so a uid that resolves to
    no node fails the WHOLE batch. That failure mode is what the admission guard exists
    to pre-empt, so the stub must reproduce it or the guard's absence reads as a pass.

    ``trace`` is an ORDERED log of side effects, so the tests can assert SEQUENCE.
    ``owner_lookups`` / ``label_lookups`` record what the guard asked about, so a test
    can prove the owner map was consulted even where no owner exists to refuse.

    ``__getattr__`` fails CLOSED: any backend call this stub does not model is an
    assertion failure, not a silent mock.
    """

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.trace: list[str] = []
        # (from_uid, to_uid, rel_type, properties) tuples, as handed to the backend
        self.batched: list[tuple[str, str, str, dict[str, Any] | None]] = []
        # uid -> owning user. A uid ABSENT here is owned by nobody — the real query
        # omits such rows, which is how a Ku (no user_uid, no owner_uid, no OWNS edge)
        # presents. Mapping a uid to a user stages an owned node.
        self.owners: dict[str, str] = {}
        # uid -> Neo4j labels; absent uids default to a Ku. ``missing`` stages a uid
        # that resolves to NO node.
        self.labels: dict[str, list[str]] = {}
        self.missing: set[str] = set()
        self.batch_fails: bool = False
        self.owner_lookups: list[list[str]] = []
        self.label_lookups: list[list[str]] = []

    async def create(self, entity: Any) -> Result[Choice]:
        props = to_neo4j_node(entity)
        self.created.append(dict(props))
        self.trace.append("node_created")
        return Result.ok(from_neo4j_node(props, Choice))

    async def create_relationships_batch(self, relationships: Any) -> Result[int]:
        edges = list(relationships)
        dangling = [to_uid for _from, to_uid, _rel, _props in edges if to_uid in self.missing]
        if self.batch_fails or dangling:
            self.trace.append("edge_batch_failed")
            return Result.fail(
                Errors.database(
                    operation="create",
                    message=f"Node(s) not found: {', '.join(dangling) or 'batch exploded'}",
                )
            )
        self.batched.extend(edges)
        self.trace.append("link_edges_written")
        return Result.ok(len(edges))

    async def get_owner_uids_batch(self, uids: Any) -> Result[dict[str, list[str]]]:
        asked = list(uids)
        self.owner_lookups.append(asked)
        return Result.ok({uid: [self.owners[uid]] for uid in asked if uid in self.owners})

    async def get_node_labels_batch(self, uids: Any) -> Result[dict[str, list[str]]]:
        asked = list(uids)
        self.label_lookups.append(asked)
        return Result.ok(
            {
                uid: self.labels.get(uid, ["Entity", "Ku"])
                for uid in asked
                if uid not in self.missing
            }
        )

    def __getattr__(self, name: str):
        async def _unexpected(*args: Any, **kwargs: Any):
            raise AssertionError(f"backend.{name}() unexpectedly called")

        return _unexpected


class _Inert:
    """Collaborator stub for facade construction — never exercised by create."""

    def __getattr__(self, name: str) -> "_Inert":
        return self

    def __call__(self, *args: Any, **kwargs: Any) -> "_Inert":
        return self


def record_publishes(bus: InMemoryEventBus, backend: StubBackend) -> None:
    """Interleave the announcement and the substance events into the backend's trace
    so ordering across the two halves — edge writes and publishes — is observable."""

    def _created(event: ChoiceCreated) -> None:
        backend.trace.append("choice_created_published")

    def _substance(event: KnowledgeInformedChoice | KnowledgeBulkInformedChoice) -> None:
        backend.trace.append("substance_published")

    bus.subscribe(ChoiceCreated, _created)
    bus.subscribe(KnowledgeInformedChoice, _substance)
    bus.subscribe(KnowledgeBulkInformedChoice, _substance)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus(capture_history=True)


@pytest.fixture
def backend() -> StubBackend:
    return StubBackend()


@pytest.fixture
def core(backend: StubBackend, event_bus: InMemoryEventBus) -> ChoicesCoreService:
    """The request door — ``create_choice`` — lives here."""
    return ChoicesCoreService(backend=backend, event_bus=event_bus)


@pytest.fixture
def facade(backend: StubBackend, event_bus: InMemoryEventBus) -> ChoicesService:
    """What ``services.choices`` is bound to: ``create_choice`` delegates to the core
    door; ``create(entity)`` is the entity door for in-process callers."""
    return ChoicesService(
        backend=backend,
        graph_intel=_Inert(),
        cross_domain_query=_Inert(),
        event_bus=event_bus,
    )


def make_request(**overrides: Any) -> ChoiceCreateRequest:
    defaults: dict[str, Any] = {
        "title": "Pick a primary datastore",
        "description": "Choose between the two candidate stores for the platform",
        "choice_type": ChoiceType.MULTIPLE,
        "domain": Domain.TECH,
        "priority": Priority.HIGH,
        "options": [
            ChoiceOptionRequest(title="Neo4j", description="graph"),
            ChoiceOptionRequest(title="Postgres", description="relational"),
        ],
    }
    defaults.update(overrides)
    return ChoiceCreateRequest(**defaults)


def make_choice() -> Choice:
    """A Choice entity shaped like the one the entity door's converter produces."""
    return Choice(
        uid="choice:entity-door",
        user_uid=USER_UID,
        title="Pick a primary datastore",
        description="Choose between the two candidate stores for the platform",
        choice_type=ChoiceType.MULTIPLE,
        options=(
            ChoiceOption(uid="option:neo4j", title="Neo4j", description="graph"),
            ChoiceOption(uid="option:postgres", title="Postgres", description="relational"),
        ),
    )


def substance_events(
    event_bus: InMemoryEventBus,
) -> list[KnowledgeInformedChoice | KnowledgeBulkInformedChoice]:
    return [
        e
        for e in event_bus.get_event_history()
        if isinstance(e, KnowledgeInformedChoice | KnowledgeBulkInformedChoice)
    ]


# ============================================================================
# THE DOOR — admitted uids become edges, and only those
# ============================================================================


@pytest.mark.asyncio
class TestOnlyAdmittedLinksAreWritten:
    async def test_one_valid_ku_writes_one_edge(
        self, core: ChoicesCoreService, backend: StubBackend
    ) -> None:
        result = await core.create_choice(
            make_request(informed_by_knowledge_uids=[KU_VALID]), USER_UID
        )

        assert result.is_ok, f"create_choice failed: {result.error}"
        assert backend.batched == [(result.value.uid, KU_VALID, INFORMED_BY, None)]

    async def test_a_mixed_list_writes_exactly_the_ku(
        self, core: ChoicesCoreService, backend: StubBackend
    ) -> None:
        """THE defect: without admission the whole list reaches the all-or-nothing
        batch, the dangling uid fails it, and the valid Ku loses its edge silently."""
        backend.missing.add(KU_DANGLING)
        backend.labels[TASK_UID] = ["Entity", "Task"]

        result = await core.create_choice(
            make_request(informed_by_knowledge_uids=[KU_VALID, KU_DANGLING, TASK_UID]),
            USER_UID,
        )

        assert result.is_ok, f"create_choice failed: {result.error}"
        assert backend.batched == [(result.value.uid, KU_VALID, INFORMED_BY, None)], (
            f"expected exactly the Ku edge, got {backend.batched}; trace {backend.trace}"
        )

    async def test_a_choice_without_knowledge_touches_no_edge_machinery(
        self, core: ChoicesCoreService, backend: StubBackend
    ) -> None:
        result = await core.create_choice(make_request(), USER_UID)

        assert result.is_ok
        assert backend.batched == []
        assert backend.owner_lookups == [] and backend.label_lookups == []

    async def test_the_edge_agrees_with_the_registry(
        self, core: ChoicesCoreService, backend: StubBackend
    ) -> None:
        """Direction comes from CHOICES_CONFIG, not a hand-copied table: a rename or a
        direction flip on the READ side must break this test rather than silently
        orphan the write. The spec's target label being ``Entity`` is also exactly why
        the KIND check cannot be delegated to the registry."""
        spec = CHOICES_CONFIG.get_relationship_by_method("knowledge")
        assert spec is not None, "CHOICES_CONFIG has no 'knowledge' relationship"
        assert spec.relationship == RelationshipName.INFORMED_BY_KNOWLEDGE
        assert spec.direction == "outgoing", (
            "the create path writes the choice as the edge SOURCE; a non-outgoing spec "
            "means the write and the read now point opposite ways"
        )
        assert spec.target_label == "Entity", (
            "the registry now declares a specific target label for this edge — "
            "revisit whether the guard's kind check is still the only one"
        )

        result = await core.create_choice(
            make_request(informed_by_knowledge_uids=[KU_VALID]), USER_UID
        )
        assert backend.batched and backend.batched[0][0] == result.value.uid, (
            "the choice must be the edge SOURCE"
        )


# ============================================================================
# ADMISSION — exists / owner / kind
# ============================================================================


@pytest.mark.asyncio
class TestLinkAdmission:
    """Every refusal below still creates the choice — only its edges are refused."""

    async def test_a_dangling_uid_does_not_lose_the_valid_link(
        self, core: ChoicesCoreService, backend: StubBackend
    ) -> None:
        backend.missing.add(KU_DANGLING)

        result = await core.create_choice(
            make_request(informed_by_knowledge_uids=[KU_DANGLING, KU_VALID]), USER_UID
        )

        assert result.is_ok
        assert backend.batched == [(result.value.uid, KU_VALID, INFORMED_BY, None)]
        assert "edge_batch_failed" not in backend.trace, (
            "the dangling uid reached the all-or-nothing batch"
        )

    async def test_refuses_a_uid_that_is_not_knowledge(
        self, core: ChoicesCoreService, backend: StubBackend
    ) -> None:
        """The field name declares the kind; the registry's ``Entity`` target cannot."""
        backend.labels[TASK_UID] = ["Entity", "Task"]

        result = await core.create_choice(
            make_request(informed_by_knowledge_uids=[TASK_UID]), USER_UID
        )

        assert result.is_ok, "the choice itself is the caller's own and must be created"
        assert backend.batched == [], "a Task was linked as the choice's informing knowledge"

    async def test_refuses_a_path_step(
        self, core: ChoicesCoreService, backend: StubBackend
    ) -> None:
        """KNOWLEDGE_LABELS is the atom only: substance fans out FROM a Ku to the
        PathSteps composing it and has no inverse, so a PathStep link would credit the
        PathStep and none of the atoms it teaches."""
        backend.labels[PATH_STEP_UID] = ["Entity", "PathStep"]

        result = await core.create_choice(
            make_request(informed_by_knowledge_uids=[PATH_STEP_UID]), USER_UID
        )

        assert result.is_ok
        assert backend.batched == []

    async def test_the_owner_map_is_consulted_and_an_unowned_ku_is_kept(
        self, core: ChoicesCoreService, backend: StubBackend
    ) -> None:
        """A Ku carries no owner, so a cross-user Ku cannot occur — but the guard's
        contract is one pair of batched reads for EVERY link list, and "owned by nobody"
        is an admission verdict it reaches by reading, not by assuming."""
        result = await core.create_choice(
            make_request(informed_by_knowledge_uids=[KU_VALID, KU_TWO]), USER_UID
        )

        assert result.is_ok
        assert backend.owner_lookups == [sorted([KU_VALID, KU_TWO])]
        assert backend.label_lookups == [sorted([KU_VALID, KU_TWO])]
        assert [edge[1] for edge in backend.batched] == [KU_VALID, KU_TWO]

    async def test_a_ku_staged_under_another_owner_is_refused(
        self, core: ChoicesCoreService, backend: StubBackend
    ) -> None:
        """The guard does not know that Kus are unowned; if one ever carried another
        user's ownership, the link is refused — fail closed, per the guard's contract."""
        backend.owners[KU_VALID] = OTHER_USER

        result = await core.create_choice(
            make_request(informed_by_knowledge_uids=[KU_VALID]), USER_UID
        )

        assert result.is_ok
        assert backend.batched == []

    async def test_edge_failure_does_not_fail_the_create(
        self, core: ChoicesCoreService, backend: StubBackend
    ) -> None:
        """Doors agree on log-and-continue: a refused or failed link never kills the
        entity it decorates."""
        backend.batch_fails = True

        result = await core.create_choice(
            make_request(informed_by_knowledge_uids=[KU_VALID]), USER_UID
        )

        assert result.is_ok
        assert "edge_batch_failed" in backend.trace


# ============================================================================
# KNOWLEDGE SUBSTANCE — announced from the uids WRITTEN, never those requested
# ============================================================================


@pytest.mark.asyncio
class TestKnowledgeSubstanceFollowsTheEdges:
    async def test_single_link_publishes_the_single_event(
        self, core: ChoicesCoreService, event_bus: InMemoryEventBus
    ) -> None:
        result = await core.create_choice(
            make_request(informed_by_knowledge_uids=[KU_VALID]), USER_UID
        )

        published = substance_events(event_bus)
        assert len(published) == 1
        assert isinstance(published[0], KnowledgeInformedChoice)
        assert published[0].knowledge_uid == KU_VALID
        assert published[0].choice_uid == result.value.uid
        assert published[0].user_uid == USER_UID

    async def test_multiple_links_publish_the_bulk_event(
        self, core: ChoicesCoreService, event_bus: InMemoryEventBus
    ) -> None:
        await core.create_choice(
            make_request(informed_by_knowledge_uids=[KU_VALID, KU_TWO]), USER_UID
        )

        published = substance_events(event_bus)
        assert len(published) == 1
        assert isinstance(published[0], KnowledgeBulkInformedChoice)
        assert published[0].knowledge_uids == (KU_VALID, KU_TWO)

    async def test_a_mixed_list_credits_only_the_ku(
        self, core: ChoicesCoreService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        """Substance for a dangling uid or a Task would claim knowledge informed the
        choice when no INFORMED_BY_KNOWLEDGE edge exists."""
        backend.missing.add(KU_DANGLING)
        backend.labels[TASK_UID] = ["Entity", "Task"]

        await core.create_choice(
            make_request(informed_by_knowledge_uids=[KU_VALID, KU_DANGLING, TASK_UID]),
            USER_UID,
        )

        published = substance_events(event_bus)
        assert len(published) == 1, f"expected one substance event, got {published}"
        assert isinstance(published[0], KnowledgeInformedChoice), (
            "substance was announced for uids that never became edges"
        )
        assert published[0].knowledge_uid == KU_VALID

    async def test_a_refused_link_announces_no_substance(
        self, core: ChoicesCoreService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        backend.missing.add(KU_DANGLING)

        await core.create_choice(make_request(informed_by_knowledge_uids=[KU_DANGLING]), USER_UID)

        assert substance_events(event_bus) == []

    async def test_a_failed_batch_announces_no_substance(
        self, core: ChoicesCoreService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        backend.batch_fails = True

        await core.create_choice(make_request(informed_by_knowledge_uids=[KU_VALID]), USER_UID)

        assert substance_events(event_bus) == []

    async def test_a_repeated_uid_is_counted_once(
        self, core: ChoicesCoreService, event_bus: InMemoryEventBus
    ) -> None:
        """The batch MERGEs (one edge) but the bulk event UNWINDs (one credit per row)."""
        await core.create_choice(
            make_request(informed_by_knowledge_uids=[KU_VALID, KU_VALID]), USER_UID
        )

        published = substance_events(event_bus)
        assert len(published) == 1
        assert isinstance(published[0], KnowledgeInformedChoice), (
            "a repeated uid announced substance twice"
        )
        assert published[0].knowledge_uid == KU_VALID


# ============================================================================
# ORDERING — edges, then the announcement, then substance
# ============================================================================


@pytest.mark.asyncio
class TestEdgesPrecedeTheAnnouncement:
    """``ChoiceCreated`` triggers the user-context rebuild, which reads the
    INFORMED_BY_KNOWLEDGE edges back out of the graph and caches what it finds."""

    async def test_the_request_door_writes_edges_first(
        self, core: ChoicesCoreService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        record_publishes(event_bus, backend)

        await core.create_choice(make_request(informed_by_knowledge_uids=[KU_VALID]), USER_UID)

        assert backend.trace == [
            "node_created",
            "link_edges_written",
            "choice_created_published",
            "substance_published",
        ]

    async def test_a_linkless_choice_still_announces(
        self, core: ChoicesCoreService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        record_publishes(event_bus, backend)

        await core.create_choice(make_request(), USER_UID)

        assert backend.trace == ["node_created", "choice_created_published"]

    async def test_exactly_one_announcement_and_one_embedding_request(
        self, core: ChoicesCoreService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        backend.missing.add(KU_DANGLING)

        await core.create_choice(
            make_request(informed_by_knowledge_uids=[KU_VALID, KU_DANGLING]), USER_UID
        )

        history = event_bus.get_event_history()
        assert len([e for e in history if isinstance(e, ChoiceCreated)]) == 1
        assert len([e for e in history if isinstance(e, ChoiceEmbeddingRequested)]) == 1


# ============================================================================
# THE TWO DOORS
# ============================================================================


@pytest.mark.asyncio
class TestTheFacadeAndTheEntityDoor:
    async def test_facade_create_choice_rides_the_guarded_door(
        self, facade: ChoicesService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        backend.missing.add(KU_DANGLING)
        backend.labels[TASK_UID] = ["Entity", "Task"]

        result = await facade.create_choice(
            make_request(informed_by_knowledge_uids=[KU_VALID, KU_DANGLING, TASK_UID]),
            USER_UID,
        )

        assert result.is_ok, f"create_choice failed: {result.error}"
        assert backend.batched == [(result.value.uid, KU_VALID, INFORMED_BY, None)]
        published = substance_events(event_bus)
        assert len(published) == 1 and isinstance(published[0], KnowledgeInformedChoice)
        assert published[0].knowledge_uid == KU_VALID

    async def test_the_entity_door_writes_no_knowledge_edges(
        self, facade: ChoicesService, backend: StubBackend, event_bus: InMemoryEventBus
    ) -> None:
        result = await facade.create(make_choice())

        assert result.is_ok, f"create failed: {result.error}"
        assert backend.batched == []
        assert backend.owner_lookups == []
        assert substance_events(event_bus) == []
        assert [e for e in event_bus.get_event_history() if isinstance(e, ChoiceCreated)], (
            "the entity door stopped announcing the choice"
        )


class TestTheEntityCarriesNoList:
    def test_the_entity_cannot_carry_the_list(self) -> None:
        """``informed_by_knowledge_uids`` is a request field, not a ``Choice`` field —
        a link the entity cannot carry is a link the entity door can never write."""
        assert "informed_by_knowledge_uids" not in {f.name for f in fields(Choice)}
