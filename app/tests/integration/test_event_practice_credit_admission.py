"""An event's knowledge credit names only knowledge the caller may read.

``EventsService.create_event_with_context`` takes ``practices_knowledge_uids`` from the
request and announces one ``KnowledgePracticedInEvent`` per uid; the substance counter
(``times_practiced_in_events``) lands on the node each names. The uids are admitted
before the event is written, by the rule an entry's knowledge references follow: a
published Ku or PathStep. A draft Ku, another user's Task, a uid that names nothing
are each dropped from the credit — no event, no counter — while the event itself is
still created and the admitted uids are still credited.

The app runs bootstrapped over its own graph (``tests/integration/_activity_link_rig.py``);
the other user's Task is made at the real create door.
"""

from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.events.knowledge_substance_events import KnowledgePracticedInEvent
from core.models.event.event import Event
from core.models.event.event_request import EventCreateRequest
from core.utils.result_simplified import Result
from tests.integration._activity_link_rig import create, published, signed_in_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzpractcredit"
# One mark per signed-in client: each client's exit wipes every uid carrying its mark.
LEARNER_MARK = f"{MARK}l"
OTHER_MARK = f"{MARK}o"
LEARNER = f"user_{LEARNER_MARK}"
OTHER = f"user_{OTHER_MARK}"
KU_PUBLISHED = f"ku.{LEARNER_MARK}.published"
KU_DRAFT = f"ku.{LEARNER_MARK}.draft"
PS_PUBLISHED = f"ps.{LEARNER_MARK}.published"
MISSING = f"ku.{LEARNER_MARK}.missing"


async def _seed(driver: AsyncDriver) -> None:
    # The published Ku carries no publication_state — the NULL-tolerant case the
    # predicate must keep; the draft is marked 'draft', the property it reads.
    async with driver.session() as session:
        for uid, label, entity_type, state in (
            (KU_PUBLISHED, "Ku", "ku", None),
            (KU_DRAFT, "Ku", "ku", "draft"),
            (PS_PUBLISHED, "PathStep", "path_step", "published"),
        ):
            await session.run(
                f"""
                CREATE (n:Entity:{label} {{uid: $uid, entity_type: $entity_type, title: $uid,
                                          status: 'active'}})
                SET n.publication_state = $state
                """,
                uid=uid,
                entity_type=entity_type,
                state=state,
            )


async def _practice_count(driver: AsyncDriver, uid: str) -> int:
    async with driver.session() as session:
        record = await (
            await session.run(
                "MATCH (n:Entity {uid: $uid}) RETURN coalesce(n.times_practiced_in_events, 0) AS n",
                uid=uid,
            )
        ).single()
    assert record is not None, uid
    return int(record["n"])


class World:
    def __init__(
        self, services: Any, driver: AsyncDriver, other_task: str
    ) -> None:  # boundary: composed Services container
        self.services = services
        self.driver = driver
        self.other_task = other_task

    async def create_event(self, knowledge_uids: list[str]) -> tuple[Result[Event], list[str]]:
        """Create the learner's event; returns the result and the uids credited."""
        request = EventCreateRequest(
            title=f"{MARK} practice",
            event_date=date(2026, 10, 10),
            start_time=time(9, 0),
            end_time=time(10, 0),
            practices_knowledge_uids=knowledge_uids,
        )
        context = SimpleNamespace(user_uid=LEARNER, active_habit_uids=set())
        with published(self.services.event_bus, KnowledgePracticedInEvent) as seen:
            result = await self.services.events.create_event_with_context(request, context)
        return result, [event.knowledge_uid for event in seen]


@pytest_asyncio.fixture(loop_scope="session")
async def world(skuel_app: Any) -> AsyncIterator[World]:  # boundary: fasthtml-app
    services = skuel_app.state.services
    driver: AsyncDriver = services.neo4j_driver
    async with (
        signed_in_client(skuel_app, LEARNER, LEARNER_MARK),
        signed_in_client(skuel_app, OTHER, OTHER_MARK) as other,
    ):
        await _seed(driver)
        other_task = await create(other, "tasks", f"{MARK}-other-task")
        yield World(services, driver, other_task)


async def test_published_knowledge_is_credited(world: World) -> None:
    """Positive control: a published Ku and a published PathStep are each credited once,
    and the counter lands on the Ku."""
    before = await _practice_count(world.driver, KU_PUBLISHED)

    result, credited = await world.create_event([KU_PUBLISHED, PS_PUBLISHED, KU_PUBLISHED])

    assert result.is_ok, result
    assert credited == [KU_PUBLISHED, PS_PUBLISHED]
    assert await _practice_count(world.driver, KU_PUBLISHED) == before + 1


async def test_anything_else_is_dropped_from_the_credit_and_the_event_still_lands(
    world: World,
) -> None:
    """A draft Ku, another user's Task and a uid that names nothing earn no credit;
    the published Ku beside them still does, and the event is created."""
    before = await _practice_count(world.driver, KU_DRAFT)

    result, credited = await world.create_event([KU_DRAFT, world.other_task, MISSING, KU_PUBLISHED])

    assert result.is_ok, result
    assert credited == [KU_PUBLISHED]
    assert await _practice_count(world.driver, KU_DRAFT) == before
