"""
The Activity link invariant: a link between two Activity domains is read, and shown, at both ends.
====================================================================================================

ADR-090 §1 and §2, derived from the relationship registry (``LABEL_CONFIGS``), never from a
hand list of pairs: ``tests/helpers/activity_links.py`` holds the derivation, shared with
the page tests. A ``both`` definition on an Activity config that is neither a
shared-neighbour definition nor a lateral type is refused outright, since it has no ends
to check.

**Rule 1 — both ends.** For every edge type joining two DIFFERENT Activity domains, the
source's config holds an outgoing definition whose far end is the target or ``Entity``,
and the target's config an incoming one whose far end is the source or ``Entity``.
Same-type pairs are a later pass (R8). An ``Entity`` far end stands for every config that
declares the same type in the opposite direction. A view filtered on an edge property (a
tier view such as ``essential_habits``) does not read the link: it lists only the edges
that carry its value.

**Rule 2 — a view lists one kind.** A view on an Activity config whose far end is
``Entity``, over an edge type that reaches that config from more than one kind of node,
names its kind in ``target_label`` (the declaration half), and every keyed reader on
``UnifiedRelationshipService`` carries the definition's ``target_label`` and its tier
(``filter_property``) to the backend (the read half). The probe sees the arguments the
backend is called with, not the query it runs; that the query applies them is
``tests/integration/test_keyed_readers.py``'s to show.

**Rule 3 — what a page reads, it shows** (R10). Every end that reads a link between two
Activities (Rule 1) shows it: one of its unfiltered views of the link carries a
``page_heading``, the domain's name for it, which the page lists it under. A link read at
one end only (``MISSING_ENDS``) is shown at the end that reads it.

**Rule 4 — no link listed twice.** No two headed views on one config share an edge type
and a direction while their far ends overlap (an ``Entity`` far end overlaps every
label). A view filtered on an edge property carries no heading: the page places an edge
by type, direction and far-end label, never by its properties.

**Rule 5 — one heading, one view.** No two headed views on one config share a heading. A
link is one stored fact (ADR-090 §1), so a heading names exactly one view of it.

The two gap lists (``MISSING_ENDS``, ``MIXED_VIEWS``) are empty: the arc closed every
entry (docs/roadmap/done/activity-links-arc.md § PR ledger). Each still fails both ways: a new
gap is red until it is closed or listed with the work that closes it, and a listed gap
that is closed or gone is red until its entry is removed.

What the registry cannot show, and how the test answers it:

- An ``Entity`` far end with no definition of its type in the opposite direction resolves
  to nothing. Each such Activity view is listed in ``FAR_END_NOT_ANOTHER_ACTIVITY`` with
  what its far end is, so a new Activity link declared that way is red until someone
  says what it reaches.
- An Activity that writes an edge type its config does not declare at all is invisible
  here: the registry is the test's only source. Writers are each PR's own census.

See: docs/decisions/ADR-090-one-link-per-fact-a-view-per-domain.md
     docs/roadmap/done/activity-links-arc.md
"""

import dataclasses
import inspect
from collections.abc import Callable, Coroutine, Mapping
from typing import Any, NamedTuple

import pytest

from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import (
    GOALS_CONFIG,
    LABEL_CONFIGS,
    DomainRelationshipConfig,
    UnifiedRelationshipDefinition,
)
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService
from core.utils.result_simplified import Result
from tests.helpers.activity_links import (
    ACTIVITY_LABELS,
    Link,
    activity_links,
    configs,
    declarations,
    far_ends,
    links,
    links_read_at_both_ends,
    reads,
    shows,
    undeclared_edge,
)


class MissingEnd(NamedTuple):
    """A link between two Activities that one of its ends does not read."""

    source: NeoLabel
    edge: RelationshipName
    target: NeoLabel
    unread_at: NeoLabel


class View(NamedTuple):
    """One registry definition: its config's label, its edge type, its method key."""

    label: NeoLabel
    edge: RelationshipName
    method_key: str


# ============================================================================
# The known gaps — each names the ledger row that removes it
# ============================================================================

MISSING_ENDS: dict[MissingEnd, str] = {}

MIXED_VIEWS: dict[View, str] = {}


# ============================================================================
# Standing registers — not gaps; they do not empty
# ============================================================================

# Keyed methods that write, not read: a write names both of its uids. The delete also
# carries the definition's far-end label (TestOneKindPerView probes it).
KEYED_WRITERS: dict[str, str] = {
    "create_relationship": "the far end's kind is admitted from the door's LinkFarEnd",
    "create_relationships_batch": "the far ends' kind is admitted from the door's LinkFarEnd",
    "create_relationship_with_properties": "names both uids",
    "delete_relationship": "names both uids and carries the far end's label",
    "reorder_relationships": "rewrites the order of edges to named uids",
}

# Keyed readers whose far-end label comes from their caller, not from the definition.
READERS_GIVEN_THE_LABEL: dict[str, str] = {
    "get_hierarchical_children": "a (key, label) pair per hop of a curriculum chain",
}

# Activity views whose far end is Entity and whose type no config declares in the
# opposite direction — the registry cannot resolve them, so each says what it reaches.
FAR_END_NOT_ANOTHER_ACTIVITY: dict[View, str] = {
    **{
        View(label, RelationshipName.SERVES_LIFE_PATH, "life_path"): "the user's LifePath"
        for label in (
            NeoLabel.TASK,
            NeoLabel.GOAL,
            NeoLabel.HABIT,
            NeoLabel.EVENT,
            NeoLabel.CHOICE,
            NeoLabel.PRINCIPLE,
        )
    },
    View(NeoLabel.TASK, RelationshipName.UNLOCKS_KNOWLEDGE, "unlocks_knowledge"): "a Ku",
    View(NeoLabel.TASK, RelationshipName.INFERRED_KNOWLEDGE, "inferred_knowledge"): "a Ku",
    View(
        NeoLabel.CHOICE, RelationshipName.REQUIRES_KNOWLEDGE_FOR_DECISION, "required_knowledge"
    ): "a Ku",
    View(NeoLabel.PRINCIPLE, RelationshipName.GROUNDED_IN_KNOWLEDGE, "knowledge"): "a Ku",
    View(NeoLabel.GOAL, RelationshipName.ALIGNED_WITH_PATH, "aligned_paths"): "a LearningPath",
    View(
        NeoLabel.GOAL, RelationshipName.REQUIRES_PATH_COMPLETION, "required_paths"
    ): "a LearningPath",
    View(NeoLabel.HABIT, RelationshipName.ENABLES_HABIT, "enabling_habits"): (
        "another Habit — a same-type link, the later pass (R8)"
    ),
}


# ============================================================================
# The derivation
# ============================================================================


def _missing_ends(label_configs: Mapping[str, DomainRelationshipConfig]) -> set[MissingEnd]:
    """Rule 1: each end of a link between two different Activities that does not read it."""
    declared = declarations(label_configs)
    missing: set[MissingEnd] = set()
    for link in activity_links(label_configs):
        if not reads(declared, link.source, "outgoing", link.edge, link.target):
            missing.add(MissingEnd(*link, unread_at=link.source))
        if not reads(declared, link.target, "incoming", link.edge, link.source):
            missing.add(MissingEnd(*link, unread_at=link.target))
    return missing


def _unshown_ends(label_configs: Mapping[str, DomainRelationshipConfig]) -> set[MissingEnd]:
    """Rule 3: each end that reads a link between two Activities but does not show it."""
    declared = declarations(label_configs)
    unshown: set[MissingEnd] = set()
    for link in activity_links(label_configs):
        for at, direction, far_end in (
            (link.source, "outgoing", link.target),
            (link.target, "incoming", link.source),
        ):
            if reads(declared, at, direction, link.edge, far_end) and not shows(
                declared, at, direction, link.edge, far_end
            ):
                unshown.add(MissingEnd(*link, unread_at=at))
    return unshown


def _double_listings(
    label_configs: Mapping[str, DomainRelationshipConfig],
) -> set[tuple[View, View]]:
    """Rule 4: two headed views on one config that would list the same edge twice."""
    doubled: set[tuple[View, View]] = set()
    for label, config in configs(label_configs).items():
        headed = [definition for definition in config.relationships if definition.page_heading]
        for index, first in enumerate(headed):
            for second in headed[index + 1 :]:
                if (
                    first.relationship == second.relationship
                    and first.direction == second.direction
                    and (
                        NeoLabel.ENTITY in (first.target_label, second.target_label)
                        or first.target_label == second.target_label
                    )
                ):
                    doubled.add(
                        (
                            View(label, first.relationship, first.method_key),
                            View(label, second.relationship, second.method_key),
                        )
                    )
    return doubled


def _shared_headings(
    label_configs: Mapping[str, DomainRelationshipConfig],
) -> set[tuple[View, View]]:
    """Rule 5: two headed views on one config under the same heading."""
    shared: set[tuple[View, View]] = set()
    for label, config in configs(label_configs).items():
        headed = [definition for definition in config.relationships if definition.page_heading]
        for index, first in enumerate(headed):
            for second in headed[index + 1 :]:
                if first.page_heading == second.page_heading:
                    shared.add(
                        (
                            View(label, first.relationship, first.method_key),
                            View(label, second.relationship, second.method_key),
                        )
                    )
    return shared


def _entity_views(
    label_configs: Mapping[str, DomainRelationshipConfig],
) -> list[tuple[View, set[NeoLabel]]]:
    """Every Activity view whose far end is Entity, with the labels it resolves to."""
    declared = declarations(label_configs)
    return [
        (
            View(label, definition.relationship, definition.method_key),
            far_ends(definition, declared),
        )
        for label, definition in declared
        if label in ACTIVITY_LABELS and definition.target_label == NeoLabel.ENTITY
    ]


def _mixed_views(label_configs: Mapping[str, DomainRelationshipConfig]) -> set[View]:
    """Rule 2, the declaration half: an Entity view over more than one kind of far end."""
    return {view for view, resolved in _entity_views(label_configs) if len(resolved) > 1}


def _unresolved_views(label_configs: Mapping[str, DomainRelationshipConfig]) -> set[View]:
    """Activity views whose Entity far end has nothing to resolve against."""
    return {view for view, resolved in _entity_views(label_configs) if not resolved}


# ============================================================================
# Copies of the registry for the instrument's own controls (never an edit to it)
# ============================================================================


def _replacing(
    label: NeoLabel,
    relationships: Callable[
        [tuple[UnifiedRelationshipDefinition, ...]], tuple[UnifiedRelationshipDefinition, ...]
    ],
    label_configs: Mapping[str, DomainRelationshipConfig],
) -> dict[str, DomainRelationshipConfig]:
    config = label_configs[label]
    replaced = dataclasses.replace(config, relationships=relationships(config.relationships))
    return {
        key: replaced if registered is config else registered
        for key, registered in label_configs.items()
    }


def _with_definitions(
    label: NeoLabel,
    *added: UnifiedRelationshipDefinition,
    label_configs: Mapping[str, DomainRelationshipConfig] = LABEL_CONFIGS,
) -> dict[str, DomainRelationshipConfig]:
    """A copy of ``label_configs`` whose ``label`` config also declares ``added``."""

    def widen(
        relationships: tuple[UnifiedRelationshipDefinition, ...],
    ) -> tuple[UnifiedRelationshipDefinition, ...]:
        return (*relationships, *added)

    return _replacing(label, widen, label_configs)


def _without_definition(label: NeoLabel, method_key: str) -> dict[str, DomainRelationshipConfig]:
    """A copy of ``LABEL_CONFIGS`` whose ``label`` config no longer declares ``method_key``."""

    def narrow(
        relationships: tuple[UnifiedRelationshipDefinition, ...],
    ) -> tuple[UnifiedRelationshipDefinition, ...]:
        kept = tuple(
            definition for definition in relationships if definition.method_key != method_key
        )
        assert len(kept) < len(relationships), f"{label} declares no {method_key}"
        return kept

    return _replacing(label, narrow, LABEL_CONFIGS)


def _definition(
    edge: RelationshipName,
    far_end: NeoLabel,
    direction: str,
    method_key: str = "probe",
    heading: str | None = None,
) -> UnifiedRelationshipDefinition:
    return UnifiedRelationshipDefinition(
        relationship=edge,
        target_label=far_end,
        direction=direction,
        context_field_name=method_key,
        method_key=method_key,
        page_heading=heading,
    )


# ============================================================================
# The read half: does a keyed reader carry target_label to the backend?
# ============================================================================

PROBE_FAR_END = NeoLabel.HABIT

PROBE_TIER = ("essentiality", "probe_tier")

PROBE_VIEW = dataclasses.replace(
    _definition(RelationshipName.SUPPORTS_GOAL, PROBE_FAR_END, "incoming"),
    filter_property=PROBE_TIER[0],
    filter_value=PROBE_TIER[1],
)

# The arguments a keyed reader takes beside its key
PROBE_ARGUMENTS: dict[str, str | list[str]] = {
    "entity_uid": "goal_probe",
    "entity_uids": ["goal_probe"],
}


class _RecordingBackend:
    """Answers every backend call with an empty success and records its arguments.

    The owner read is the one call whose empty success is a mapping (nobody owns the
    probe), so a link write can go on to its own call.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def __getattr__(self, name: str) -> Callable[..., Coroutine[object, object, Result[Any]]]:
        if name.startswith("__"):
            raise AttributeError(name)

        async def record(*args: object, **kwargs: object) -> Result[Any]:
            self.calls.append((name, args, kwargs))
            return Result.ok({} if name == "get_owner_uids_batch" else 0)

        return record


def _mentions(value: object, label: NeoLabel) -> bool:
    """Whether ``label`` is ``value``, sits in a collection of it, or is a passed definition's."""
    if isinstance(value, str):
        return value == label
    if isinstance(value, UnifiedRelationshipDefinition):
        return value.target_label == label
    if isinstance(value, Mapping):
        return any(_mentions(item, label) for item in (*value.keys(), *value.values()))
    if isinstance(value, list | tuple | set | frozenset):
        return any(_mentions(item, label) for item in value)
    return False


def _keyed_methods() -> set[str]:
    """Public methods that take a registry key or look one up."""
    return {
        name
        for name, method in inspect.getmembers(UnifiedRelationshipService, inspect.isfunction)
        if not name.startswith("_")
        and (
            "relationship_key" in inspect.signature(method).parameters
            or "get_relationship_by_method" in inspect.getsource(method)
        )
    }


def _mentions_tier(value: object) -> bool:
    """Whether the probe's tier sits in ``value`` as a key with its value, at any depth."""
    if isinstance(value, Mapping):
        key, tier = PROBE_TIER
        return value.get(key) == tier or any(_mentions_tier(item) for item in value.values())
    if isinstance(value, list | tuple | set | frozenset):
        return any(_mentions_tier(item) for item in value)
    return False


class _Reach(NamedTuple):
    """What a keyed reader carried to the backend over the probe view."""

    label: bool
    tier: bool


async def _reaches_backend_with(
    reader: str,
    label: NeoLabel = PROBE_FAR_END,
    service_class: type[UnifiedRelationshipService] | None = None,
) -> _Reach:
    """Run ``reader`` over the probe view; whether ``label`` and the tier reached the backend.

    A keyed method this cannot call (a parameter ``PROBE_ARGUMENTS`` does not know) fails
    here, so a new keyed method is red until it is listed where it belongs.
    """
    backend = _RecordingBackend()
    config = dataclasses.replace(GOALS_CONFIG, relationships=(PROBE_VIEW,))
    service = (service_class or UnifiedRelationshipService)(backend=backend, config=config)
    method = getattr(service, reader)
    parameters = list(inspect.signature(method).parameters.values())[1:]
    unknown = [
        parameter.name
        for parameter in parameters
        if parameter.name not in PROBE_ARGUMENTS and parameter.default is inspect.Parameter.empty
    ]
    assert not unknown, (
        f"{reader} takes {unknown}: list it in KEYED_WRITERS if it writes, in "
        "READERS_GIVEN_THE_LABEL if its caller names the far end's label, or teach "
        "PROBE_ARGUMENTS what to pass"
    )
    arguments = {p.name: PROBE_ARGUMENTS[p.name] for p in parameters if p.name in PROBE_ARGUMENTS}

    result = await method(PROBE_VIEW.method_key, **arguments)

    assert not result.is_error, f"{reader} failed over the probe view: {result}"
    assert backend.calls, f"{reader} reached no backend call"
    passed = [(args, kwargs) for _name, args, kwargs in backend.calls]
    return _Reach(
        label=any(_mentions(call, label) for call in passed),
        tier=any(_mentions_tier(call) for call in passed),
    )


def _keyed_readers() -> set[str]:
    return _keyed_methods() - set(KEYED_WRITERS) - set(READERS_GIVEN_THE_LABEL)


# ============================================================================
# Rule 1 — both ends
# ============================================================================


class TestBothEnds:
    def test_every_missing_end_is_listed(self):
        unlisted = _missing_ends(LABEL_CONFIGS) - set(MISSING_ENDS)

        assert not unlisted, (
            "These links between two Activities are not read at one end. Declare the "
            "missing view on that end's config, or list the gap in MISSING_ENDS with the "
            f"ledger row that closes it: {sorted(unlisted)}"
        )

    def test_every_listed_end_is_missing(self):
        closed = set(MISSING_ENDS) - _missing_ends(LABEL_CONFIGS)

        assert not closed, (
            f"MISSING_ENDS lists ends that are read now, or that are gone — remove: {sorted(closed)}"
        )

    def test_no_activity_link_is_declared_both_ways(self):
        both_ways = {
            View(label, definition.relationship, definition.method_key)
            for label, config in configs(LABEL_CONFIGS).items()
            if label in ACTIVITY_LABELS
            for definition in config.relationships
            if definition.direction == "both"
            and definition.shared_neighbor_config is None
            and not definition.relationship.is_lateral_relationship()
        }

        assert not both_ways, (
            "A 'both' definition has no source and no target, so the test cannot check "
            f"its ends. Declare each direction on its own: {sorted(both_ways)}"
        )


# ============================================================================
# Rules 3 and 4 — the page (R10)
# ============================================================================


class TestThePageShowsWhatItReads:
    def test_every_end_that_reads_a_link_shows_it(self):
        unshown = _unshown_ends(LABEL_CONFIGS)

        assert not unshown, (
            "These ends read a link between two Activities but give it no page_heading, "
            "so their page does not show it. Name the link from that domain's side "
            f"(ADR-090 §2): {sorted(unshown)}"
        )

    def test_no_link_is_listed_twice_on_a_page(self):
        doubled = _double_listings(LABEL_CONFIGS)

        assert not doubled, (
            "These headed views share an edge type and a direction with overlapping far "
            "ends, so the page would list the same edge under both. Keep the heading on "
            f"one of them: {sorted(doubled)}"
        )

    def test_no_two_views_share_a_heading(self):
        shared = _shared_headings(LABEL_CONFIGS)

        assert not shared, (
            "These headed views on one config share a heading, so the page lists two "
            f"views of a link as one. Give each view its own name: {sorted(shared)}"
        )

    def test_no_tier_view_carries_a_heading(self):
        tiered = {
            View(label, definition.relationship, definition.method_key)
            for label, config in configs(LABEL_CONFIGS).items()
            for definition in config.relationships
            if definition.page_heading is not None and definition.filter_property is not None
        }

        assert not tiered, (
            "The page reader places an edge by its type, direction and far-end label, not "
            "by its properties, so a headed view filtered on an edge property would list "
            f"every edge of its type under the tier's heading: {sorted(tiered)}"
        )

    def test_both_ends_census_is_the_registry_less_its_missing_ends(self):
        missing = {(end.source, end.edge, end.target) for end in MISSING_ENDS}

        assert set(links_read_at_both_ends()) == {
            link for link in activity_links(LABEL_CONFIGS) if tuple(link) not in missing
        }


# ============================================================================
# Rule 2 — a view lists one kind
# ============================================================================


class TestOneKindPerView:
    def test_every_mixed_view_is_listed(self):
        unlisted = _mixed_views(LABEL_CONFIGS) - set(MIXED_VIEWS)

        assert not unlisted, (
            "These Activity views read an edge type that reaches them from more than one "
            "kind of node, with an Entity far end. Name the kind in target_label, or list "
            f"the view in MIXED_VIEWS with the ledger row that closes it: {sorted(unlisted)}"
        )

    def test_every_listed_view_is_mixed(self):
        closed = set(MIXED_VIEWS) - _mixed_views(LABEL_CONFIGS)

        assert not closed, (
            "MIXED_VIEWS lists views that name one kind now, or that are gone — remove: "
            f"{sorted(closed)}"
        )

    async def test_every_keyed_reader_carries_target_label(self):
        dropping = {r for r in _keyed_readers() if not (await _reaches_backend_with(r)).label}

        assert not dropping, (
            "These keyed readers do not carry the definition's target_label to the "
            "backend, so a view that names one kind still lists every kind: "
            f"{sorted(dropping)}"
        )

    @pytest.mark.parametrize(
        ("direction", "labelled_end", "open_end"),
        [("incoming", "from_label", "to_label"), ("outgoing", "to_label", "from_label")],
    )
    async def test_the_keyed_delete_carries_the_far_ends_label(
        self, direction, labelled_end, open_end
    ):
        """Two kinds can share an edge type and a direction, so a key deletes only an
        edge whose far end is of its own kind — the label sits on the far end."""
        view = _definition(RelationshipName.SUPPORTS_GOAL, PROBE_FAR_END, direction)
        backend = _RecordingBackend()
        # boundary: the recording backend stands in for any domain's operations
        service = UnifiedRelationshipService[Any, Any, Any](
            backend=backend, config=dataclasses.replace(GOALS_CONFIG, relationships=(view,))
        )

        await service.delete_relationship(view.method_key, "goal_probe", "far_probe")

        [(_args, kwargs)] = [
            (args, kwargs) for name, args, kwargs in backend.calls if name == "delete_relationship"
        ]
        assert kwargs[labelled_end] == PROBE_FAR_END
        assert kwargs[open_end] is None

    async def test_every_keyed_reader_carries_the_tier(self):
        dropping = {r for r in _keyed_readers() if not (await _reaches_backend_with(r)).tier}

        assert not dropping, (
            "These keyed readers do not carry the definition's edge-property filter to "
            "the backend, so a tier view lists every tier: "
            f"{sorted(dropping)}"
        )

    def test_every_registered_keyed_method_exists(self):
        gone = (set(KEYED_WRITERS) | set(READERS_GIVEN_THE_LABEL)) - _keyed_methods()

        assert not gone, (
            "KEYED_WRITERS / READERS_GIVEN_THE_LABEL list methods that neither take nor "
            f"look up a registry key — remove: {sorted(gone)}"
        )


# ============================================================================
# Entity far ends the registry cannot resolve
# ============================================================================


class TestUnresolvedFarEnds:
    def test_every_unresolved_view_is_listed(self):
        unlisted = _unresolved_views(LABEL_CONFIGS) - set(FAR_END_NOT_ANOTHER_ACTIVITY)

        assert not unlisted, (
            "These Activity views have an Entity far end that no config declares in the "
            "opposite direction, so the test cannot tell whether they link two Activities. "
            "Name the far end's label, declare the other end, or list the view in "
            f"FAR_END_NOT_ANOTHER_ACTIVITY with what it reaches: {sorted(unlisted)}"
        )

    def test_every_listed_view_is_unresolved(self):
        resolved = set(FAR_END_NOT_ANOTHER_ACTIVITY) - _unresolved_views(LABEL_CONFIGS)

        assert not resolved, (
            "FAR_END_NOT_ANOTHER_ACTIVITY lists views that resolve now, or that are gone "
            f"— remove: {sorted(resolved)}"
        )


# ============================================================================
# The instrument sees what it claims to see
# ============================================================================


class TestTheInstrument:
    """Each control is built on an edge type no config declares, so no PR in the arc moves it."""

    def test_aliases_are_read_once(self):
        assert NeoLabel.PATH_STEP in configs(LABEL_CONFIGS)
        assert NeoLabel.LEARNING_PATH in configs(LABEL_CONFIGS)
        assert len(configs(LABEL_CONFIGS)) == len({id(config) for config in LABEL_CONFIGS.values()})

    def test_a_view_declared_at_the_source_only_is_a_missing_end(self):
        edge = undeclared_edge()
        configs = _with_definitions(NeoLabel.TASK, _definition(edge, NeoLabel.CHOICE, "outgoing"))

        added = _missing_ends(configs) - _missing_ends(LABEL_CONFIGS)

        assert added == {
            MissingEnd(NeoLabel.TASK, edge, NeoLabel.CHOICE, unread_at=NeoLabel.CHOICE)
        }

    def test_a_view_declared_at_the_target_only_is_a_missing_end(self):
        edge = undeclared_edge()
        configs = _with_definitions(NeoLabel.GOAL, _definition(edge, NeoLabel.EVENT, "incoming"))

        added = _missing_ends(configs) - _missing_ends(LABEL_CONFIGS)

        assert added == {MissingEnd(NeoLabel.EVENT, edge, NeoLabel.GOAL, unread_at=NeoLabel.EVENT)}

    def test_a_link_declared_at_both_ends_is_not_missing(self):
        edge = undeclared_edge()
        configs = _with_definitions(
            NeoLabel.GOAL,
            _definition(edge, NeoLabel.TASK, "incoming"),
            label_configs=_with_definitions(
                NeoLabel.TASK, _definition(edge, NeoLabel.ENTITY, "outgoing")
            ),
        )

        assert Link(NeoLabel.TASK, edge, NeoLabel.GOAL) in links(declarations(configs))
        assert _missing_ends(configs) == _missing_ends(LABEL_CONFIGS)

    def test_a_tier_view_alone_does_not_read_the_link(self):
        configs = _without_definition(NeoLabel.GOAL, "supporting_habits")

        added = _missing_ends(configs) - _missing_ends(LABEL_CONFIGS)

        assert added == {
            MissingEnd(
                NeoLabel.HABIT,
                RelationshipName.SUPPORTS_GOAL,
                NeoLabel.GOAL,
                unread_at=NeoLabel.GOAL,
            )
        }

    def test_an_entity_far_end_with_no_counterpart_is_unresolved(self):
        edge = undeclared_edge()
        configs = _with_definitions(NeoLabel.TASK, _definition(edge, NeoLabel.ENTITY, "outgoing"))

        added = _unresolved_views(configs) - _unresolved_views(LABEL_CONFIGS)

        assert added == {View(NeoLabel.TASK, edge, "probe")}

    def test_an_entity_view_over_several_kinds_of_source_is_mixed(self):
        edge = undeclared_edge()
        sources = _with_definitions(
            NeoLabel.EVENT,
            _definition(edge, NeoLabel.GOAL, "outgoing"),
            label_configs=_with_definitions(
                NeoLabel.TASK, _definition(edge, NeoLabel.GOAL, "outgoing")
            ),
        )
        configs = _with_definitions(
            NeoLabel.GOAL, _definition(edge, NeoLabel.ENTITY, "incoming"), label_configs=sources
        )

        added = _mixed_views(configs) - _mixed_views(LABEL_CONFIGS)

        assert added == {View(NeoLabel.GOAL, edge, "probe")}

    def test_a_view_naming_its_kind_is_not_mixed(self):
        edge = undeclared_edge()
        sources = _with_definitions(
            NeoLabel.EVENT,
            _definition(edge, NeoLabel.GOAL, "outgoing"),
            label_configs=_with_definitions(
                NeoLabel.TASK, _definition(edge, NeoLabel.GOAL, "outgoing")
            ),
        )
        configs = _with_definitions(
            NeoLabel.GOAL, _definition(edge, NeoLabel.TASK, "incoming"), label_configs=sources
        )

        assert _mixed_views(configs) == _mixed_views(LABEL_CONFIGS)

    def test_a_link_read_but_not_headed_at_one_end_is_unshown_there(self):
        edge = undeclared_edge()
        configs_ = _with_definitions(
            NeoLabel.CHOICE,
            _definition(edge, NeoLabel.TASK, "incoming"),
            label_configs=_with_definitions(
                NeoLabel.TASK, _definition(edge, NeoLabel.CHOICE, "outgoing", heading="probe")
            ),
        )

        added = _unshown_ends(configs_) - _unshown_ends(LABEL_CONFIGS)

        assert added == {
            MissingEnd(NeoLabel.TASK, edge, NeoLabel.CHOICE, unread_at=NeoLabel.CHOICE)
        }

    def test_a_link_headed_at_both_ends_is_shown(self):
        edge = undeclared_edge()
        configs_ = _with_definitions(
            NeoLabel.CHOICE,
            _definition(edge, NeoLabel.ENTITY, "incoming", heading="probe"),
            label_configs=_with_definitions(
                NeoLabel.TASK, _definition(edge, NeoLabel.CHOICE, "outgoing", heading="probe")
            ),
        )

        assert Link(NeoLabel.TASK, edge, NeoLabel.CHOICE) in activity_links(configs_)
        assert _unshown_ends(configs_) == _unshown_ends(LABEL_CONFIGS)

    def test_a_headed_tier_view_alone_does_not_show_the_link(self):
        edge = undeclared_edge()
        tier = dataclasses.replace(
            _definition(edge, NeoLabel.ENTITY, "incoming", heading="probe"),
            filter_property="essentiality",
            filter_value="essential",
        )
        configs_ = _with_definitions(
            NeoLabel.GOAL,
            _definition(edge, NeoLabel.HABIT, "incoming", "plain"),
            tier,
            label_configs=_with_definitions(
                NeoLabel.HABIT, _definition(edge, NeoLabel.GOAL, "outgoing", heading="probe")
            ),
        )

        added = _unshown_ends(configs_) - _unshown_ends(LABEL_CONFIGS)

        assert added == {MissingEnd(NeoLabel.HABIT, edge, NeoLabel.GOAL, unread_at=NeoLabel.GOAL)}

    def test_two_headed_views_over_overlapping_far_ends_are_a_double_listing(self):
        edge = undeclared_edge()
        configs_ = _with_definitions(
            NeoLabel.HABIT,
            _definition(edge, NeoLabel.TASK, "incoming", "from_tasks", heading="a"),
            _definition(edge, NeoLabel.ENTITY, "incoming", "from_anything", heading="b"),
        )

        added = _double_listings(configs_) - _double_listings(LABEL_CONFIGS)

        assert added == {
            (
                View(NeoLabel.HABIT, edge, "from_tasks"),
                View(NeoLabel.HABIT, edge, "from_anything"),
            )
        }

    def test_two_views_under_one_heading_share_it(self):
        edge = undeclared_edge()
        configs_ = _with_definitions(
            NeoLabel.HABIT,
            _definition(edge, NeoLabel.TASK, "incoming", "from_tasks", heading="a"),
            _definition(edge, NeoLabel.EVENT, "incoming", "from_events", heading="a"),
        )

        added = _shared_headings(configs_) - _shared_headings(LABEL_CONFIGS)

        assert added == {
            (View(NeoLabel.HABIT, edge, "from_tasks"), View(NeoLabel.HABIT, edge, "from_events"))
        }

    def test_two_edge_types_under_one_heading_share_it(self):
        # One link is one stored fact, so two edge types never share a name either.
        first, second = undeclared_edge(0), undeclared_edge(1)
        configs_ = _with_definitions(
            NeoLabel.HABIT,
            _definition(first, NeoLabel.TASK, "incoming", "from_tasks", heading="a"),
            _definition(second, NeoLabel.TASK, "incoming", "also_from_tasks", heading="a"),
        )

        added = _shared_headings(configs_) - _shared_headings(LABEL_CONFIGS)

        assert added == {
            (
                View(NeoLabel.HABIT, first, "from_tasks"),
                View(NeoLabel.HABIT, second, "also_from_tasks"),
            )
        }

    def test_views_under_different_headings_do_not_share_one(self):
        configs_ = _with_definitions(
            NeoLabel.HABIT,
            _definition(undeclared_edge(), NeoLabel.TASK, "incoming", "from_tasks", heading="a"),
            _definition(undeclared_edge(), NeoLabel.EVENT, "incoming", "from_events", heading="b"),
        )

        assert _shared_headings(configs_) == _shared_headings(LABEL_CONFIGS)

    def test_headed_views_naming_different_far_ends_are_not_a_double_listing(self):
        edge = undeclared_edge()
        configs_ = _with_definitions(
            NeoLabel.HABIT,
            _definition(edge, NeoLabel.TASK, "incoming", "from_tasks", heading="a"),
            _definition(edge, NeoLabel.EVENT, "incoming", "from_events", heading="b"),
            _definition(edge, NeoLabel.ENTITY, "incoming", "unheaded"),
        )

        assert _double_listings(configs_) == _double_listings(LABEL_CONFIGS)

    @pytest.mark.parametrize(
        "value",
        [
            {"target_label": PROBE_FAR_END},
            {"labels": [PROBE_FAR_END, NeoLabel.PATH_STEP]},
            PROBE_VIEW,
        ],
    )
    def test_the_probe_sees_a_label_however_it_is_passed(self, value):
        assert _mentions(value, PROBE_FAR_END)

    @pytest.mark.parametrize(
        "value",
        [
            {"relationship_type": "REINFORCES_HABIT", "entity_label": NeoLabel.ENTITY},
            dataclasses.replace(GOALS_CONFIG, relationships=(PROBE_VIEW,)),
        ],
    )
    def test_the_probe_does_not_see_a_label_it_was_not_passed(self, value):
        assert not _mentions(value, PROBE_FAR_END)

    async def test_the_probe_tells_what_a_reader_carries_from_what_it_drops(
        self,
    ):
        class CarriesTheLabel(UnifiedRelationshipService):
            async def get_related_uids(self, relationship_key, entity_uid):
                spec = self.config.get_relationship_by_method(relationship_key)
                assert spec is not None, relationship_key
                return await self.backend.get_related_uids(
                    uid=entity_uid,
                    relationship_type=spec.relationship,
                    direction=spec.direction,
                    target_label=spec.target_label,
                )

        class CarriesTheTier(UnifiedRelationshipService):
            async def get_related_uids(self, relationship_key, entity_uid):
                spec = self.config.get_relationship_by_method(relationship_key)
                assert spec is not None, relationship_key
                return await self.backend.get_related_uids(
                    uid=entity_uid,
                    relationship_type=spec.relationship,
                    direction=spec.direction,
                    properties={spec.filter_property: spec.filter_value},
                )

        class DropsTheLabel(UnifiedRelationshipService):
            async def get_related_uids(self, relationship_key, entity_uid):
                spec = self.config.get_relationship_by_method(relationship_key)
                assert spec is not None, relationship_key
                return await self.backend.get_related_uids(
                    uid=entity_uid,
                    relationship_type=spec.relationship,
                    direction=spec.direction,
                    config=self.config,
                )

        carries_label = await _reaches_backend_with(
            "get_related_uids", service_class=CarriesTheLabel
        )
        carries_tier = await _reaches_backend_with("get_related_uids", service_class=CarriesTheTier)
        drops_both = await _reaches_backend_with("get_related_uids", service_class=DropsTheLabel)

        assert (carries_label.label, carries_label.tier) == (True, False)
        assert (carries_tier.label, carries_tier.tier) == (False, True)
        assert (drops_both.label, drops_both.tier) == (False, False)
