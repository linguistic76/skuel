"""A PathStep-spawned event starts ``scheduled``, and the ``scheduled`` readers see it.

An engagement spawns only ACTIVE templates. The event it spawns takes its own default
status, ``scheduled``, as an event the learner creates does: for an event ``active``
means under way. Held here over the bootstrapped app: a real engagement over a step
whose templates are a habit and an event that reinforces it spawns a ``scheduled``
event, and the habit integration's at-risk read (``status_filter="scheduled"``) finds
it, by the graph read and by the rich context alike. Control: the same event set
``active`` is out of both.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums.entity_enums import EntityStatus
from core.models.pathways.path_step import PathStep
from core.models.relationship_names import RelationshipName
from core.models.templates.event_template import EventTemplate
from core.models.templates.habit_template import HabitTemplate
from core.models.templates.relative_offset import RelativeOffset
from core.models.type_hints import UserUID
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import signed_in_client, write_edge

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from adapters.inbound.fasthtml_types import FastHTMLApp

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzspawnedevent"
LEARNER = seed_user_uid(MARK)


async def test_a_spawned_event_is_scheduled_and_the_habit_at_risk_read_sees_it(
    skuel_app: FastHTMLApp,
) -> None:
    services = skuel_app.state.services
    driver: AsyncDriver = services.neo4j_driver
    ps_uid = f"ps.{MARK}-step"
    habit_tpl, event_tpl = f"ht.{MARK}-practice", f"et.{MARK}-session"

    async with signed_in_client(skuel_app, LEARNER, MARK):
        backends = build_production_backends(driver)
        step = PathStep(uid=ps_uid, title=f"{MARK} step")
        assert (await backends["ps_backend"].create(step)).is_ok
        habit = HabitTemplate(uid=habit_tpl, title=f"{MARK} practice", status=EntityStatus.ACTIVE)
        event = EventTemplate(
            uid=event_tpl,
            title=f"{MARK} practice session",
            status=EntityStatus.ACTIVE,  # an engagement spawns only ACTIVE templates
            event_offset=RelativeOffset(days=1),
            reinforces_habit_template_uid=habit_tpl,
        )
        assert (await backends["habit_template_backend"].create(habit)).is_ok
        assert (await backends["event_template_backend"].create(event)).is_ok
        await write_edge(driver, ps_uid, RelationshipName.HAS_HABIT_TEMPLATE.value, habit_tpl)
        await write_edge(driver, ps_uid, RelationshipName.HAS_EVENT_TEMPLATE.value, event_tpl)

        engaged = await services.ps_engagement.engage_pathstep(LEARNER, ps_uid)
        assert engaged.is_ok, engaged.expect_error().message

        spawned = await _spawned_event(driver, event_tpl)
        assert spawned["status"] == EntityStatus.SCHEDULED.value
        assert await _at_risk_event_uids(skuel_app, spawned["uid"]) == (
            {spawned["uid"]},
            {spawned["uid"]},
        )

        async with driver.session() as session:
            await session.run(
                "MATCH (e:Event {uid: $uid}) SET e.status = $active",
                uid=spawned["uid"],
                active=EntityStatus.ACTIVE.value,
            )
        assert await _at_risk_event_uids(skuel_app, spawned["uid"]) == (set(), set()), (
            "the at-risk read keys on scheduled, so an active spawn would be invisible to it"
        )


async def _spawned_event(driver: AsyncDriver, template_uid: str) -> dict[str, str]:
    async with driver.session() as session:
        record = await (
            await session.run(
                "MATCH (e:Event {user_uid: $user})-[:SPAWNED_FROM]->({uid: $tpl}) "
                "RETURN e.uid AS uid, e.status AS status",
                user=LEARNER,
                tpl=template_uid,
            )
        ).single()
    assert record is not None, "the engagement spawned no event"
    return {"uid": str(record["uid"]), "status": str(record["status"])}


async def _at_risk_event_uids(skuel_app: FastHTMLApp, event_uid: str) -> tuple[set[str], set[str]]:
    """The at-risk read's events, over the standard context (the graph read) and the rich
    one, which holds ``event_uid`` among its own events (the context read)."""
    builder = skuel_app.state.services.user.context_builder
    events = skuel_app.state.services.events
    standard = await builder.build(UserUID(LEARNER))
    rich = await builder.build_rich(UserUID(LEARNER))
    assert standard.is_ok, standard.expect_error().message
    assert rich.is_ok, rich.expect_error().message
    held = {item["entity"].get("uid") for item in rich.value.entities_rich.get("events", [])}
    assert event_uid in held, "the rich context does not hold the event, so its read is untested"
    by_graph = await events.get_at_risk_habit_events(standard.value)
    by_context = await events.get_at_risk_habit_events(rich.value)
    assert by_graph.is_ok, by_graph.expect_error().message
    assert by_context.is_ok, by_context.expect_error().message
    return {e.uid for e in by_graph.value}, {e.uid for e in by_context.value}
