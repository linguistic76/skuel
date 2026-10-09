"""
Entries awaiting a report reach the daily plan — the ``report`` dependency's live slot.
=======================================================================================

The daily plan (``DailyPlanningMixin.get_ready_to_work_on_today``, Priority 2.7) names the
owner's turn-ins that are out of their hands: entries on a pipeline that ``awaits_report``
(teacher review) with no ``REPORT_FOR`` yet, newest first. A reported turn-in, a journal
entry, a plain entry and another user's turn-in are not in it. ``/api/context/next-action``
carries the list through.

The learner's entries (raw-seeded: the slot is a graph predicate, not a door):

    UE_NEW       teacher_review, no report, created later      -> awaiting
    UE_OLD       teacher_review, no report, created earlier    -> awaiting
    UE_REPORTED  teacher_review, one EntryReport REPORT_FOR it -> not awaiting
    UE_JOURNAL   extract_activities, no report                 -> the owner asks for a response
    UE_PLAIN     none, no report                               -> nobody reports on it
    UE_FOREIGN   another user's teacher_review, no report      -> not the owner's

The app runs bootstrapped over its own graph (``tests/integration/_activity_link_rig.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.integration._activity_link_rig import signed_in_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzawrp"
USER = f"user_{MARK}"
OTHER = f"user_{MARK}_other"  # never signs in
UE_NEW = f"ue_{MARK}_new"
UE_OLD = f"ue_{MARK}_old"
UE_REPORTED = f"ue_{MARK}_reported"
UE_JOURNAL = f"ue_{MARK}_journal"
UE_PLAIN = f"ue_{MARK}_plain"
UE_FOREIGN = f"ue_{MARK}_foreign"
REPORT = f"er_{MARK}_report"

SEED = """
MATCH (u:User {uid: $user})
MERGE (o:User {uid: $other})
CREATE (u)-[:OWNS]->(:Entity:UserEntry {uid: $ue_new, entity_type: 'user_entry', user_uid: $user,
        pipeline: 'teacher_review', status: 'submitted', created_at: '2026-10-02T10:00:00+00:00'})
CREATE (u)-[:OWNS]->(:Entity:UserEntry {uid: $ue_old, entity_type: 'user_entry', user_uid: $user,
        pipeline: 'teacher_review', status: 'submitted', created_at: '2026-10-01T10:00:00+00:00'})
CREATE (u)-[:OWNS]->(reported:Entity:UserEntry {uid: $ue_reported, entity_type: 'user_entry',
        user_uid: $user, pipeline: 'teacher_review', status: 'completed',
        created_at: '2026-10-03T10:00:00+00:00'})
CREATE (u)-[:OWNS]->(report:Entity:EntryReport {uid: $report, entity_type: 'entry_report',
        user_uid: $user, created_at: '2026-10-04T10:00:00+00:00'})
CREATE (report)-[:REPORT_FOR]->(reported)
CREATE (u)-[:OWNS]->(:Entity:UserEntry {uid: $ue_journal, entity_type: 'user_entry', user_uid: $user,
        pipeline: 'extract_activities', status: 'completed', created_at: '2026-10-05T10:00:00+00:00'})
CREATE (u)-[:OWNS]->(:Entity:UserEntry {uid: $ue_plain, entity_type: 'user_entry', user_uid: $user,
        pipeline: 'none', status: 'completed', created_at: '2026-10-06T10:00:00+00:00'})
CREATE (o)-[:OWNS]->(:Entity:UserEntry {uid: $ue_foreign, entity_type: 'user_entry', user_uid: $other,
        pipeline: 'teacher_review', status: 'submitted', created_at: '2026-10-07T10:00:00+00:00'})
"""


class Env:
    def __init__(self, client: httpx.AsyncClient, services: Any) -> None:  # boundary: Services
        self.client = client
        self.services = services


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(
    skuel_app: Any,  # boundary: fasthtml-app
) -> AsyncIterator[Env]:
    async with signed_in_client(skuel_app, USER, MARK) as client:
        services = skuel_app.state.services
        async with services.neo4j_driver.session() as session:
            await session.run(
                SEED,
                user=USER,
                other=OTHER,
                ue_new=UE_NEW,
                ue_old=UE_OLD,
                ue_reported=UE_REPORTED,
                ue_journal=UE_JOURNAL,
                ue_plain=UE_PLAIN,
                ue_foreign=UE_FOREIGN,
                report=REPORT,
            )
        yield Env(client, services)
    # every seeded uid carries MARK: signed_in_client's exit wipe removes them, OTHER included


async def test_the_daily_plan_names_the_owners_turn_ins_with_no_report_newest_first(
    env: Env,
) -> None:
    built = await env.services.context.context_builder.build_rich(USER)
    assert built.is_ok, built
    intelligence = env.services.context_intelligence.create(built.value)
    intelligence.zpd_service = None

    plan = await intelligence.get_ready_to_work_on_today()

    assert plan.is_ok, plan
    assert plan.value.awaiting_report == (UE_NEW, UE_OLD)
    assert plan.value.estimated_time_minutes == 0
    assert "2 entries awaiting a report" in plan.value.rationale.split("; ")


async def test_next_action_carries_the_entries_awaiting_a_report(env: Env) -> None:
    response = await env.client.get("/api/context/next-action")

    assert response.status_code == 200, response.text
    assert response.json()["awaiting_report"] == [UE_NEW, UE_OLD]
