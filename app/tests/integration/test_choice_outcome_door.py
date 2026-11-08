"""Closing a decided choice and recording how it turned out, over the bootstrapped app.

A decided choice closes from its card (``POST /api/choices/{uid}/status``) and reopens
active, never draft; how it turned out is recorded on its page
(``POST /api/choices/{uid}/outcome``), open or closed, and updated later. Both writes are
planned from the choice under its lock. Held here against the app's own graph:

- the card's own ``hx-post`` closes a decided choice, stamps it, and reopens it with the
  stamp cleared; a decided choice sent to draft is refused and unchanged;
- the page's outcome form records the outcome, the page shows it, and the same form,
  filled in, replaces it; ``ChoiceOutcomeRecorded`` reaches its handler;
- an outcome racing a close leaves both;
- an outcome on a choice not yet decided is refused, and another user's choice is not
  found.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.events import ChoiceOutcomeRecorded
from core.models.choice.choice_request import ChoiceCreateRequest, ChoiceOptionRequest
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import create, published, signed_in_client, wipe

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

MARK = "zzzchoiceoutcome"
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


async def _node(env: Env, uid: str) -> dict[str, Any]:  # boundary: raw node properties
    async with env.driver.session() as session:
        record = await (
            await session.run("MATCH (c:Choice {uid: $uid}) RETURN properties(c) AS p", uid=uid)
        ).single()
    assert record is not None, uid
    return dict(record["p"])


def _without_stamp(node: dict[str, Any]) -> dict[str, Any]:  # boundary: raw node properties
    return {key: value for key, value in node.items() if key != "updated_at"}


async def _decided_choice(env: Env, title: str) -> str:
    """A choice with two options, decided at its door."""
    uid = await create(
        env.client,
        "choices",
        f"{MARK} {title}",
        options=[{"title": "Mornings"}, {"title": "Evenings"}],
    )
    options = json.loads(str((await _node(env, uid))["options"]))
    decided = await env.client.post(
        f"/api/choices/{uid}/decide", json={"selected_option_uid": options[0]["uid"]}
    )
    assert decided.status_code == 200, decided.text
    return uid


def _attribute(tag: str, name: str) -> str:
    match = re.search(rf"{name}=(['\"])(.*?)\1", tag)
    assert match is not None, (name, tag)
    return match.group(2)


def _card_button(html: str, uid: str) -> str:
    card = re.search(
        rf'<div id="choice-{uid}".*?<button[^>]*data-choice-status[^>]*>', html, re.DOTALL
    )
    assert card is not None, f"no card with a status control for {uid}"
    button = re.search(r"<button[^>]*data-choice-status[^>]*>", card.group(0))
    assert button is not None
    return button.group(0)


async def _press(env: Env, button: str) -> httpx.Response:
    """Post a card's control as htmx would: its ``hx-post`` with its ``hx-vals``."""
    return await env.client.post(
        _attribute(button, "hx-post"),
        data=json.loads(_attribute(button, "hx-vals")),
        headers=HTMX,
    )


async def _page(env: Env, uid: str) -> str:
    """The choice page as a learner gets it: the shell, then the content it loads."""
    shell = await env.client.get(f"/choices/detail?uid={uid}")
    assert shell.status_code == 200
    content = re.search(r'hx-get="(/choices/detail/content\?uid=[^"]*)"', shell.text)
    assert content is not None, "the detail shell loads its body over HTMX"
    page = await env.client.get(content.group(1), headers=HTMX)
    assert page.status_code == 200
    return page.text


def _outcome_form(html: str) -> str:
    match = re.search(r"<form[^>]*data-choice-outcome[^>]*>", html)
    assert match is not None, "no outcome form"
    return match.group(0)


# ---------------------------------------------------------------------------
# Closing and reopening from the card
# ---------------------------------------------------------------------------


async def test_a_decided_choice_closes_from_its_card_and_reopens_active(env: Env) -> None:
    uid = await _decided_choice(env, "close")
    decided = await _node(env, uid)
    listing = await env.client.get("/choices/content?status=decided", headers=HTMX)
    assert listing.status_code == 200

    closed = await _press(env, _card_button(listing.text, uid))

    assert closed.status_code == 200, closed.text
    node = await _node(env, uid)
    assert node["status"] == "completed"
    assert node["completed_at"]
    for field in ("decided_at", "selected_option_uid", "options", "choice_type"):
        assert node[field] == decided[field], f"closing kept the decision's {field}"
    reopen = _card_button(closed.text, uid)
    assert 'data-choice-status="active"' in reopen

    reopened = await _press(env, reopen)

    assert reopened.status_code == 200, reopened.text
    node = await _node(env, uid)
    assert node["status"] == "active"
    assert "completed_at" not in node, "reopening clears the completion stamp"
    assert node["decided_at"] == decided["decided_at"]


async def test_a_decided_choice_sent_to_draft_is_refused(env: Env) -> None:
    uid = await _decided_choice(env, "draft")
    archived = await env.client.post(
        f"/api/choices/{uid}/status", data={"status": "archived"}, headers=HTMX
    )
    assert archived.status_code == 200, archived.text
    assert (await _node(env, uid))["status"] == "archived"
    before = _without_stamp(await _node(env, uid))

    refused = await env.client.post(
        f"/api/choices/{uid}/status", data={"status": "draft"}, headers=HTMX
    )

    assert "cannot go back to draft" in refused.text
    assert _without_stamp(await _node(env, uid)) == before


# ---------------------------------------------------------------------------
# The outcome, from the page's form
# ---------------------------------------------------------------------------


async def test_an_outcome_is_recorded_from_the_page_shown_and_replaced(env: Env) -> None:
    uid = await _decided_choice(env, "outcome")
    page = await _page(env, uid)
    assert "How did it turn out?" in page
    form = _outcome_form(page)
    assert _attribute(form, "hx-target") == f"#choice-detail-{uid}"

    with published(env.services.event_bus, ChoiceOutcomeRecorded) as recorded:
        swapped = await env.client.post(
            _attribute(form, "hx-post"),
            data={
                "satisfaction_score": "4",
                "actual_outcome": "I kept to it most weeks",
                "lessons_learned": "Start small\n\n  Keep a log  \n",
            },
            headers=HTMX,
        )

    assert swapped.status_code == 200, swapped.text
    assert f'id="choice-detail-{uid}"' in swapped.text
    assert "I kept to it most weeks" in swapped.text
    assert "Update the outcome" in swapped.text
    node = await _node(env, uid)
    assert node["satisfaction_score"] == 4
    assert node["actual_outcome"] == "I kept to it most weeks"
    assert node["lessons_learned"] == ["Start small", "Keep a log"]
    assert node["status"] == "active", "the outcome writes no status"
    assert [(e.choice_uid, e.outcome_quality, e.lessons_learned) for e in recorded] == [
        (uid, 0.75, "Start small\nKeep a log")
    ]

    updated = await env.client.post(
        _attribute(_outcome_form(swapped.text), "hx-post"),
        data={"satisfaction_score": "2", "actual_outcome": "It slipped", "lessons_learned": ""},
        headers=HTMX,
    )

    assert updated.status_code == 200, updated.text
    node = await _node(env, uid)
    assert node["satisfaction_score"] == 2
    assert node["actual_outcome"] == "It slipped"
    assert node["lessons_learned"] == []


async def test_a_closed_choice_takes_an_outcome(env: Env) -> None:
    uid = await _decided_choice(env, "closed-outcome")
    closed = await env.client.post(
        f"/api/choices/{uid}/status", data={"status": "completed"}, headers=HTMX
    )
    assert closed.status_code == 200, closed.text

    recorded = await env.client.post(
        f"/api/choices/{uid}/outcome",
        json={"satisfaction_score": 5, "actual_outcome": "Worth it", "lessons_learned": []},
    )

    assert recorded.status_code == 200, recorded.text
    node = await _node(env, uid)
    assert node["status"] == "completed"
    assert node["satisfaction_score"] == 5


async def test_choice_outcome_recorded_reaches_its_handler(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A principle-aligned choice that turned out well earns the positive correlation."""
    principle = await create(env.client, "principles", f"{MARK} principle")
    uid = await _decided_choice(env, "aligned")
    linked = await env.client.post(
        "/api/choices/link-principle", json={"choice_uid": uid, "principle_uid": principle}
    )
    assert linked.status_code == 200, linked.text
    logger = MagicMock()
    monkeypatch.setattr(env.services.choices.event_handler, "logger", logger)

    recorded = await env.client.post(
        f"/api/choices/{uid}/outcome",
        json={"satisfaction_score": 5, "actual_outcome": "It held"},
    )

    assert recorded.status_code == 200, recorded.text
    logged = [call.kwargs["extra"] for call in logger.info.call_args_list]
    assert [(row["event_type"], row.get("choice_uid")) for row in logged] == [
        ("choice.outcome.analyzed", uid),
        ("choice.principle_correlation.positive", uid),
    ]
    assert logged[0]["quality_category"] == "excellent"
    assert logged[0]["was_principle_aligned"] is True


async def test_an_outcome_racing_a_close_leaves_both(env: Env) -> None:
    """Neither write carries the other's field, and both plan from the locked choice."""
    for round_ in range(4):
        uid = await _decided_choice(env, f"race-{round_}")

        outcome, close = await asyncio.gather(
            env.client.post(
                f"/api/choices/{uid}/outcome",
                json={"satisfaction_score": 3, "actual_outcome": f"round {round_}"},
            ),
            env.client.post(
                f"/api/choices/{uid}/status", data={"status": "completed"}, headers=HTMX
            ),
        )

        assert outcome.status_code == 200, outcome.text
        assert close.status_code == 200, close.text
        node = await _node(env, uid)
        assert node["status"] == "completed"
        assert node["completed_at"]
        assert node["satisfaction_score"] == 3
        assert node["actual_outcome"] == f"round {round_}"


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


async def test_an_outcome_on_a_choice_not_yet_decided_is_refused(env: Env) -> None:
    uid = await create(
        env.client, "choices", f"{MARK} undecided", options=[{"title": "A"}, {"title": "B"}]
    )
    page = await _page(env, uid)
    assert "data-choice-outcome" not in page, "no outcome form before a decision"
    before = _without_stamp(await _node(env, uid))

    with published(env.services.event_bus, ChoiceOutcomeRecorded) as recorded:
        refused = await env.client.post(
            f"/api/choices/{uid}/outcome",
            json={"satisfaction_score": 4, "actual_outcome": "Too soon"},
        )

    assert refused.status_code == 400, refused.text
    assert "Decide this choice before" in refused.text
    assert _without_stamp(await _node(env, uid)) == before
    assert recorded == []


async def test_a_malformed_outcome_is_refused(env: Env) -> None:
    uid = await _decided_choice(env, "malformed")
    before = _without_stamp(await _node(env, uid))

    answers = [
        await env.client.post(
            f"/api/choices/{uid}/outcome", data={"satisfaction_score": "6", "actual_outcome": "x"}
        ),
        await env.client.post(
            f"/api/choices/{uid}/outcome", data={"satisfaction_score": "3", "actual_outcome": ""}
        ),
    ]

    assert [answer.status_code for answer in answers] == [400, 400]
    assert _without_stamp(await _node(env, uid)) == before


async def test_another_users_choice_is_not_found_at_the_outcome_door(env: Env) -> None:
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
    decided = await env.services.choices.make_decision(theirs.uid, theirs.options[0].uid)
    assert decided.is_ok, decided
    before = _without_stamp(await _node(env, theirs.uid))

    answer = await env.client.post(
        f"/api/choices/{theirs.uid}/outcome",
        json={"satisfaction_score": 1, "actual_outcome": "Mine now"},
    )

    assert answer.status_code == 404
    assert _without_stamp(await _node(env, theirs.uid)) == before
