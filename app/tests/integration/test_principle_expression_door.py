"""A principle's two append doors over the bootstrapped app: an expression, a reflection.

``POST /api/principles/expression`` appends a lived expression to the principle's
``expressions``; ``POST /api/principles/reflection`` appends a dated entry to its
``alignment_history``. Each plans its write from the principle as it stands under its
lock (``rewrite_under_lock``) and writes its own fields alone. Held here against the
app's own graph:

- a door-appended expression is stored as the JSON list every writer stores, and the
  read model hands it back as written;
- the append writes ``expressions`` (and ``updated_at``) and nothing else;
- four expressions appended at once are all kept, and so are four reflections, and a
  self-assessment beside a reflection;
- an append racing an archive leaves both: the expression and the archived status;
- another user's principle is not found, and is left as it was.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums.principle_enums import AlignmentLevel
from core.models.principle.principle import Principle
from core.models.principle.principle_request import (
    PrincipleCreateRequest,
    PrincipleExpressionRequest,
)
from core.models.principle.principle_types import PrincipleExpression
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import create, signed_in_client, wipe

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

MARK = "zzzprincipleexpr"
CALLER = seed_user_uid(MARK)
STRANGER = seed_user_uid(f"{MARK}-stranger")


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


async def _principle(env: Env, title: str) -> str:
    return await create(env.client, "principles", f"{MARK} {title}")


async def _node(env: Env, uid: str) -> dict[str, Any]:  # boundary: raw node properties
    async with env.driver.session() as session:
        record = await (
            await session.run("MATCH (p:Principle {uid: $uid}) RETURN properties(p) AS p", uid=uid)
        ).single()
    assert record is not None, uid
    return dict(record["p"])


def _rows(node: dict[str, Any], key: str) -> list[dict[str, Any]]:  # boundary: JSON rows
    raw = node.get(key)
    if raw is None or raw == []:
        return []
    assert isinstance(raw, str), f"{key} is stored as a JSON string, got {type(raw)}"
    rows = json.loads(raw)
    assert isinstance(rows, list)
    return rows


def _without_stamp(node: dict[str, Any]) -> dict[str, Any]:  # boundary: raw node properties
    return {key: value for key, value in node.items() if key != "updated_at"}


async def _express(env: Env, uid: str, context: str) -> httpx.Response:
    return await env.client.post(
        f"/api/principles/expression?uid={uid}",
        json={"context": context, "behavior": f"{context} behavior", "example": None},
    )


async def _reflect(env: Env, uid: str, evidence: str) -> httpx.Response:
    return await env.client.post(
        "/api/principles/reflection",
        json={"principle_uid": uid, "alignment_level": "aligned", "evidence": evidence},
    )


# ---------------------------------------------------------------------------
# One stored shape, one written field
# ---------------------------------------------------------------------------


async def test_an_appended_expression_is_stored_and_read_back_as_written(env: Env) -> None:
    uid = await _principle(env, "shape")

    first = await _express(env, uid, "Work")
    second = await env.client.post(
        f"/api/principles/expression?uid={uid}",
        json={"context": "Family", "behavior": "Listen first", "example": "Dinner"},
    )

    assert first.status_code == 200, first.text
    assert second.json() == {"context": "Family", "behavior": "Listen first", "example": "Dinner"}
    stored = _rows(await _node(env, uid), "expressions")
    assert stored == [
        {"context": "Work", "behavior": "Work behavior", "example": None},
        {"context": "Family", "behavior": "Listen first", "example": "Dinner"},
    ]
    read = await env.services.principles.core.backend.get(uid)
    assert read.is_ok, read
    assert isinstance(read.value, Principle)
    assert read.value.expressions == (
        PrincipleExpression(context="Work", behavior="Work behavior", example=None),
        PrincipleExpression(context="Family", behavior="Listen first", example="Dinner"),
    )


async def test_an_expression_created_with_the_principle_is_kept_by_an_append(env: Env) -> None:
    created = await env.services.principles.create_principle(
        PrincipleCreateRequest(
            title=f"{MARK} seeded",
            statement="seeded statement",
            expressions=[PrincipleExpressionRequest(context="Home", behavior="Rest")],
        ),
        CALLER,
    )
    assert created.is_ok, created
    uid = created.value.uid

    appended = await _express(env, uid, "Work")

    assert appended.status_code == 200, appended.text
    assert [row["context"] for row in _rows(await _node(env, uid), "expressions")] == [
        "Home",
        "Work",
    ]


async def test_the_append_writes_its_list_and_nothing_else(env: Env) -> None:
    uid = await _principle(env, "fields")
    before = await _node(env, uid)

    appended = await _express(env, uid, "Work")

    assert appended.status_code == 200, appended.text
    after = await _node(env, uid)
    changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
    assert changed == {"expressions", "updated_at"}


# ---------------------------------------------------------------------------
# The lock: racing appends on one principle serialize
# ---------------------------------------------------------------------------


async def test_four_expressions_appended_at_once_are_all_kept(env: Env) -> None:
    uid = await _principle(env, "race-append")

    answers = await asyncio.gather(*[_express(env, uid, f"Context {n}") for n in range(4)])

    assert [answer.status_code for answer in answers] == [200] * 4
    assert sorted(row["context"] for row in _rows(await _node(env, uid), "expressions")) == [
        f"Context {n}" for n in range(4)
    ]


async def test_an_append_racing_an_archive_keeps_both(env: Env) -> None:
    for round_ in range(4):
        uid = await _principle(env, f"race-archive-{round_}")

        archive, append = await asyncio.gather(
            env.client.post(f"/api/principles/{uid}/status", data={"status": "archived"}),
            _express(env, uid, "Work"),
        )

        assert archive.status_code == 200, archive.text
        assert append.status_code == 200, append.text
        node = await _node(env, uid)
        assert node["status"] == "archived", round_
        assert [row["context"] for row in _rows(node, "expressions")] == ["Work"], round_


async def test_four_reflections_recorded_at_once_are_all_kept(env: Env) -> None:
    uid = await _principle(env, "race-reflect")
    seeded = len(_rows(await _node(env, uid), "alignment_history"))

    answers = await asyncio.gather(*[_reflect(env, uid, f"Evidence {n}") for n in range(4)])

    assert [answer.status_code for answer in answers] == [200] * 4
    history = _rows(await _node(env, uid), "alignment_history")
    assert len(history) == seeded + 4
    assert sorted(row["evidence"] for row in history[seeded:]) == [
        f"Evidence {n}" for n in range(4)
    ]


async def test_a_self_assessment_racing_a_reflection_keeps_both(env: Env) -> None:
    """The staged self-assessment (``assess_with_user_input``) appends to the same
    history the reflection door does, under the same lock."""
    for round_ in range(4):
        uid = await _principle(env, f"race-assess-{round_}")
        seeded = len(_rows(await _node(env, uid), "alignment_history"))

        assessed, reflected = await asyncio.gather(
            env.services.principles.alignment.assess_with_user_input(
                uid, CALLER, AlignmentLevel.PARTIAL, "Assessed"
            ),
            _reflect(env, uid, "Reflected"),
        )

        assert assessed.is_ok, assessed
        assert reflected.status_code == 200, reflected.text
        history = _rows(await _node(env, uid), "alignment_history")
        assert sorted(row["evidence"] for row in history[seeded:]) == [
            "Assessed",
            "Reflected",
        ], round_


# ---------------------------------------------------------------------------
# Refusals leave the principle as it was
# ---------------------------------------------------------------------------


async def test_another_users_principle_is_not_found_and_unchanged(env: Env) -> None:
    async with env.driver.session() as session:
        await session.run("MERGE (u:User {uid: $uid}) SET u.title = $uid", uid=STRANGER)
    created = await env.services.principles.create_principle(
        PrincipleCreateRequest(title=f"{MARK} not yours", statement="theirs"), STRANGER
    )
    assert created.is_ok, created
    theirs = created.value.uid
    before = _without_stamp(await _node(env, theirs))

    answers = [await _express(env, theirs, "Mine now"), await _reflect(env, theirs, "Mine")]

    assert [answer.status_code for answer in answers] == [404, 404]
    assert _without_stamp(await _node(env, theirs)) == before
