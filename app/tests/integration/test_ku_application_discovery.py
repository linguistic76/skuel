"""The knowledge end of an application read is an ``:Entity``: a Ku uid is answered, not refused.

``PsApplicationDiscoveryService`` holds the PathStep backend, and the hub's method 1 hands
it Ku uids (its ZPD and vector sources). The reads match the knowledge end by uid as an
``:Entity`` — a Ku or a PathStep — and verify nothing first: a habit reinforcing a Ku is
found by the Ku's uid, and an unknown uid is an empty answer.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.activity_backends import HabitsBackend
from adapters.persistence.neo4j.backends.curriculum_backends import KuBackend, PsBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.habit.habit import Habit
from core.models.ku.ku import Ku
from core.models.pathways.path_step import PathStep
from core.models.relationship_names import RelationshipName
from core.services.ps.ps_application_discovery_service import PsApplicationDiscoveryService

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

USER = "user_ku_application_discovery"
KU = "ku.test.application-discovery"
HABIT = "habit.test.reinforces-the-ku"


@pytest_asyncio.fixture
async def discovery(neo4j_driver, clean_neo4j) -> PsApplicationDiscoveryService:
    ps_backend = PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    return PsApplicationDiscoveryService(repo=ps_backend)


async def test_a_habit_reinforcing_a_ku_is_found_by_the_ku_uid(neo4j_driver, discovery) -> None:
    kus = KuBackend(neo4j_driver, NeoLabel.KU, Ku, base_label=NeoLabel.ENTITY)
    ku = await kus.create(Ku(uid=KU, title="Discovery anchor"))
    assert ku.is_ok, ku
    habits = HabitsBackend(neo4j_driver, NeoLabel.HABIT, Habit, base_label=NeoLabel.ENTITY)
    habit = await habits.create(Habit(uid=HABIT, user_uid=USER, title="Reinforce the Ku"))
    assert habit.is_ok, habit
    linked = await habits.create_relationships_batch(
        [(HABIT, KU, RelationshipName.REINFORCES_KNOWLEDGE.value, None)]
    )
    assert linked.is_ok, linked

    found = await discovery.find_habits_reinforcing_knowledge(KU, USER, only_active=False)

    assert found.is_ok, found
    assert found.value == [HABIT]


async def test_an_unknown_uid_is_an_empty_answer(discovery) -> None:
    unknown = await discovery.find_events_applying_knowledge("ku.test.nowhere", USER)

    assert unknown.is_ok, unknown
    assert unknown.value == []
