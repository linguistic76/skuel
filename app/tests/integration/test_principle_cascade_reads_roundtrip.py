"""Real-Neo4j guards for the principle strength-cascade relationship reads.

``PrincipleEventHandlerService.handle_principle_strength_changed`` analyzes which
goals and habits a principle's strength change cascades to. Both reads were broken
(same class as #198's phantom call):

* goals used ``relationships.get_principle_goals(...)`` — a method declared on the
  protocol but **implemented nowhere** → AttributeError, swallowed by the handler's
  fire-and-forget try/except → goals silently never counted.
* habits used ``relationships.get_related_uids("habits", ...)`` — ``"habits"`` is not
  a PRINCIPLES_CONFIG method key, so the reader returned an error Result → habits
  silently never counted.

The fix routes both through the generic config-keyed reader with the *real* keys:
``"guided_goals"`` (GUIDES_GOAL) and ``"inspired_habits"`` (INSPIRES_HABIT).

A mocked relationship service can't catch either (it returns success for any key /
any attribute). These tests resolve the edges against real Neo4j, with a built-in
negative control on the dead ``"habits"`` key.
"""

import pytest
from structlog.testing import capture_logs

from core.events.principle_events import PrincipleStrengthChanged
from core.models.principle.principle_request import PrincipleCreateRequest
from core.models.type_hints import EntityUID
from core.services.principles.principle_event_handler_service import (
    PrincipleEventHandlerService,
)


@pytest.mark.asyncio
class TestPrincipleCascadeReadsRoundTrip:
    """The principle→goal / principle→habit cascade reads must resolve real edges."""

    async def _seed(self, neo4j_driver, principle: str, goal: str, habit: str) -> None:
        """Create principle + GUIDES_GOAL goal + INSPIRES_HABIT habit."""
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (p:Entity:Principle {uid: $p}) SET p.entity_type='principle', p.title='P'
                MERGE (g:Entity:Goal {uid: $g}) SET g.entity_type='goal', g.title='G'
                MERGE (h:Entity:Habit {uid: $h}) SET h.entity_type='habit', h.title='H'
                MERGE (p)-[:GUIDES_GOAL]->(g)
                MERGE (p)-[:INSPIRES_HABIT]->(h)
                """,
                p=principle,
                g=goal,
                h=habit,
            )

    async def test_cascade_keys_resolve_real_edges(self, services, neo4j_driver, clean_neo4j):
        """'guided_goals' and 'inspired_habits' resolve; the old 'habits' key is invalid."""
        p, g, h = "principle_cascade_1", "goal_cascade_1", "habit_cascade_1"
        await self._seed(neo4j_driver, p, g, h)
        rels = services.principles.relationships

        goals = await rels.get_related_uids("guided_goals", EntityUID(p))
        assert goals.is_ok and g in goals.value

        habits = await rels.get_related_uids("inspired_habits", EntityUID(p))
        assert habits.is_ok and h in habits.value

        # Negative control: the pre-fix habit key is not a valid PRINCIPLES_CONFIG
        # method, so the reader fails closed (this is why it silently returned none).
        bad = await rels.get_related_uids("habits", EntityUID(p))
        assert bad.is_error

    async def test_handler_counts_cascaded_goals_and_habits(
        self, services, neo4j_driver, clean_neo4j
    ):
        """The handler logs a non-zero cascade — the count is empty under the pre-fix reads.

        The 'Cascade impact: N entities' log only fires when total_affected > 0, so its
        presence is a true negative control: pre-fix both reads returned nothing (phantom
        goals method + invalid 'habits' key) → total 0 → the log never emitted.
        """
        # Real principle node (handler's backend.get must deserialize it) + one
        # GUIDES_GOAL goal and one INSPIRES_HABIT habit (read by UID only).
        principle = (
            await services.principles.create_principle(
                PrincipleCreateRequest(title="Integrity", statement="Act with integrity"),
                "user_cascade",
            )
        ).value
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (p:Entity {uid: $p})
                MERGE (g:Entity:Goal {uid: 'goal_cascade_2'}) SET g.entity_type='goal', g.title='G'
                MERGE (h:Entity:Habit {uid: 'habit_cascade_2'}) SET h.entity_type='habit', h.title='H'
                MERGE (p)-[:GUIDES_GOAL]->(g)
                MERGE (p)-[:INSPIRES_HABIT]->(h)
                """,
                p=principle.uid,
            )

        event = PrincipleStrengthChanged(
            principle_uid=principle.uid,
            user_uid="user_cascade",
            old_strength="aspirational",
            new_strength="core",  # elevation, so the cascade-impact branch logs
        )
        handler = PrincipleEventHandlerService(
            backend=services.principles.backend,
            relationship_service=services.principles.relationships,
        )
        with capture_logs() as logs:
            # Fire-and-forget (returns None); we assert on what it logged.
            await handler.handle_principle_strength_changed(event)

        events = " | ".join(str(entry.get("event", "")) for entry in logs)
        # 1 goal + 1 habit = 2 affected; absent entirely under the broken reads.
        assert "Cascade impact: 2 entities" in events, events
