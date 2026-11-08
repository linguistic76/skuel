"""The choice page's three doors over the bootstrapped app: add an option, remove one, decide.

Each door verifies the owner at the route, reads JSON or the page's form through
``parse_body``, and writes from the choice as it stands under its lock
(``ChoicesBackend.rewrite_choice_under_lock``). Held here against the app's own graph:

- an option added on the page is stored exactly as one the JSON create door wrote, and
  the decision can select it;
- the decision writes its fields, and ``ChoiceMade`` reaches its subscribers: the
  decision-pattern handler (its insight), and the PathStep engagement's auto-complete,
  which closes an engagement whose one activity is a spawned choice once it is decided;
- another user's choice is not found, a foreign option and a second decision are refused,
  and each refusal leaves the node as it was;
- two writes racing on one choice serialize: neither loses the other's option, and an
  option write never undoes a decision;
- the page's controls drive their own ``hx-post``.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.events import ChoiceMade
from core.models.choice.choice_option import ChoiceOption
from core.models.choice.choice_request import ChoiceCreateRequest, ChoiceOptionRequest
from core.models.enums.entity_enums import EntityStatus
from core.models.pathways.path_step import PathStep
from core.models.relationship_names import RelationshipName
from core.models.templates.choice_template import ChoiceTemplate
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import (
    create,
    published,
    signed_in_client,
    wipe,
    write_edge,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx
    from neo4j import AsyncDriver

    from adapters.inbound.fasthtml_types import FastHTMLApp

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzchoicedecide"
CALLER = seed_user_uid(MARK)
STRANGER = seed_user_uid(f"{MARK}-stranger")
HTMX = {"HX-Request": "true"}


@dataclass(frozen=True)
class Env:
    client: httpx.AsyncClient
    services: Any  # boundary: the composed Services container
    driver: AsyncDriver


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def env(skuel_app: FastHTMLApp) -> AsyncIterator[Env]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with signed_in_client(skuel_app, CALLER, MARK) as client:
        yield Env(client=client, services=skuel_app.state.services, driver=driver)
    await wipe(driver, STRANGER, MARK)


# ---------------------------------------------------------------------------
# Seeds and reads
# ---------------------------------------------------------------------------


async def _choice(env: Env, title: str, *options: str) -> str:
    """A choice made at the JSON create door, with ``options`` (none, or two or more)."""
    return await create(
        env.client,
        "choices",
        f"{MARK} {title}",
        options=[{"title": option, "description": f"{option} description"} for option in options],
    )


async def _node(env: Env, uid: str) -> dict[str, Any]:  # boundary: raw node properties
    async with env.driver.session() as session:
        record = await (
            await session.run("MATCH (c:Choice {uid: $uid}) RETURN properties(c) AS p", uid=uid)
        ).single()
    assert record is not None, uid
    return dict(record["p"])


async def _stored_options(env: Env, uid: str) -> list[dict[str, Any]]:  # boundary: JSON rows
    raw = (await _node(env, uid))["options"]
    assert isinstance(raw, str), f"options are stored as a JSON string, got {type(raw)}"
    rows = json.loads(raw)
    assert isinstance(rows, list)
    return rows


def _option_uid(options: list[dict[str, Any]], title: str) -> str:  # boundary: JSON rows
    return next(str(row["uid"]) for row in options if row["title"] == title)


def _without_stamp(node: dict[str, Any]) -> dict[str, Any]:  # boundary: raw node properties
    return {key: value for key, value in node.items() if key != "updated_at"}


# ---------------------------------------------------------------------------
# One builder: a page-added option is stored like a created one
# ---------------------------------------------------------------------------


async def test_an_option_added_on_the_page_is_stored_like_one_the_create_door_wrote(
    env: Env,
) -> None:
    uid = await _choice(env, "shape", "Morning", "Noon")

    # The page's add form: url-encoded, a blank description posted as "".
    added = await env.client.post(
        f"/api/choices/{uid}/options",
        data={"title": "Evening", "description": "Evening description"},
        headers=HTMX,
    )

    assert added.status_code == 200, added.text
    created, _noon, page_added = await _stored_options(env, uid)
    assert page_added["title"] == "Evening"
    assert set(page_added) == set(created)
    assert {k: v for k, v in page_added.items() if k not in ("uid", "title", "description")} == {
        k: v for k, v in created.items() if k not in ("uid", "title", "description")
    }
    assert str(page_added["uid"]).startswith("option_")
    assert str(created["uid"]).startswith("option_")

    blank = await env.client.post(
        f"/api/choices/{uid}/options", data={"title": "Night", "description": ""}, headers=HTMX
    )
    assert blank.status_code == 200, blank.text
    assert (await _stored_options(env, uid))[-1]["description"] == ""


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------


async def test_the_decision_selects_a_page_added_option_and_writes_its_fields(env: Env) -> None:
    uid = await _choice(env, "decide", "Morning", "Noon")
    added = await env.client.post(f"/api/choices/{uid}/options", data={"title": "Evening"})
    assert added.status_code == 200, added.text
    evening = _option_uid(await _stored_options(env, uid), "Evening")

    with published(env.services.event_bus, ChoiceMade) as made:
        decided = await env.client.post(
            f"/api/choices/{uid}/decide",
            json={
                "selected_option_uid": evening,
                "decision_rationale": "the house is quiet",
                "confidence": 0.9,
            },
        )

    assert decided.status_code == 200, decided.text
    assert decided.json()["selected_option_uid"] == evening
    node = await _node(env, uid)
    assert node["selected_option_uid"] == evening
    assert node["decision_rationale"] == "the house is quiet"
    assert node["status"] == "active"
    assert isinstance(datetime.fromisoformat(str(node["decided_at"])), datetime)
    assert "confidence" not in node, "confidence rides on the event, not the node"
    assert [(e.choice_uid, e.selected_option, e.confidence) for e in made] == [(uid, evening, 0.9)]


async def test_choice_made_reaches_the_decision_pattern_handler(env: Env) -> None:
    """A high-confidence decision a principle informs earns the handler's insight."""
    principle = await create(env.client, "principles", f"{MARK} principle")
    uid = await _choice(env, "aligned", "Walk", "Drive")
    linked = await env.client.post(
        "/api/choices/link-principle", json={"choice_uid": uid, "principle_uid": principle}
    )
    assert linked.status_code == 200, linked.text
    walk = _option_uid(await _stored_options(env, uid), "Walk")

    decided = await env.client.post(
        f"/api/choices/{uid}/decide", json={"selected_option_uid": walk, "confidence": 0.9}
    )

    assert decided.status_code == 200, decided.text
    async with env.driver.session() as session:
        rows = await (
            await session.run(
                "MATCH (i:Insight {user_uid: $user, entity_uid: $uid}) RETURN i.insight_type AS t",
                user=CALLER,
                uid=uid,
            )
        ).data()
    assert [row["t"] for row in rows] == ["decision_pattern"]


async def test_deciding_a_spawned_choice_completes_its_engagement(env: Env) -> None:
    """A PathStep whose one activity is a choice: the decision closes the engagement.

    The choice is spawned by a real engagement from a template carrying options and a
    rationale, as the content vault's choice templates can. It starts an undecided draft
    without the template's rationale, as a choice the learner creates does, so its
    options are open: it takes one more before the decision. The engagement counts a
    decided choice as done.
    """
    ps_uid, template_uid = f"ps.{MARK}-step", f"ct.{MARK}-when"
    backends = build_production_backends(env.driver)
    assert (await backends["ps_backend"].create(PathStep(uid=ps_uid, title=f"{MARK} step"))).is_ok
    template = ChoiceTemplate(
        uid=template_uid,
        title=f"{MARK} when will you practise",
        status=EntityStatus.ACTIVE,  # an engagement spawns only ACTIVE templates
        decision_rationale="the template's reasoning",
        options=(
            ChoiceOption(uid="opt.morning", title="First thing"),
            ChoiceOption(uid="opt.evening", title="Before bed"),
        ),
    )
    assert (await backends["choice_template_backend"].create(template)).is_ok
    await write_edge(env.driver, ps_uid, RelationshipName.HAS_CHOICE_TEMPLATE.value, template_uid)
    engaged = await env.services.ps_engagement.engage_pathstep(CALLER, ps_uid)
    assert engaged.is_ok, engaged.expect_error().message
    async with env.driver.session() as session:
        record = await (
            await session.run(
                "MATCH (c:Choice {user_uid: $user})-[:SPAWNED_FROM]->({uid: $tpl}) "
                "RETURN c.uid AS uid",
                user=CALLER,
                tpl=template_uid,
            )
        ).single()
    assert record is not None
    spawned = str(record["uid"])
    assert [row["uid"] for row in await _stored_options(env, spawned)] == [
        "opt.morning",
        "opt.evening",
    ]
    assert await _engagement_state(env, ps_uid) == "engaged"
    node = await _node(env, spawned)
    assert node["status"] == "draft"
    assert "decision_rationale" not in node, "the template's rationale is not the learner's"

    added = await env.client.post(f"/api/choices/{spawned}/options", json={"title": "At lunch"})
    assert added.status_code == 200, added.text
    lunch = _option_uid(await _stored_options(env, spawned), "At lunch")
    assert await _engagement_state(env, ps_uid) == "engaged", "an added option decides nothing"

    decided = await env.client.post(
        f"/api/choices/{spawned}/decide", json={"selected_option_uid": lunch}
    )

    assert decided.status_code == 200, decided.text
    assert (await _node(env, spawned))["status"] == "active"
    assert await _engagement_state(env, ps_uid) == "completed"


async def _engagement_state(env: Env, ps_uid: str) -> str | None:
    async with env.driver.session() as session:
        record = await (
            await session.run(
                "MATCH (:User {uid: $user})-[e:ENGAGED_WITH]->({uid: $ps}) RETURN e.state AS s",
                user=CALLER,
                ps=ps_uid,
            )
        ).single()
    return None if record is None else str(record["s"])


# ---------------------------------------------------------------------------
# Refusals leave the choice as it was
# ---------------------------------------------------------------------------


async def test_another_users_choice_is_not_found_at_every_door(env: Env) -> None:
    async with env.driver.session() as session:
        await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=STRANGER)
    created = await env.services.choices.create_choice(
        ChoiceCreateRequest(
            title=f"{MARK} not yours",
            description="theirs",
            options=[ChoiceOptionRequest(title="A"), ChoiceOptionRequest(title="B")],
        ),
        STRANGER,
    )
    assert created.is_ok, created
    theirs = created.value
    before = _without_stamp(await _node(env, theirs.uid))
    option = theirs.options[0].uid

    answers = [
        await env.client.post(f"/api/choices/{theirs.uid}/options", json={"title": "Mine now"}),
        await env.client.post(f"/api/choices/{theirs.uid}/options/{option}/remove"),
        await env.client.post(
            f"/api/choices/{theirs.uid}/decide", json={"selected_option_uid": option}
        ),
    ]

    assert [answer.status_code for answer in answers] == [404, 404, 404]
    assert _without_stamp(await _node(env, theirs.uid)) == before


async def test_a_foreign_option_and_a_second_decision_are_refused(env: Env) -> None:
    uid = await _choice(env, "refusals", "Stay", "Go")
    other = await _choice(env, "other", "Up", "Down")
    foreign = _option_uid(await _stored_options(env, other), "Up")
    before = _without_stamp(await _node(env, uid))

    refused = await env.client.post(
        f"/api/choices/{uid}/decide", json={"selected_option_uid": foreign}
    )

    assert refused.status_code == 400, refused.text
    assert _without_stamp(await _node(env, uid)) == before

    stay = _option_uid(await _stored_options(env, uid), "Stay")
    go = _option_uid(await _stored_options(env, uid), "Go")
    assert (
        await env.client.post(f"/api/choices/{uid}/decide", json={"selected_option_uid": stay})
    ).status_code == 200
    decided = _without_stamp(await _node(env, uid))

    with published(env.services.event_bus, ChoiceMade) as made:
        again = await env.client.post(
            f"/api/choices/{uid}/decide", json={"selected_option_uid": go}
        )
        late_add = await env.client.post(f"/api/choices/{uid}/options", json={"title": "Wait"})
        late_remove = await env.client.post(f"/api/choices/{uid}/options/{go}/remove")

    assert [again.status_code, late_add.status_code, late_remove.status_code] == [400, 400, 400]
    assert "already decided" in again.text
    assert _without_stamp(await _node(env, uid)) == decided
    assert made == []


async def test_removing_keeps_two_options_and_names_a_missing_one_not_found(env: Env) -> None:
    uid = await _choice(env, "remove", "One", "Two", "Three")
    two = _option_uid(await _stored_options(env, uid), "Two")

    removed = await env.client.post(f"/api/choices/{uid}/options/{two}/remove")
    floor = await env.client.post(
        f"/api/choices/{uid}/options/{_option_uid(await _stored_options(env, uid), 'One')}/remove"
    )
    missing = await env.client.post(f"/api/choices/{uid}/options/{two}/remove")

    assert removed.status_code == 200, removed.text
    assert [row["title"] for row in await _stored_options(env, uid)] == ["One", "Three"]
    assert floor.status_code == 400, floor.text
    assert missing.status_code == 404, missing.text


# ---------------------------------------------------------------------------
# The lock: racing writes on one choice serialize
# ---------------------------------------------------------------------------


async def test_two_options_added_at_once_are_both_kept(env: Env) -> None:
    uid = await _choice(env, "race-add")

    answers = await asyncio.gather(
        *[
            env.client.post(f"/api/choices/{uid}/options", json={"title": f"Option {n}"})
            for n in range(4)
        ]
    )

    assert [answer.status_code for answer in answers] == [200] * 4
    assert sorted(row["title"] for row in await _stored_options(env, uid)) == [
        f"Option {n}" for n in range(4)
    ]


async def test_an_option_write_racing_a_decision_never_undoes_it(env: Env) -> None:
    """Whichever lands first, the choice ends decided: an add that loses the race is
    refused, and one that wins is kept beside the decision."""
    for round_ in range(4):
        uid = await _choice(env, f"race-decide-{round_}", "Left", "Right")
        left = _option_uid(await _stored_options(env, uid), "Left")

        decide, add = await asyncio.gather(
            env.client.post(f"/api/choices/{uid}/decide", json={"selected_option_uid": left}),
            env.client.post(f"/api/choices/{uid}/options", json={"title": "Middle"}),
        )

        assert decide.status_code == 200, decide.text
        assert add.status_code in (200, 400), add.text
        node = await _node(env, uid)
        assert node["status"] == "active"
        assert node["selected_option_uid"] == left
        titles = [row["title"] for row in await _stored_options(env, uid)]
        assert titles == (
            ["Left", "Right", "Middle"] if add.status_code == 200 else ["Left", "Right"]
        )


# ---------------------------------------------------------------------------
# The page drives its own hx-post
# ---------------------------------------------------------------------------


def _attribute(tag: str, name: str) -> str:
    match = re.search(rf'{name}="([^"]*)"', tag)
    assert match is not None, (name, tag)
    return match.group(1)


def _tag(html: str, marker: str) -> str:
    match = re.search(rf"<(?:form|button)[^>]*{marker}[^>]*>", html)
    assert match is not None, marker
    return match.group(0)


async def test_the_page_controls_post_to_their_own_doors(env: Env) -> None:
    uid = await _choice(env, "page")
    shell = await env.client.get(f"/choices/detail?uid={uid}")
    assert shell.status_code == 200
    content = re.search(r'hx-get="(/choices/detail/content\?uid=[^"]*)"', shell.text)
    assert content is not None, "the detail shell loads its body over HTMX"
    page = await env.client.get(content.group(1), headers=HTMX)
    assert page.status_code == 200
    add_form = _tag(page.text, "data-choice-add-option")
    assert "data-choice-decide" not in page.text, "no decide form before two options"
    target = _attribute(add_form, "hx-target")
    assert target == f"#choice-detail-{uid}"
    assert f'id="choice-detail-{uid}"' in page.text

    for title in ("Tea", "Coffee", "Water"):
        swapped = await env.client.post(
            _attribute(add_form, "hx-post"), data={"title": title, "description": ""}, headers=HTMX
        )
        assert swapped.status_code == 200, swapped.text
        add_form = _tag(swapped.text, "data-choice-add-option")
    assert f'id="choice-detail-{uid}"' in swapped.text

    water = _option_uid(await _stored_options(env, uid), "Water")
    remove = _tag(swapped.text, f'data-choice-option-remove="{water}"')
    after_remove = await env.client.post(_attribute(remove, "hx-post"), headers=HTMX)
    assert after_remove.status_code == 200, after_remove.text
    assert [row["title"] for row in await _stored_options(env, uid)] == ["Tea", "Coffee"]
    assert "data-choice-option-remove" not in after_remove.text, "two options stay two"

    decide_form = _tag(after_remove.text, "data-choice-decide")
    coffee = _option_uid(await _stored_options(env, uid), "Coffee")
    decided = await env.client.post(
        _attribute(decide_form, "hx-post"),
        data={"selected_option_uid": coffee, "decision_rationale": "", "confidence": "0.7"},
        headers=HTMX,
    )

    assert decided.status_code == 200, decided.text
    assert "(selected)" in decided.text
    assert "data-choice-decide" not in decided.text
    assert "data-choice-add-option" not in decided.text
    node = await _node(env, uid)
    assert node["selected_option_uid"] == coffee
    assert "decision_rationale" not in node, "a blank rationale is no rationale"
