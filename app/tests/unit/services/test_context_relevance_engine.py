"""The relevance engine finds the published knowledge around a learner's activities.

Each activity's knowledge is read in two depth-1 rings
(``GraphIntelligenceService.get_entity_context``): what the activity links itself
(``DIRECT``), then what sits one edge from that knowledge (``ADJACENT``). The second
ring grows out of knowledge only, so a goal's knowledge is never credited to a task
that merely contributes to the goal. Every ``GraphContext`` here is built by the real
transformer from rows shaped like the shared producer's, so edge direction is read the
way production reads it.

The real-traversal half is ``tests/integration/test_relevance_engine_knowledge.py``.
"""

from __future__ import annotations

import pytest

from core.models.enums import Domain, EntityType, KuComplexity, RelevanceRing
from core.models.graph_context import GraphContext
from core.models.query_types import QueryIntent
from core.models.type_hints import Neo4jProperties
from core.ports.query_types import PrerequisiteGraphRow
from core.services.askesis.context_relevance_engine import (
    ContextRelevanceEngine,
    prerequisites_first,
)
from core.services.infrastructure.graph_record_transformer import (
    build_graph_context_from_domain_context,
)
from core.utils.result_simplified import Errors, Result

TASK = "task_mine"
HABIT = "habit_mine"
GOAL = "goal_mine"
KU_A = "ku.rel.a"  # linked by the task and the habit
KU_B = "ku.rel.b"  # a prerequisite of KU_A
KU_C = "ku.rel.c"  # the goal's knowledge — the task contributes to the goal
KU_E = "ku.rel.e"  # linked by the task alone
PS = "ps.rel.step"  # uses KU_A
DRAFT = "ku.rel.draft"


def _row(
    uid: str,
    entity_type: str | None,
    rel: str,
    *,
    into_neighbour: bool,
    **properties: str,
) -> dict[str, object]:
    """One producer row: a neighbour one edge from the center, and that edge."""
    props: Neo4jProperties = {"uid": uid, "title": f"title of {uid}", **properties}
    if entity_type is not None:
        props["entity_type"] = entity_type
    return {
        "uid": uid,
        "labels": ["Entity"],
        "properties": props,
        "distance": 1,
        "path_strength": 0.8,
        "via_relationships": [("->" if into_neighbour else "<-") + rel],
        "incident_rel_type": rel,
        "incident_into_related": into_neighbour,
        "incident_rel_properties": {},
    }


def _context(center: str, rows: list[dict[str, object]]) -> GraphContext:
    return build_graph_context_from_domain_context(
        rows, center, Domain.KNOWLEDGE, QueryIntent.RELATIONSHIP, 1
    )


CONTEXTS: dict[str, GraphContext] = {
    TASK: _context(
        TASK,
        [
            _row("user_mine", None, "OWNS", into_neighbour=False),
            _row(KU_A, "ku", "APPLIES_KNOWLEDGE", into_neighbour=True, domain="knowledge"),
            _row(KU_E, "ku", "APPLIES_KNOWLEDGE", into_neighbour=True),
            _row(DRAFT, "ku", "APPLIES_KNOWLEDGE", into_neighbour=True, publication_state="draft"),
            _row(GOAL, "goal", "CONTRIBUTES_TO_GOAL", into_neighbour=True),
        ],
    ),
    HABIT: _context(HABIT, [_row(KU_A, "ku", "REINFORCES_KNOWLEDGE", into_neighbour=True)]),
    KU_A: _context(
        KU_A,
        [
            _row(KU_B, "ku", "REQUIRES_KNOWLEDGE", into_neighbour=True, complexity="hard"),
            _row(
                PS,
                "path_step",
                "USES_KU",
                into_neighbour=False,
                domain="health",
                complexity="advanced",
            ),
            _row(DRAFT, "ku", "REQUIRES_KNOWLEDGE", into_neighbour=True, publication_state="draft"),
        ],
    ),
    KU_E: _context(KU_E, []),
    GOAL: _context(GOAL, [_row(KU_C, "ku", "REQUIRES_KNOWLEDGE", into_neighbour=True)]),
}


class _FakeBackend:
    def __init__(self, requires: dict[str, list[str]], fail: bool = False) -> None:
        self.requires = requires
        self.fail = fail

    async def get_prerequisite_graph(
        self, ku_uids: list[str]
    ) -> Result[list[PrerequisiteGraphRow]]:
        if self.fail:
            return Result.fail(Errors.database(operation="get_prerequisite_graph", message="down"))
        return Result.ok(
            [{"uid": uid, "prerequisites": self.requires.get(uid, [])} for uid in ku_uids]
        )


class _FakeGraphIntel:
    """A graph intelligence service holding the contexts above — and no other read."""

    def __init__(
        self,
        *,
        missing: frozenset[str] = frozenset(),
        failing: frozenset[str] = frozenset(),
        prerequisites_fail: bool = False,
    ) -> None:
        self.backend = _FakeBackend({KU_A: [KU_B]}, fail=prerequisites_fail)
        self.missing = missing
        self.failing = failing
        self.asked: list[tuple[str, int]] = []

    async def get_entity_context(self, entity_uid: str, depth: int = 2) -> Result[GraphContext]:
        self.asked.append((entity_uid, depth))
        if entity_uid in self.failing:
            return Result.fail(Errors.database(operation="get_entity_context", message="down"))
        if entity_uid in self.missing or entity_uid not in CONTEXTS:
            return Result.fail(Errors.not_found(resource="Entity", identifier=entity_uid))
        return Result.ok(CONTEXTS[entity_uid])


def _engine(graph: _FakeGraphIntel) -> ContextRelevanceEngine:
    return ContextRelevanceEngine(graph_intel=graph)


@pytest.mark.asyncio
async def test_two_rings_credit_published_knowledge_and_name_their_route() -> None:
    graph = _FakeGraphIntel()

    result = await _engine(graph).find_relevant_for_context(
        current_habits=[HABIT], pending_tasks=[TASK], min_relevance_score=0.0
    )

    assert result.is_ok, result
    found = result.value
    assert [unit["uid"] for unit in found["knowledge_units"]] == [KU_A, KU_B, PS, KU_E]
    # The goal's Ku is the goal's: no read grows out of an activity's other activities.
    assert (GOAL, 1) not in graph.asked
    assert all(depth == 1 for _, depth in graph.asked)
    # KU_A's own neighbourhood is read once though two activities link it.
    assert graph.asked.count((KU_A, 1)) == 1

    assert found["relevance_reasons"][KU_A] == [
        {
            "activity_uid": HABIT,
            "activity_type": EntityType.HABIT,
            "ring": RelevanceRing.DIRECT,
            "via_uid": None,
            "relationship": "REINFORCES_KNOWLEDGE",
            "outgoing": True,
        },
        {
            "activity_uid": TASK,
            "activity_type": EntityType.TASK,
            "ring": RelevanceRing.DIRECT,
            "via_uid": None,
            "relationship": "APPLIES_KNOWLEDGE",
            "outgoing": True,
        },
    ]
    assert found["relevance_reasons"][PS] == [
        {
            "activity_uid": activity,
            "activity_type": activity_type,
            "ring": RelevanceRing.ADJACENT,
            "via_uid": KU_A,
            "relationship": "USES_KU",
            "outgoing": False,  # the step uses KU_A: the edge points at KU_A
        }
        for activity, activity_type in ((HABIT, EntityType.HABIT), (TASK, EntityType.TASK))
    ]
    assert found["domain_coverage"][KU_B] == [EntityType.HABIT, EntityType.TASK]
    assert found["domain_coverage"][KU_E] == [EntityType.TASK]
    assert found["relevance_scores"] == {KU_A: 0.7, KU_B: 0.7, PS: 0.7, KU_E: 0.35}


@pytest.mark.asyncio
async def test_rows_carry_what_the_file_authored_and_nothing_invented() -> None:
    result = await _engine(_FakeGraphIntel()).find_relevant_for_context(
        current_habits=[HABIT], pending_tasks=[TASK], min_relevance_score=0.0
    )

    assert result.is_ok, result
    rows = {unit["uid"]: unit for unit in result.value["knowledge_units"]}
    assert rows[PS] == {
        "uid": PS,
        "title": f"title of {PS}",
        "entity_type": EntityType.PATH_STEP,
        "domain": Domain.HEALTH,
        "complexity": KuComplexity.ADVANCED,
    }
    # "knowledge" is the default every entity carries, not a subject; "hard" is no level.
    assert (rows[KU_A]["domain"], rows[KU_A]["complexity"]) == (None, None)
    assert (rows[KU_B]["domain"], rows[KU_B]["complexity"]) == (None, None)
    assert rows[KU_A]["entity_type"] is EntityType.KU


@pytest.mark.asyncio
async def test_recommended_order_puts_each_prerequisite_first() -> None:
    result = await _engine(_FakeGraphIntel()).find_relevant_for_context(
        current_habits=[HABIT], pending_tasks=[TASK], min_relevance_score=0.0
    )

    assert result.is_ok, result
    assert result.value["recommended_order"] == [KU_B, PS, KU_E, KU_A]


@pytest.mark.asyncio
async def test_default_threshold_needs_two_reasons() -> None:
    result = await _engine(_FakeGraphIntel()).find_relevant_for_context(
        current_habits=[HABIT], pending_tasks=[TASK]
    )

    assert result.is_ok, result
    # Two reasons and two kinds: 0.7. One reason and one kind: 0.35, under 0.5.
    assert [unit["uid"] for unit in result.value["knowledge_units"]] == [KU_A, KU_B, PS]


@pytest.mark.asyncio
async def test_a_missing_activity_contributes_nothing() -> None:
    graph = _FakeGraphIntel(missing=frozenset({HABIT}))

    result = await _engine(graph).find_relevant_for_context(
        current_habits=[HABIT], pending_tasks=[TASK], min_relevance_score=0.0
    )

    assert result.is_ok, result
    assert result.value["domain_coverage"][KU_A] == [EntityType.TASK]


@pytest.mark.parametrize(
    "graph",
    [
        pytest.param(_FakeGraphIntel(failing=frozenset({TASK})), id="activity-read"),
        pytest.param(_FakeGraphIntel(failing=frozenset({KU_A})), id="neighbourhood-read"),
        pytest.param(_FakeGraphIntel(prerequisites_fail=True), id="prerequisite-read"),
    ],
)
@pytest.mark.asyncio
async def test_a_failed_read_fails_the_call(graph: _FakeGraphIntel) -> None:
    result = await _engine(graph).find_relevant_for_context(
        current_habits=[HABIT], pending_tasks=[TASK], min_relevance_score=0.0
    )

    assert result.is_error


def test_prerequisites_first_orders_a_chain_and_keeps_ties_in_input_order() -> None:
    requires = {"c": ["b"], "b": ["a"], "x": ["outside"]}

    assert prerequisites_first(["c", "x", "b", "a"], requires) == ["x", "a", "b", "c"]


def test_prerequisites_first_leaves_a_cycle_in_input_order() -> None:
    requires = {"a": ["b"], "b": ["a"], "c": ["a"]}

    assert prerequisites_first(["c", "a", "b", "d"], requires) == ["d", "c", "a", "b"]
