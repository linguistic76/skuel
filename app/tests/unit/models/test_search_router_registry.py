"""
SearchRouter registry completeness + UserEntry privacy guards.

The class of bug these tests prevent: ``_SEARCHABLE_DOMAINS`` promising a
domain whose ``_SERVICE_REGISTRY`` attribute the ``Services`` container never
composes. That combination made ``supports_search()`` lie and ``search()``
silently return not_found — user entries were unsearchable for months while
every surface claimed otherwise.

No live database needed: the registry guards introspect the ``Services``
dataclass fields and the router's own constructor signature (explicit DI —
compose passes ``services.<name>`` for each same-named parameter); the routing
guards monkeypatch the router's internals.
"""

import dataclasses
import inspect
from typing import Any

import pytest

from core.models.enums import SearchVisibility
from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.models.ps_content.content_chunks import ContentChunkType
from core.models.search.filter_enums import SearchSortOrder
from core.models.search_request import SearchRequest
from core.orchestrator.search_router import SearchRouter, UnifiedSearchResult
from core.utils.result_simplified import Result
from services_bootstrap import Services

SERVICES_FIELD_NAMES = {f.name for f in dataclasses.fields(Services)}


class TestRegistryCompleteness:
    """Every searchable domain must resolve to a real Services field."""

    def test_searchable_domains_are_registered(self) -> None:
        """Every _SEARCHABLE_DOMAINS member has a _SERVICE_REGISTRY entry."""
        unregistered = [
            et
            for et in SearchRouter._SEARCHABLE_DOMAINS
            if et not in SearchRouter._SERVICE_REGISTRY
        ]
        assert not unregistered, (
            f"_SEARCHABLE_DOMAINS promises search for {unregistered} but "
            "_SERVICE_REGISTRY has no service attribute for them — "
            "supports_search() lies and search() silently returns not_found."
        )

    def test_registry_attributes_exist_on_services_container(self) -> None:
        """Every _SERVICE_REGISTRY value is an actual Services dataclass field."""
        phantom = {
            et: attr
            for et, attr in SearchRouter._SERVICE_REGISTRY.items()
            if attr not in SERVICES_FIELD_NAMES
        }
        assert not phantom, (
            f"_SERVICE_REGISTRY points at Services attributes that do not exist: {phantom}. "
            "getattr(services, attr, None) degrades this to a silent not_found at runtime."
        )

    def test_registry_keys_match_constructor_service_dict(self) -> None:
        """Every _SERVICE_REGISTRY key is dispatchable: __init__ builds a
        _domain_services entry for it (and nothing extra)."""
        router = SearchRouter()
        assert set(router._domain_services) == set(SearchRouter._SERVICE_REGISTRY), (
            "_SERVICE_REGISTRY and the constructor-built _domain_services dict "
            "disagree — an enum routed by the registry has no constructor "
            "parameter carrying its service (or vice versa)."
        )

    def test_registry_attributes_are_constructor_params(self) -> None:
        """Every _SERVICE_REGISTRY value names a SearchRouter.__init__ parameter.

        The explicit-DI counterpart of the Services-field check: compose passes
        ``services.<name>`` to the parameter of the same name, so a registry
        value without a matching parameter is a domain search silently lost.
        """
        params = set(inspect.signature(SearchRouter.__init__).parameters) - {"self"}
        phantom = {
            et: attr for et, attr in SearchRouter._SERVICE_REGISTRY.items() if attr not in params
        }
        assert not phantom, (
            f"_SERVICE_REGISTRY names constructor parameters that do not exist: {phantom}."
        )

    def test_constructor_params_exist_on_services_container(self) -> None:
        """Every SearchRouter.__init__ parameter is a real Services field.

        Pins the name-for-name convention compose relies on
        (``SearchRouter(tasks=services.tasks, ...)``) — a container rename
        must rename the router parameter with it.
        """
        params = set(inspect.signature(SearchRouter.__init__).parameters) - {"self"}
        phantom = sorted(params - SERVICES_FIELD_NAMES)
        assert not phantom, (
            f"SearchRouter.__init__ takes parameters with no Services field: {phantom}. "
            "compose.py wires each parameter from the same-named container field."
        )

    def test_graph_aware_domain_strings_exist_on_services_container(self) -> None:
        """_GRAPH_AWARE_DOMAINS strings are used directly as Services attributes."""
        phantom = sorted(SearchRouter._GRAPH_AWARE_DOMAINS - SERVICES_FIELD_NAMES)
        assert not phantom, (
            f"_GRAPH_AWARE_DOMAINS names Services attributes that do not exist: {phantom}. "
            "This is how the stale 'submissions' → 'submissions_search' alias shipped broken."
        )


class TestOwnerOnlyDomainsCarryTheScopingProperty:
    """Every searchable OWNER_ONLY domain must have the property the clause filters.

    ``build_search_visibility_clause`` renders OWNER_ONLY as
    ``entity.{ownership_property} = $user_uid`` — a *property* predicate on the
    domain's ``DomainConfig.ownership_property`` declaration (default
    ``user_uid``; Group declares ``owner_uid`` — ADR-086). A domain whose
    declared property does not exist on its model gets a predicate that is
    null for every row, so its search silently returns nothing.

    This became reachable when faceted search stopped anchoring on
    ``(User)-[:OWNS]->(entity)``: the edge anchor happened to work for such a
    domain, the property predicate does not. Codex flagged exactly this shape
    on ``GroupService`` (P2, PR #1079) — correct about the mechanism, and the
    ``ownership_property`` declaration is the fix. This test is the guard
    that keeps every declaration pointing at a real model field.
    """

    # The one domain that legitimately keys on owner_uid WITHOUT declaring it
    # via ownership_property: Exercise's owned half rides inside SCOPE_AWARE,
    # whose composition hardcodes the owner_uid claim + :OWNS edge dual read.
    # Its exemption is verified below rather than asserted, so the set cannot
    # quietly grow.
    _OWNER_UID_EXEMPT = frozenset({EntityType.EXERCISE})

    # THE config that governs each searchable domain's search scoping — the
    # class whose ``search_visibility`` / ``ownership_property`` properties
    # feed the search mixin. Facades and their search sub-services build
    # their configs from the same factory, so one entry per domain suffices;
    # Ku/PS/LP facades carry no _config, so their search services stand in.
    @staticmethod
    def _search_config_services() -> dict[EntityType, Any]:
        from core.services.choices_service import ChoicesService
        from core.services.events_service import EventsService
        from core.services.exercises.exercise_service import ExerciseService
        from core.services.goals_service import GoalsService
        from core.services.habits_service import HabitsService
        from core.services.ku.ku_search_service import KuSearchService
        from core.services.lp.lp_search_service import LpSearchService
        from core.services.principles_service import PrinciplesService
        from core.services.ps.ps_search_service import PsSearchService
        from core.services.revised_exercises.revised_exercise_service import (
            RevisedExerciseService,
        )
        from core.services.tasks_service import TasksService
        from core.services.user_entry.user_entry_service import UserEntryService

        return {
            EntityType.TASK: TasksService,
            EntityType.GOAL: GoalsService,
            EntityType.HABIT: HabitsService,
            EntityType.EVENT: EventsService,
            EntityType.CHOICE: ChoicesService,
            EntityType.PRINCIPLE: PrinciplesService,
            EntityType.KU: KuSearchService,
            EntityType.PATH_STEP: PsSearchService,
            EntityType.LEARNING_PATH: LpSearchService,
            EntityType.EXERCISE: ExerciseService,
            EntityType.REVISED_EXERCISE: RevisedExerciseService,
            EntityType.USER_ENTRY: UserEntryService,
        }

    def test_the_owner_uid_exemption_is_earned_not_declared(self) -> None:
        """Exercise may key on ``owner_uid`` only because it declares SCOPE_AWARE."""
        from core.services.exercises.exercise_service import ExerciseService

        assert EntityType.EXERCISE in self._OWNER_UID_EXEMPT
        assert len(self._OWNER_UID_EXEMPT) == 1, (
            "the exemption set must not grow silently — each member needs its own "
            "earned justification, like the SCOPE_AWARE check below"
        )
        assert ExerciseService._config.get_search_visibility() is SearchVisibility.SCOPE_AWARE, (
            "Exercise's exemption below rests on it NOT being OWNER_ONLY"
        )

    def test_every_searchable_owner_only_domain_declares_a_real_property(self) -> None:
        """The declared ownership_property must exist on the domain's model.

        Tightened from the earlier user_uid/owner_uid heuristic (ownership
        bundle PR-4): the clause now renders whatever the domain DECLARES, so
        the guard asserts the declaration itself — for every searchable
        OWNER_ONLY domain, ``DomainConfig.ownership_property`` names a real
        field on ``model_class``. A declaration pointing at a phantom field is
        a search that silently returns nothing for every user.
        """
        import dataclasses as dc

        service_by_type = self._search_config_services()
        missing = sorted(
            et.value for et in SearchRouter._SEARCHABLE_DOMAINS if et not in service_by_type
        )
        assert not missing, (
            f"searchable domains missing from the config-service map: {missing} — "
            "extend _search_config_services so their declarations stay guarded"
        )

        offenders: list[str] = []
        examined: list[EntityType] = []
        for entity_type in SearchRouter._SEARCHABLE_DOMAINS:
            if entity_type in self._OWNER_UID_EXEMPT:
                continue
            config = service_by_type[entity_type]._config
            if config.get_search_visibility() is not SearchVisibility.OWNER_ONLY:
                # PUBLIC curriculum carries no owner — the OWNER_ONLY clause
                # never composes for it, so there is no declaration to check.
                continue
            examined.append(entity_type)
            fields = {f.name for f in dc.fields(config.model_class)}
            if config.ownership_property not in fields:
                offenders.append(
                    f"{entity_type.value} declares ownership_property="
                    f"{config.ownership_property!r} but {config.model_class.__name__} "
                    f"has no such field"
                )

        assert examined, "no OWNER_ONLY domain examined — the guard is not guarding"
        assert offenders == [], (
            "a searchable OWNER_ONLY domain declares an ownership_property its "
            f"model does not carry, so its search returns nothing: {offenders}"
        )

    def test_group_declares_the_property_it_actually_writes(self) -> None:
        """Group's declaration is coherent: owner_uid, and the model carries it.

        Group stores ownership as ``owner_uid`` (not the Entity-wide
        ``user_uid``), so its config declares ``ownership_property="owner_uid"``
        — the OWNER_ONLY clause renders the property Group actually writes
        (ADR-086; the fix for Codex P2 on #1079).
        """
        import dataclasses as dc

        from core.models.group.group import Group
        from core.services.groups.group_service import GroupService

        config = GroupService._config
        assert config.get_search_visibility() is SearchVisibility.OWNER_ONLY
        assert config.ownership_property == "owner_uid"
        assert "owner_uid" in {f.name for f in dc.fields(Group)}

    def test_group_is_not_a_searchable_domain(self) -> None:
        """Group's absence from search stays a deliberate pin, not an accident.

        ``GroupService`` now declares ``ownership_property="owner_uid"``
        (verified above), so its inherited search would scope correctly — but
        Group remains absent from every search registry, and wiring it in is
        a product decision, not a side effect. This pin makes that wiring an
        explicit act: whoever adds Group to a registry must also extend
        ``_search_config_services`` above, keeping the declaration guarded.
        """
        registry_values = set(SearchRouter._SERVICE_REGISTRY.values())
        assert "groups" not in registry_values
        assert "groups" not in SearchRouter._GRAPH_AWARE_DOMAINS
        assert NonKuDomain.GROUP not in SearchRouter._SERVICE_REGISTRY


class _OwnerOnlySearchStub:
    """A wired, OWNER_ONLY-declaring search service that records every call.

    Wired deliberately: an *unwired* router refuses everything with not_found,
    so a test built on one passes even with the ownership gate deleted.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    @property
    def search_visibility(self) -> SearchVisibility:
        return SearchVisibility.OWNER_ONLY

    async def search(
        self, query: str, limit: int = 50, user_uid: str | None = None
    ) -> Result[list[object]]:
        self.calls.append((query, user_uid))
        return Result.ok([object()])


class TestOwnerOnlySearchScopeGate:
    """Unscoped OWNER_ONLY search must be refused, never leaked.

    UserEntry was the first domain to get this line (entries are private user
    content). It is not special: every OWNER_ONLY domain composes the same
    ownership predicate, and ``build_search_visibility_clause`` emits NO
    predicate without a user — so an unscoped call returns every user's rows
    unless ``search()`` refuses first.
    """

    @pytest.mark.asyncio
    async def test_search_without_user_uid_is_refused(self) -> None:
        stub = _OwnerOnlySearchStub()
        router = SearchRouter(user_entry=stub)

        result = await router.search(EntityType.USER_ENTRY, "anything")

        assert result.is_error
        assert "user scope" in str(result.expect_error().message)
        assert stub.calls == [], "the domain must never be queried unscoped"

    @pytest.mark.asyncio
    async def test_search_with_user_uid_reaches_the_domain(self) -> None:
        """Positive control: the gate refuses the null uid, not every call."""
        stub = _OwnerOnlySearchStub()
        router = SearchRouter(user_entry=stub)

        result = await router.search(EntityType.USER_ENTRY, "anything", user_uid="user_a")

        assert result.is_ok, result.expect_error()
        assert stub.calls == [("anything", "user_a")]

    @pytest.mark.asyncio
    async def test_task_domain_gets_the_same_gate(self) -> None:
        """The gate is keyed on the visibility declaration, not on UserEntry."""
        stub = _OwnerOnlySearchStub()
        router = SearchRouter(tasks=stub)

        result = await router.search(EntityType.TASK, "anything")

        assert result.is_error
        assert "user scope" in str(result.expect_error().message)
        assert stub.calls == []

    @pytest.mark.asyncio
    async def test_anonymous_faceted_single_domain_never_queries_unscoped(self) -> None:
        """The production-reachable shape: an anonymous single-domain faceted call.

        ``/api/explore/search`` serves anonymous callers and resolves its raw
        ``?type=`` param through ``EntityType.from_string`` with no catalog
        whitelist, so ``?type=revised_exercise`` reaches
        ``faceted_search(request, user_uid=None)`` for an OWNER_ONLY domain.
        There, ``_graph_aware_domain_search`` correctly declines (anonymous +
        non-PUBLIC) and hands off to ``_simple_domain_search`` — which mapped
        ``revised_exercises`` to a real EntityType and called ``search()``
        without any scope. Every teacher's revised exercises, to a logged-out
        caller.

        ``user_entry`` never had this hole: ``faceted_search`` guards it by
        name at the entry point. The gate under test is the general form of
        that guard.

        Asserted on the stub's call log, not just on the returned rows: an
        empty response is the right answer for several wrong reasons, but a
        domain query issued with ``user_uid=None`` is unambiguous.
        """
        stub = _OwnerOnlySearchStub()
        router = SearchRouter(revised_exercises=stub)

        result = await router.faceted_search(
            SearchRequest(query_text="anything", entity_types=[EntityType.REVISED_EXERCISE]),
            user_uid=None,
            log_event=False,
        )

        assert result.is_ok, result.expect_error()
        assert result.value.results == []
        assert stub.calls == [], (
            "an anonymous faceted call must never reach an OWNER_ONLY domain's "
            f"search — got {stub.calls}"
        )

    @pytest.mark.asyncio
    async def test_authenticated_faceted_single_domain_forwards_the_scope(self) -> None:
        """Positive control, and the second half of the same defect.

        ``_simple_domain_search`` took no ``user_uid`` at all, so the scope was
        dropped for authenticated callers too. Refusing unscoped searches
        without also forwarding the scope would have turned that leak into an
        owner seeing an empty page — fail-closed, but still wrong.

        The explicit sort is load-bearing, not decoration: it makes
        ``_cross_domain_search`` take the faceted sweep, which skips this
        non-graph-aware stub. Without it the scored text sweep would issue a
        second, correctly-scoped ``search()`` and the assertion below would
        pass even with the scope still dropped upstream.
        """
        stub = _OwnerOnlySearchStub()
        router = SearchRouter(revised_exercises=stub)

        result = await router.faceted_search(
            SearchRequest(
                query_text="anything",
                entity_types=[EntityType.REVISED_EXERCISE],
                sort_order=SearchSortOrder.TITLE_ASC,
            ),
            user_uid="user_teacher",
            log_event=False,
        )

        assert result.is_ok, result.expect_error()
        assert stub.calls == [("anything", "user_teacher")]

    @pytest.mark.asyncio
    async def test_cross_domain_sweep_excludes_user_entry(self, monkeypatch) -> None:
        """The default 'All Types' sweep never touches the UserEntry store."""
        router = SearchRouter()
        swept_types: list[EntityType | NonKuDomain] = []
        swept_uids: list[str | None] = []

        async def fake_search_domains(entity_types, query, limit_per_domain=20, user_uid=None):
            swept_types.extend(entity_types)
            swept_uids.append(user_uid)
            return UnifiedSearchResult(query=query, results_by_domain={}, total_count=0)

        monkeypatch.setattr(router, "search_domains", fake_search_domains)

        request = SearchRequest(query_text="anything")
        result = await router.faceted_search(request, user_uid="user_a")

        assert result.is_ok
        assert EntityType.USER_ENTRY not in swept_types
        assert EntityType.TASK in swept_types
        # Owner scope threads through so user-owned domains filter server-side
        assert swept_uids == ["user_a"]

    @pytest.mark.asyncio
    async def test_explicit_multi_type_filter_includes_user_entry(self, monkeypatch) -> None:
        """[USER_ENTRY, TASK] narrows the sweep and keeps entries (scoped)."""
        router = SearchRouter()
        swept_types: list[EntityType | NonKuDomain] = []
        swept_uids: list[str | None] = []

        async def fake_search_domains(entity_types, query, limit_per_domain=20, user_uid=None):
            swept_types.extend(entity_types)
            swept_uids.append(user_uid)
            return UnifiedSearchResult(query=query, results_by_domain={}, total_count=0)

        monkeypatch.setattr(router, "search_domains", fake_search_domains)

        request = SearchRequest(
            query_text="anything", entity_types=[EntityType.USER_ENTRY, EntityType.TASK]
        )
        result = await router.faceted_search(request, user_uid="user_a")

        assert result.is_ok
        assert swept_types == [EntityType.USER_ENTRY, EntityType.TASK]
        assert swept_uids == ["user_a"]

    @pytest.mark.asyncio
    async def test_faceted_user_entry_without_user_is_refused(self) -> None:
        """A user_entry faceted request with no user fails loudly, not empty-ok."""
        router = SearchRouter()

        request = SearchRequest(query_text="anything", entity_types=[EntityType.USER_ENTRY])
        result = await router.faceted_search(request, user_uid=None)

        assert result.is_error
        assert "user scope" in str(result.expect_error().message)

    @pytest.mark.asyncio
    async def test_advanced_search_skips_user_entry(self) -> None:
        """Cross-domain advanced search (unscoped strategies) skips UserEntry.

        USER_ENTRY is excluded from eligibility before any service lookup —
        an ok/empty result (never a not_found error) proves the skip fired.
        """
        router = SearchRouter()

        request = SearchRequest(query_text="anything", entity_types=[EntityType.USER_ENTRY])
        result = await router.advanced_search(request)

        assert result.is_ok
        assert result.value.total_count == 0
        assert not result.value.results_by_domain


class TestSingleEntityTypeRouting:
    """The /search dropdown filter routes to the single-domain path."""

    def test_user_entry_filter_resolves_to_user_entry_domain(self) -> None:
        router = SearchRouter()
        request = SearchRequest(query_text="x", entity_types=[EntityType.USER_ENTRY])

        assert router._resolve_single_domain(request) == "user_entry"

    def test_task_filter_resolves_to_tasks_domain(self) -> None:
        router = SearchRouter()
        request = SearchRequest(query_text="x", entity_types=[EntityType.TASK])

        assert router._resolve_single_domain(request) == "tasks"

    def test_no_filter_resolves_to_none(self) -> None:
        router = SearchRouter()
        request = SearchRequest(query_text="x")

        assert router._resolve_single_domain(request) is None

    def test_multiple_filters_resolve_to_none(self) -> None:
        """Two or more entity types stay on the cross-domain path."""
        router = SearchRouter()
        request = SearchRequest(query_text="x", entity_types=[EntityType.TASK, EntityType.GOAL])

        assert router._resolve_single_domain(request) is None

    def test_ku_filter_resolves_to_ku_domain(self) -> None:
        """Ku is a searchable curriculum domain — the /search 'Knowledge
        Units' dropdown option routes to the single-domain path."""
        router = SearchRouter()
        request = SearchRequest(query_text="x", entity_types=[EntityType.KU])

        assert router._resolve_single_domain(request) == "ku"

    def test_non_searchable_type_resolves_to_none(self) -> None:
        """LIFE_PATH is registered for get_service but NOT searchable — the
        dropdown filter must stay consistent with search()'s supports_search()
        gate."""
        router = SearchRouter()
        request = SearchRequest(query_text="x", entity_types=[EntityType.LIFE_PATH])

        assert router._resolve_single_domain(request) is None

    @pytest.mark.asyncio
    async def test_user_entry_filter_routes_graph_aware_with_user(self, monkeypatch) -> None:
        """user_entry filter + user → OWNS-scoped graph-aware domain search."""
        router = SearchRouter()
        captured: dict[str, str] = {}

        async def fake_graph_aware(request, user_uid, domain_str):
            captured["domain"] = domain_str
            captured["user_uid"] = user_uid
            from core.models.search_request import SearchResponse
            from core.utils.result_simplified import Result

            return Result.ok(
                SearchResponse(
                    results=[],
                    total=0,
                    limit=request.limit,
                    offset=request.offset,
                    query_text=request.query_text,
                    domain=domain_str,
                    facet_counts={},
                    applied_filters={},
                    search_time_ms=0.0,
                )
            )

        monkeypatch.setattr(router, "_graph_aware_domain_search", fake_graph_aware)

        request = SearchRequest(query_text="tasks list", entity_types=[EntityType.USER_ENTRY])
        result = await router.faceted_search(request, user_uid="user_a")

        assert result.is_ok
        assert captured["domain"] == "user_entry"
        assert captured["user_uid"] == "user_a"


class TestBodyChunkAggregation:
    """Parent-dedup + best-chunk-score aggregation for lesson-BODY search.

    DB-free: exercises SearchRouter._aggregate_body_chunk_parents directly with
    fabricated :ContentChunk hit dicts. Guards the merge/dedup contract that the
    body-chunk augmentation relies on — max score per parent, scope filtering,
    and dedupe against parents already in the base results.
    """

    @staticmethod
    def _hit(parent_uid: str, parent_type: str, score: float, text: str = "body prose") -> dict:
        return {
            "chunk_uid": f"chunk_{parent_uid}_{score}",
            # A real persisted value — "CONCEPT" is not a ContentChunkType member
            # at all, so no writer could ever produce it.
            "chunk_type": ContentChunkType.EXPLANATION.value,
            "text": text,
            "context_window": None,
            "similarity_score": score,
            "parent_uid": parent_uid,
            "parent_title": parent_uid.split(".")[-1].title(),
            "parent_entity_type": parent_type,
        }

    def test_best_score_per_parent(self) -> None:
        """Multiple chunks of one parent collapse to a single card at MAX score."""
        hits = [
            self._hit("ku.discipline.visualization", "ku", 0.71, "first passage"),
            self._hit("ku.discipline.visualization", "ku", 0.88, "best passage"),
            self._hit("ku.discipline.visualization", "ku", 0.75, "third passage"),
        ]
        results = SearchRouter._aggregate_body_chunk_parents(
            hits, frozenset({"ku"}), existing_uids=set()
        )
        assert len(results) == 1
        card = results[0]
        assert card["uid"] == "ku.discipline.visualization"
        assert card["_domain"] == "ku"
        assert card["_score"] == 0.88
        assert card["description"] == "best passage"

    def test_dedupes_against_existing_parents(self) -> None:
        """A parent already in the base results is not re-listed as a body hit."""
        hits = [self._hit("ku.discipline.visualization", "ku", 0.9)]
        results = SearchRouter._aggregate_body_chunk_parents(
            hits, frozenset({"ku"}), existing_uids={"ku.discipline.visualization"}
        )
        assert results == []

    def test_scope_filters_out_of_target_types(self) -> None:
        """Parents outside the in-scope curriculum types are dropped."""
        hits = [
            self._hit("ku.a", "ku", 0.9),
            self._hit("ps.b", "path_step", 0.95),
        ]
        # Single-domain Ku search: only Ku parents survive.
        results = SearchRouter._aggregate_body_chunk_parents(
            hits, frozenset({"ku"}), existing_uids=set()
        )
        assert [r["uid"] for r in results] == ["ku.a"]

    def test_cross_domain_ranks_both_types_by_score(self) -> None:
        """Cross-domain scope keeps Ku and PS, ranked by best-chunk score desc."""
        hits = [
            self._hit("ku.a", "ku", 0.80),
            self._hit("ps.b", "path_step", 0.92),
            self._hit("ku.c", "ku", 0.85),
        ]
        results = SearchRouter._aggregate_body_chunk_parents(
            hits, frozenset({"ku", "path_step"}), existing_uids=set()
        )
        assert [r["uid"] for r in results] == ["ps.b", "ku.c", "ku.a"]
        assert [r["_domain"] for r in results] == ["path_step", "ku", "ku"]

    def test_empty_hits_returns_empty(self) -> None:
        """No chunk hits → no body cards."""
        assert SearchRouter._aggregate_body_chunk_parents([], frozenset({"ku"}), set()) == []
