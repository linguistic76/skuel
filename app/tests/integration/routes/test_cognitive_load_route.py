"""``GET /cal/cognitive-load`` answers the caller's day, over the bootstrapped app.

The route reads the caller's open tasks due on the date, analyses each task's
cognitive load, and names the ones that risk overload. Both of its paths are
held here: a day with no task answers an empty report, and a day with tasks
answers one analysis per task with the overload risks drawn from the same
analyses — a task whose total load clears the overload threshold is a risk,
a light one is not.

The tasks are created at the domain's real create door, so each carries the
label, the ``entity_type``, the due date and the ownership edge the app itself
writes.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import create, signed_in_client

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

USER = seed_user_uid("cogload_caller")
MARK = "cogload"


@pytest_asyncio.fixture(loop_scope="session")
async def client(skuel_app) -> AsyncIterator[httpx.AsyncClient]:
    async with signed_in_client(skuel_app, USER, MARK) as http:
        yield http


def _day_after_tomorrow() -> str:
    """A day no other fixture's task lands on; a create door refuses a past due date."""
    return (today_in(current_zone()) + timedelta(days=2)).isoformat()


async def test_a_day_with_no_task_answers_an_empty_report(client: httpx.AsyncClient) -> None:
    response = await client.get("/cal/cognitive-load", params={"target_date": "2099-01-05"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["date"] == "2099-01-05"
    assert body["task_count"] == 0
    assert body["cognitive_analyses"] == []
    assert body["overload_risks"] == []


async def test_a_day_with_tasks_names_the_overload_risks(client: httpx.AsyncClient) -> None:
    """One analysis per open task due that day; the risks are the analyses that clear the threshold."""
    day = _day_after_tomorrow()
    heavy = await create(
        client,
        "tasks",
        f"{MARK} heavy",
        due_date=day,
        priority="high",
        project=f"{MARK}-project",
        knowledge_mastery_check=True,
    )
    light = await create(client, "tasks", f"{MARK} light", due_date=day, priority="low")

    response = await client.get("/cal/cognitive-load", params={"target_date": day})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["date"] == day
    assert body["task_count"] == 2
    by_uid = {a["task_uid"]: a for a in body["cognitive_analyses"]}
    assert set(by_uid) == {heavy, light}
    assert by_uid[heavy]["task_title"] == f"{MARK} heavy"
    assert by_uid[heavy]["cognitive_load"]["is_overload_risk"] is True
    assert by_uid[heavy]["cognitive_load"]["load_category"] == "overload"
    assert by_uid[light]["cognitive_load"]["is_overload_risk"] is False
    # The risks are drawn from the same analyses — the heavy task, whole, and only it.
    assert body["overload_risks"] == [by_uid[heavy]]


async def test_a_day_with_tasks_but_no_risk_answers_no_risk(client: httpx.AsyncClient) -> None:
    """The control of the risk filter: a day of light tasks reports every task and no risk."""
    day = _day_after_tomorrow()
    light = await create(client, "tasks", f"{MARK} only light", due_date=day, priority="low")

    response = await client.get("/cal/cognitive-load", params={"target_date": day})

    assert response.status_code == 200, response.text
    body = response.json()
    assert [a["task_uid"] for a in body["cognitive_analyses"]] == [light]
    assert body["overload_risks"] == []


async def test_a_signed_out_request_is_refused(skuel_app) -> None:
    """The route reads the caller's tasks — it has no answer without a caller."""
    async with signed_in_client(skuel_app, USER + "_out", MARK + "out") as http:
        http.cookies.clear()
        response = await http.get("/cal/cognitive-load")
    assert response.status_code == 401, response.text


@pytest.mark.parametrize(
    "strategy",
    [
        "cognitive_balanced",
        "knowledge_focused",
        "deadline_driven",
        "energy_aligned",
        "spaced_repetition",
    ],
)
async def test_the_sibling_optimizer_schedules_a_day_with_tasks(
    client: httpx.AsyncClient, strategy: str
) -> None:
    """``GET /cal/optimize`` reads the same tasks through the same orchestrator: every
    strategy answers a day with a task, and charges the day its load."""
    day = _day_after_tomorrow()
    await create(client, "tasks", f"{MARK} optimize {strategy}", due_date=day, priority="high")

    response = await client.get("/cal/optimize", params={"target_date": day, "strategy": strategy})

    assert response.status_code == 200, response.text
    assert response.json()["total_cognitive_load"] > 0.0
