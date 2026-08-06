"""
Choice creation: the two doors must agree
==========================================

Choices have two create doors, and before this suite they disagreed on both the
data they carried and the rules they enforced:

  DOOR A — generated CRUD route (``CRUDRouteFactory._register_create_route``)
      POST /api/choices/create validates the body into ``ChoiceCreateRequest``,
      converts it via ``ConversionServiceV2.choice_create_to_pure`` (which DOES
      hand-convert nested options into ``ChoiceOption`` values), then calls
      ``service.create(entity)`` on the ``ChoicesService`` FACADE.

  DOOR B — service facade / UI form (``ChoicesService.create_choice``)
      POST /choices/create delegates to ``ChoicesCoreService.create_choice``,
      which built a DTO via ``ChoiceDTO.create_choice(...)`` and dropped every
      field it did not name explicitly — options among them.

Two independent defects met here:

  1. DOOR B dropped request fields. ``ChoiceDTO.create_choice`` takes ``**kwargs``,
     so the fields were droppable in silence: options, choice_type,
     decision_criteria, constraints, stakeholders and tags never reached the DTO.

  2. Neither door validated. ``ChoicesCoreService._validate_create`` states the
     domain's rules (>=2 options, BINARY needs exactly 2, STRATEGIC needs a 50+
     char description), but it is only ever invoked from
     ``CrudOperationsMixin.create()``. DOOR B bypassed that method entirely by
     calling ``_create_and_convert`` (which goes straight to ``backend.create``),
     and DOOR A reached the mixin but resolved ``_validate_create`` to the base
     no-op: the rules live on ``ChoicesCoreService``, which is a delegated
     ATTRIBUTE of the facade (``self.core``), never a base class of it. The
     override was therefore not in the facade's MRO.

The tests below pin the settled semantics:

  Options are OPTIONAL at creation. A supplied set must hold at least 2, and a
  BINARY choice that carries options must carry exactly 2. Both doors carry the
  options and reach the same verdict, via the one validated, event-firing path.

Optional rather than required because three live doors create optionless choices
on purpose — the UI create form (which omits the nested list entirely), DSL
activity ingestion (which infers BINARY from prose and supplies none), and
learning guidance. Options are added afterwards via ``add_option``, and the ">= 2"
floor is enforced from then on by ``remove_option`` / ``_validate_update``.
``TestLiveDoorsStillWork`` pins those payloads so a future tightening of the rule
breaks here rather than in the app.

The routing mirrors the update path, reconciled the same way earlier:
``ChoicesService.update`` overrides the inherited CRUD update so the core's
validation and events cannot be skipped.

No Neo4j: the backend is stubbed, so what is under test is the service wiring —
which is exactly where both defects lived.
"""

from typing import Any

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.events.choice_events import ChoiceCreated
from core.models.choice.choice import Choice
from core.models.choice.choice_option import ChoiceOption
from core.models.choice.choice_request import ChoiceCreateRequest, ChoiceOptionRequest
from core.models.enums import Domain, Priority
from core.models.enums.choice_enums import ChoiceType
from core.services.choices.choices_core_service import ChoicesCoreService
from core.services.choices_service import ChoicesService
from core.utils.result_simplified import Result

USER_UID = "user:parity"


# ============================================================================
# STUBS
# ============================================================================


class StubChoicesBackend:
    """Minimal ChoicesOperations stand-in that records what create() was handed.

    Mirrors the real backend's contract exactly: whatever it is handed (entity or
    dict) is serialized with ``to_neo4j_node`` — so nested options pass through
    the JSON string property they really are on disk — and the round-tripped
    DOMAIN ENTITY is returned, as ``_create_node`` does via ``from_neo4j_node``.
    Returning raw props instead would let an options-dropping bug read as a pass.
    """

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        # Ordered trace of side effects, so tests can assert *sequence*, not just
        # occurrence — the knowledge-edge/event ordering below is load-bearing.
        self.trace: list[str] = []

    async def create(self, entity: Any) -> Result[Choice]:
        props = to_neo4j_node(entity)
        self.created.append(dict(props))
        self.trace.append("node_created")
        return Result.ok(from_neo4j_node(props, Choice))

    async def create_relationships_batch(self, relationships: Any) -> Result[bool]:
        self.trace.append("knowledge_edges_written")
        return Result.ok(True)

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


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus(capture_history=True)


@pytest.fixture
def backend() -> StubChoicesBackend:
    return StubChoicesBackend()


@pytest.fixture
def core(backend: StubChoicesBackend, event_bus: InMemoryEventBus) -> ChoicesCoreService:
    """DOOR B's service — ChoicesCoreService.create_choice."""
    return ChoicesCoreService(backend=backend, event_bus=event_bus)


@pytest.fixture
def facade(backend: StubChoicesBackend, event_bus: InMemoryEventBus) -> ChoicesService:
    """DOOR A's service — the object CRUDRouteFactory calls ``.create(entity)`` on.

    ``services.choices`` is bound to the ChoicesService FACADE in
    services_bootstrap/_activity_services.py, so the facade — not the core
    sub-service — is what the generated route reaches.
    """
    return ChoicesService(
        backend=backend,
        graph_intel=_Inert(),
        cross_domain_query=_Inert(),
        event_bus=event_bus,
    )


def make_request(**overrides: Any) -> ChoiceCreateRequest:
    """A valid two-option create request; override to build invalid variants."""
    defaults: dict[str, Any] = {
        "title": "Pick a primary datastore",
        "description": "Choose between the two candidate stores for the platform",
        "choice_type": ChoiceType.MULTIPLE,
        "domain": Domain.TECH,
        "priority": Priority.HIGH,
        "decision_criteria": ["cost", "latency"],
        "constraints": ["must be open source"],
        "stakeholders": ["platform team"],
        "tags": ["infra", "adr"],
        "options": [
            ChoiceOptionRequest(title="Neo4j", description="graph"),
            ChoiceOptionRequest(title="Postgres", description="relational"),
        ],
    }
    defaults.update(overrides)
    return ChoiceCreateRequest(**defaults)


def option(title: str) -> ChoiceOption:
    return ChoiceOption(uid=f"option:{title.lower()}", title=title, description=title)


def make_choice(**overrides: Any) -> Choice:
    """A Choice entity shaped like the one DOOR A's converter produces."""
    defaults: dict[str, Any] = {
        "uid": "choice:door-a",
        "user_uid": USER_UID,
        "title": "Pick a primary datastore",
        "description": "Choose between the two candidate stores for the platform",
        "choice_type": ChoiceType.MULTIPLE,
        "options": (option("Neo4j"), option("Postgres")),
    }
    defaults.update(overrides)
    return Choice(**defaults)


# ============================================================================
# DOOR B — the facade/UI door must carry the request's payload
# ============================================================================


@pytest.mark.asyncio
class TestDoorBCarriesRequestFields:
    """``create_choice`` must not silently drop what the request supplied."""

    async def test_options_are_carried(self, core: ChoicesCoreService) -> None:
        """RED before the fix: create_choice never passed choice_request.options."""
        result = await core.create_choice(make_request(), USER_UID)

        assert result.is_ok, f"create_choice failed: {result.error}"
        assert len(result.value.options) == 2, (
            "DOOR B dropped the request's options — ChoiceDTO.create_choice was "
            "called without choice_request.options"
        )
        assert [o.title for o in result.value.options] == ["Neo4j", "Postgres"]

    async def test_options_reach_the_backend_not_just_the_return_value(
        self, core: ChoicesCoreService, backend: StubChoicesBackend
    ) -> None:
        """Persisted, not merely echoed: assert on what the backend was handed.

        A fix that populated only the returned model would pass the test above
        while still writing an optionless node.
        """
        await core.create_choice(make_request(), USER_UID)

        assert backend.created, "backend.create() was never called"
        props = backend.created[0]
        assert "Neo4j" in str(props.get("options")), (
            f"options absent from the persisted properties: {props.get('options')!r}"
        )

    async def test_choice_type_is_carried(self, core: ChoicesCoreService) -> None:
        """RED before the fix: choice_type was dropped, persisting as None."""
        request = make_request(
            choice_type=ChoiceType.BINARY,
            options=[
                ChoiceOptionRequest(title="Neo4j", description="graph"),
                ChoiceOptionRequest(title="Postgres", description="relational"),
            ],
        )
        result = await core.create_choice(request, USER_UID)

        assert result.is_ok, f"create_choice failed: {result.error}"
        assert result.value.choice_type == ChoiceType.BINARY

    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ("decision_criteria", ("cost", "latency")),
            ("constraints", ("must be open source",)),
            ("stakeholders", ("platform team",)),
            ("tags", ("infra", "adr")),
        ],
    )
    async def test_list_fields_are_carried(
        self, core: ChoicesCoreService, field: str, expected: tuple[str, ...]
    ) -> None:
        """RED before the fix: four more request fields were dropped alongside options."""
        result = await core.create_choice(make_request(), USER_UID)

        assert result.is_ok, f"create_choice failed: {result.error}"
        assert tuple(getattr(result.value, field)) == expected


@pytest.mark.asyncio
class TestDoorBValidates:
    """``create_choice`` must run the domain's own creation rules."""

    async def test_rejects_fewer_than_two_options(self, core: ChoicesCoreService) -> None:
        """RED before the fix: _create_and_convert bypassed CrudOperationsMixin.create()."""
        request = make_request(options=[ChoiceOptionRequest(title="Only one")])

        result = await core.create_choice(request, USER_UID)

        assert result.is_error, "a one-option choice was created despite the >=2 rule"
        assert "at least 2" in str(result.error)

    async def test_allows_no_options(self, core: ChoicesCoreService) -> None:
        """Options are OPTIONAL at creation — a draft gathers them via add_option.

        This is not a gap in the rule, it is the rule: the UI create form omits the
        nested options list entirely and DSL ingestion supplies none, so rejecting
        an optionless create would break both doors.
        """
        result = await core.create_choice(make_request(options=[]), USER_UID)

        assert result.is_ok, f"an optionless draft choice was rejected: {result.error}"
        assert result.value.options == ()

    async def test_allows_binary_with_no_options(self, core: ChoicesCoreService) -> None:
        """DSL ingestion infers BINARY from prose keywords and supplies no options."""
        result = await core.create_choice(
            make_request(choice_type=ChoiceType.BINARY, options=[]), USER_UID
        )

        assert result.is_ok, f"an optionless BINARY draft was rejected: {result.error}"

    async def test_rejects_binary_with_three_options(self, core: ChoicesCoreService) -> None:
        request = make_request(
            choice_type=ChoiceType.BINARY,
            options=[
                ChoiceOptionRequest(title="A"),
                ChoiceOptionRequest(title="B"),
                ChoiceOptionRequest(title="C"),
            ],
        )

        result = await core.create_choice(request, USER_UID)

        assert result.is_error, "a 3-option BINARY choice was created"
        assert "exactly 2 options" in str(result.error)

    async def test_a_rejected_create_writes_nothing(
        self, core: ChoicesCoreService, backend: StubChoicesBackend
    ) -> None:
        """Validation must precede persistence, not merely report after it."""
        await core.create_choice(
            make_request(options=[ChoiceOptionRequest(title="Only one")]), USER_UID
        )

        assert backend.created == [], "a rejected create still wrote to the backend"


# ============================================================================
# DOOR A — the generated CRUD route must reach the same rules
# ============================================================================


@pytest.mark.asyncio
class TestDoorAValidates:
    """``ChoicesService.create(entity)`` is what CRUDRouteFactory calls."""

    async def test_rejects_fewer_than_two_options(self, facade: ChoicesService) -> None:
        """RED before the fix: the facade resolved _validate_create to the base no-op."""
        result = await facade.create(make_choice(options=(option("Only one"),)))

        assert result.is_error, (
            "DOOR A created a one-option choice — ChoicesCoreService._validate_create "
            "is not in the facade's MRO, so the base no-op ran"
        )
        assert "at least 2" in str(result.error)

    async def test_allows_no_options(self, facade: ChoicesService) -> None:
        """Both doors agree that an optionless draft is legal."""
        result = await facade.create(make_choice(options=()))

        assert result.is_ok, f"DOOR A rejected an optionless draft choice: {result.error}"

    async def test_rejects_binary_with_three_options(self, facade: ChoicesService) -> None:
        result = await facade.create(
            make_choice(
                choice_type=ChoiceType.BINARY,
                options=(option("A"), option("B"), option("C")),
            )
        )

        assert result.is_error, "DOOR A created a 3-option BINARY choice"
        assert "exactly 2 options" in str(result.error)

    async def test_a_rejected_create_writes_nothing(
        self, facade: ChoicesService, backend: StubChoicesBackend
    ) -> None:
        await facade.create(make_choice(options=(option("Only one"),)))

        assert backend.created == [], "DOOR A wrote a choice that failed validation"

    async def test_valid_choice_still_passes(self, facade: ChoicesService) -> None:
        """Positive control: the guard must not reject what it should admit.

        Without this, every assertion above would also pass against a create
        that rejects unconditionally.
        """
        result = await facade.create(make_choice())

        assert result.is_ok, f"a valid two-option choice was rejected: {result.error}"
        assert len(result.value.options) == 2

    async def test_entity_without_domain_still_creates(self, facade: ChoicesService) -> None:
        """``Choice.domain`` is nullable, and this door accepts hand-built entities.

        Building the ChoiceCreated payload with a bare ``choice.domain.value`` raises
        AttributeError here. It never bit before because the event was only published
        from the request door, where ChoiceCreateRequest.domain always defaults.
        """
        result = await facade.create(make_choice(domain=None))

        assert result.is_ok, f"a domainless choice crashed or was rejected: {result.error}"

    async def test_publishes_choice_created(
        self, facade: ChoicesService, event_bus: InMemoryEventBus
    ) -> None:
        """RED before the fix: DOOR A published no event at all.

        DOOR B fired ChoiceCreated from create_choice; the generated route went
        straight through the mixin, so an API-created choice invalidated no
        context and requested no embedding.
        """
        await facade.create(make_choice())

        created = [e for e in event_bus.get_event_history() if isinstance(e, ChoiceCreated)]
        assert created, "DOOR A published no ChoiceCreated event"
        assert created[0].choice_uid == "choice:door-a"

    async def test_publishes_exactly_one_event_per_create(
        self, core: ChoicesCoreService, event_bus: InMemoryEventBus
    ) -> None:
        """Guards the fix's own failure mode: routing DOOR B through the shared
        create primitive must not publish ChoiceCreated twice."""
        await core.create_choice(make_request(), USER_UID)

        created = [e for e in event_bus.get_event_history() if isinstance(e, ChoiceCreated)]
        assert len(created) == 1, f"expected 1 ChoiceCreated, got {len(created)}"


# ============================================================================
# PARITY — the two doors must not diverge again
# ============================================================================


@pytest.mark.asyncio
class TestDoorsAgree:
    """Same request through both doors → same persisted choice."""

    async def test_both_doors_persist_the_same_options(
        self, core: ChoicesCoreService, facade: ChoicesService, backend: StubChoicesBackend
    ) -> None:
        from core.services.conversion_service import ConversionServiceV2

        request = make_request()

        # DOOR A: exactly what CRUDRouteFactory does — convert, then service.create()
        entity = ConversionServiceV2.get_converter(type(request))(
            request, "choice:door-a", user_uid=USER_UID
        )
        door_a = await facade.create(entity)

        # DOOR B: the facade/UI door
        door_b = await core.create_choice(request, USER_UID)

        assert door_a.is_ok and door_b.is_ok, (
            f"door A: {door_a.error if door_a.is_error else 'ok'}, "
            f"door B: {door_b.error if door_b.is_error else 'ok'}"
        )
        assert [o.title for o in door_a.value.options] == [o.title for o in door_b.value.options], (
            "the two create doors persisted different options for the same request"
        )

    @pytest.mark.parametrize(
        ("options", "choice_type", "should_fail"),
        [
            pytest.param(
                [ChoiceOptionRequest(title="Only one")],
                ChoiceType.MULTIPLE,
                True,
                id="one-option-rejected",
            ),
            pytest.param(
                [ChoiceOptionRequest(title=t) for t in ("A", "B", "C")],
                ChoiceType.BINARY,
                True,
                id="binary-with-three-rejected",
            ),
            pytest.param([], ChoiceType.MULTIPLE, False, id="no-options-allowed"),
            pytest.param([], ChoiceType.BINARY, False, id="binary-no-options-allowed"),
        ],
    )
    async def test_both_doors_reach_the_same_verdict(
        self,
        core: ChoicesCoreService,
        facade: ChoicesService,
        options: list[ChoiceOptionRequest],
        choice_type: ChoiceType,
        should_fail: bool,
    ) -> None:
        """Agreement asserted directly, rather than against a hand-copied matrix.

        Agreement alone would be satisfied by both doors being equally wrong —
        which is exactly the pre-fix state — so the settled verdict is asserted
        too. Otherwise this test is vacuous against the bug it guards.
        """
        from core.services.conversion_service import ConversionServiceV2

        request = make_request(options=options, choice_type=choice_type)
        entity = ConversionServiceV2.get_converter(type(request))(
            request, "choice:door-a", user_uid=USER_UID
        )

        door_a = await facade.create(entity)
        door_b = await core.create_choice(request, USER_UID)

        assert door_a.is_error == door_b.is_error, (
            f"doors disagree on the same request: "
            f"door A is_error={door_a.is_error}, door B is_error={door_b.is_error}"
        )
        assert door_a.is_error is should_fail, (
            f"expected is_error={should_fail}, got {door_a.is_error} "
            f"({door_a.error if door_a.is_error else 'accepted'})"
        )


@pytest.mark.asyncio
class TestKnowledgeEdgesPrecedeTheEvent:
    """`ChoiceCreated` must not fire until the choice's graph edges are written.

    `ChoiceCreated` is subscribed to `invalidate_context`, which debounces 100ms and
    then rebuilds the user context — and the rebuild reads `choice_knowledge_informed`
    back out of the graph. Announcing the choice before `create_relationships_batch`
    completes lets the rebuild observe zero INFORMED_BY_KNOWLEDGE edges and cache that
    for the full 300s TTL; the later KnowledgeInformedChoice events reach only substance
    handlers and never invalidate the context, so nothing corrects it.

    Regression guard for the ordering inversion Codex caught on #960.
    """

    async def test_edges_are_written_before_choice_created(
        self, core: ChoicesCoreService, backend: StubChoicesBackend, event_bus: InMemoryEventBus
    ) -> None:
        published: list[str] = []

        def _record(event: ChoiceCreated) -> None:
            published.append("choice_created")
            backend.trace.append("choice_created_published")

        event_bus.subscribe(ChoiceCreated, _record)

        result = await core.create_choice(
            make_request(informed_by_knowledge_uids=["ku_a", "ku_b"]), USER_UID
        )

        assert result.is_ok, f"create_choice failed: {result.error}"
        assert published, "ChoiceCreated was never published"
        assert backend.trace.index("knowledge_edges_written") < backend.trace.index(
            "choice_created_published"
        ), (
            "ChoiceCreated fired BEFORE the knowledge edges were written — a context "
            f"rebuild would cache a choice with no edges. Order was: {backend.trace}"
        )

    async def test_route_door_still_publishes_without_edges(
        self, facade: ChoicesService, event_bus: InMemoryEventBus
    ) -> None:
        """Positive control: deferring the publish must not lose it on the door that
        writes no knowledge edges at all."""
        result = await facade.create(make_choice())

        assert result.is_ok, f"create failed: {result.error}"
        assert [e for e in event_bus.get_event_history() if isinstance(e, ChoiceCreated)], (
            "the route door stopped publishing ChoiceCreated"
        )


@pytest.mark.asyncio
class TestLiveDoorsStillWork:
    """The reason options are optional at creation, asserted against the real payloads.

    Turning the rules on is only safe because these doors keep working. Each builds
    the exact request its production caller builds; if a future tightening of
    ``_validate_create`` breaks one, it breaks here first rather than in the app.
    """

    async def test_ui_form_submission_still_creates(self, core: ChoicesCoreService) -> None:
        """The create form collects only title/description/choice_type/domain/priority
        /decision_deadline — ui/activities/choices_form.py deliberately omits the
        nested options list and every free-text list field."""
        form_only = ChoiceCreateRequest(
            title="Should I switch stacks?",
            description="Captured from the create form, options added on the detail page",
            choice_type=ChoiceType.MULTIPLE,
            domain=Domain.TECH,
            priority=Priority.MEDIUM,
        )

        result = await core.create_choice(form_only, USER_UID)

        assert result.is_ok, f"the UI create form's own payload was rejected: {result.error}"

    async def test_dsl_ingested_choice_still_creates(self, core: ChoicesCoreService) -> None:
        """DSL activity ingestion infers BINARY from prose ("should i", "whether", ...)
        and supplies no options — core/services/dsl/activity_domain_converters.py."""
        dsl_shaped = ChoiceCreateRequest(
            title="Should I take the contract",
            description="Should I take the contract or stay put",
            choice_type=ChoiceType.BINARY,
            tags=["high-energy"],
        )

        result = await core.create_choice(dsl_shaped, USER_UID)

        assert result.is_ok, f"a DSL-ingested choice was rejected: {result.error}"
        assert result.value.choice_type == ChoiceType.BINARY
