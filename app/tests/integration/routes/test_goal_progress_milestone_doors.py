"""The goal page's doors over the bootstrapped app: progress, add a milestone, complete or reopen one.

Each door verifies the owner at the route, reads JSON or the page's form through
``parse_body``, and writes from the goal as it stands under its lock
(``rewrite_under_lock``). Held here against the app's own graph:

- a milestone added from the page's form shows on the page and on the node, under a
  generated uid, and nothing else on the node changes;
- adds racing on one goal are all kept;
- a completion names its milestone by uid, a repeat moves no stamp, and a milestone
  the goal does not hold is not found;
- the goal's measurement type names the figure's one writer: on a milestone-measured
  goal the milestones move it and the last one achieves the goal once, by the fields
  the status door writes; on any other type they are a checklist;
- an entered figure writes its own fields and no others, in the goal's unit on a
  numeric goal; a derived goal refuses one; 100 achieves and a fall un-achieves;
- a reached milestone reopens from the page: the figure falls, a fall from 100
  un-achieves the goal, and the milestone keeps the day it was first reached through
  the completion that follows;
- a goal reopened at the status door takes the figure its measure gives (milestones,
  units), and only a goal whose percentage is the measure is reset to 0;
- a note posted with a figure from the page's form rides the history entry the
  write appends, a note with the figure unmoved is an entry of its own and moves no
  stamp, the page shows the history newest first, and notes racing on one goal are
  all kept;
- another user's goal is not found at any of the doors, and stays as it was.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import date
from html import unescape
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.events import GoalAchieved, GoalMilestoneReached, GoalProgressUpdated
from core.utils.zone_context import today_in_current_zone
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

MARK = "zzzgoaldoors"
CALLER = seed_user_uid(MARK)
STRANGER = seed_user_uid(f"{MARK}-stranger")
STRANGERS_GOAL = f"goal.{MARK}-not-yours"
HTMX = {"HX-Request": "true"}
_RACERS = 4
_TRIALS = 5


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


async def _goal(
    env: Env,
    title: str,
    measurement: str = "percentage",
    **fields: Any,  # boundary: JSON body fields
) -> str:
    """A goal made at the JSON create door."""
    return await create(
        env.client, "goals", f"{MARK} {title}", measurement_type=measurement, **fields
    )


async def _node(env: Env, uid: str) -> dict[str, Any]:  # boundary: raw node properties
    async with env.driver.session() as session:
        record = await (
            await session.run("MATCH (g:Goal {uid: $uid}) RETURN properties(g) AS p", uid=uid)
        ).single()
    assert record is not None, uid
    return dict(record["p"])


def _rows(node: dict[str, Any], field: str) -> list[dict[str, Any]]:  # boundary: JSON rows
    raw = node.get(field)
    if raw is None:
        return []
    assert isinstance(raw, str), f"{field} is stored as a JSON string, got {type(raw)}"
    rows = json.loads(raw)
    assert isinstance(rows, list)
    return rows


async def _milestones(env: Env, uid: str) -> list[dict[str, Any]]:  # boundary: JSON rows
    return _rows(await _node(env, uid), "milestones")


def _changed(
    before: dict[str, Any],  # boundary: raw node properties
    after: dict[str, Any],  # boundary: raw node properties
) -> set[str]:
    """The properties two reads of a node differ in, ``updated_at`` aside."""
    keys = (set(before) | set(after)) - {"updated_at"}
    return {key for key in keys if before.get(key) != after.get(key)}


async def _add(env: Env, uid: str, title: str, **fields: str) -> str:
    """Add one milestone at the JSON door; its uid."""
    answer = await env.client.post(f"/api/goals/{uid}/milestones", json={"title": title, **fields})
    assert answer.status_code == 200, answer.text
    return next(str(m["uid"]) for m in await _milestones(env, uid) if m["title"] == title)


async def _complete(env: Env, uid: str, milestone_uid: str) -> httpx.Response:
    return await env.client.post(
        f"/api/goals/{uid}/milestones/complete", json={"milestone_uid": milestone_uid}
    )


async def _reopen(env: Env, uid: str, milestone_uid: str) -> httpx.Response:
    return await env.client.post(
        f"/api/goals/{uid}/milestones/reopen", json={"milestone_uid": milestone_uid}
    )


async def _status(env: Env, uid: str, status: str) -> None:
    """Move a goal at the status door, as the page's status control posts it."""
    posted = await env.client.post(
        f"/api/goals/{uid}/status", data={"status": status}, headers=HTMX
    )
    assert posted.status_code == 200, posted.text


async def _backdate_milestones(env: Env, uid: str, day: date) -> None:
    """Move every stored milestone completion date to ``day``, as if reached then."""
    rows = await _milestones(env, uid)
    for row in rows:
        if row["is_completed"]:
            row["achieved_date"] = day.isoformat()
    async with env.driver.session() as session:
        await session.run(
            "MATCH (g:Goal {uid: $uid}) SET g.milestones = $rows", uid=uid, rows=json.dumps(rows)
        )


# ---------------------------------------------------------------------------
# Adding a milestone
# ---------------------------------------------------------------------------


async def test_an_added_milestone_is_stored_under_its_own_uid_and_changes_nothing_else(
    env: Env,
) -> None:
    uid = await _goal(env, "add")
    before = await _node(env, uid)
    due = today_in_current_zone()

    added = await env.client.post(
        f"/api/goals/{uid}/milestones",
        json={
            "title": "  First draft ",
            "target_date": due.isoformat(),
            "description": "All of it",
        },
    )

    assert added.status_code == 200, added.text
    after = await _node(env, uid)
    assert _changed(before, after) == {"milestones"}
    (stored,) = _rows(after, "milestones")
    assert re.fullmatch(r"milestone_[0-9a-f]{16}", stored["uid"])
    assert (stored["title"], stored["target_date"], stored["description"]) == (
        "First draft",
        due.isoformat(),
        "All of it",
    )
    assert (stored["is_completed"], stored["achieved_date"]) == (False, None)
    assert [m["uid"] for m in added.json()["milestones"]] == [stored["uid"]]


async def test_milestones_added_at_once_are_all_kept(env: Env) -> None:
    for trial in range(_TRIALS):
        uid = await _goal(env, f"race-add-{trial}")

        answers = await asyncio.gather(
            *[
                env.client.post(f"/api/goals/{uid}/milestones", json={"title": f"Step {n}"})
                for n in range(_RACERS)
            ]
        )

        assert [answer.status_code for answer in answers] == [200] * _RACERS
        stored = await _milestones(env, uid)
        assert sorted(m["title"] for m in stored) == [f"Step {n}" for n in range(_RACERS)]
        assert len({m["uid"] for m in stored}) == _RACERS


async def test_a_completion_racing_an_add_keeps_both(env: Env) -> None:
    for trial in range(_TRIALS):
        uid = await _goal(env, f"race-complete-{trial}", "milestone")
        first = await _add(env, uid, "First")

        completed, added = await asyncio.gather(
            _complete(env, uid, first),
            env.client.post(f"/api/goals/{uid}/milestones", json={"title": "Second"}),
        )

        assert (completed.status_code, added.status_code) == (200, 200)
        node = await _node(env, uid)
        stored = [(m["title"], m["is_completed"]) for m in _rows(node, "milestones")]
        assert stored == [("First", True), ("Second", False)]
        # Whichever landed second, the figure is the list's: one of two.
        assert node["progress_percentage"] == 50.0
        assert (node["current_value"], node["target_value"]) == (1.0, 2.0)
        assert node["status"] == "active"
        assert node.get("achieved_date") is None


# ---------------------------------------------------------------------------
# Completing a milestone
# ---------------------------------------------------------------------------


async def test_a_completion_names_its_milestone_by_uid(env: Env) -> None:
    uid = await _goal(env, "by-uid")
    await _add(env, uid, "Earlier")
    wanted = await _add(env, uid, "Wanted")
    await _add(env, uid, "Later")

    answer = await _complete(env, uid, wanted)

    assert answer.status_code == 200, answer.text
    stored = await _milestones(env, uid)
    assert [(m["title"], m["is_completed"]) for m in stored] == [
        ("Earlier", False),
        ("Wanted", True),
        ("Later", False),
    ]
    assert stored[1]["achieved_date"] == today_in_current_zone().isoformat()


async def test_a_repeat_completion_moves_no_stamp(env: Env) -> None:
    uid = await _goal(env, "repeat", "milestone")
    first = await _add(env, uid, "First")
    await _add(env, uid, "Second")
    assert (await _complete(env, uid, first)).status_code == 200
    reached = date(2026, 3, 1)
    await _backdate_milestones(env, uid, reached)
    before = await _node(env, uid)

    with published(env.services.event_bus, GoalMilestoneReached, GoalProgressUpdated) as events:
        again = await _complete(env, uid, first)

    assert again.status_code == 200, again.text
    after = await _node(env, uid)
    assert _changed(before, after) == set()
    assert _rows(after, "milestones")[0]["achieved_date"] == reached.isoformat()
    assert events == []


async def test_a_milestone_the_goal_does_not_hold_is_not_found(env: Env) -> None:
    uid = await _goal(env, "foreign-milestone")
    other = await _goal(env, "the-other-goal")
    await _add(env, uid, "Mine")
    elsewhere = await _add(env, other, "Elsewhere")
    before = await _node(env, uid)

    answer = await _complete(env, uid, elsewhere)

    assert answer.status_code == 404, answer.text
    assert _changed(before, await _node(env, uid)) == set()
    assert (await _milestones(env, other))[0]["is_completed"] is False


# ---------------------------------------------------------------------------
# Whose figure it is
# ---------------------------------------------------------------------------


async def test_the_last_milestone_achieves_a_milestone_goal_once_as_the_status_door_does(
    env: Env,
) -> None:
    uid = await _goal(env, "achieve", "milestone")
    first = await _add(env, uid, "First")
    second = await _add(env, uid, "Second")

    with published(env.services.event_bus, GoalAchieved, GoalMilestoneReached) as events:
        halfway = await _complete(env, uid, first)
        half_node = await _node(env, uid)
        done = await _complete(env, uid, second)
        done_node = await _node(env, uid)
        repeat = await _complete(env, uid, second)

    assert (halfway.status_code, done.status_code, repeat.status_code) == (200, 200, 200)
    assert (half_node["progress_percentage"], half_node["status"]) == (50.0, "active")
    assert half_node.get("achieved_date") is None
    assert done_node["progress_percentage"] == 100.0
    assert (done_node["current_value"], done_node["target_value"]) == (2.0, 2.0)
    assert done_node["status"] == "completed"
    assert done_node["achieved_date"] == today_in_current_zone().isoformat()
    assert [e.new_progress for e in events if isinstance(e, GoalProgressUpdated)] == []
    assert [type(e) for e in events] == [GoalMilestoneReached, GoalMilestoneReached, GoalAchieved]
    assert _changed(done_node, await _node(env, uid)) == set()

    # The status door completes a goal with the same three fields.
    by_status = await _goal(env, "achieve-by-status")
    posted = await env.client.post(
        f"/api/goals/{by_status}/status", data={"status": "completed"}, headers=HTMX
    )
    assert posted.status_code == 200, posted.text
    status_node = await _node(env, by_status)
    assert {k: status_node[k] for k in ("status", "achieved_date", "progress_percentage")} == {
        k: done_node[k] for k in ("status", "achieved_date", "progress_percentage")
    }


async def test_a_milestone_added_to_an_achieved_milestone_goal_un_achieves_it(env: Env) -> None:
    uid = await _goal(env, "un-achieve", "milestone")
    only = await _add(env, uid, "Only")
    assert (await _complete(env, uid, only)).status_code == 200
    assert (await _node(env, uid))["status"] == "completed"

    await _add(env, uid, "One more")

    node = await _node(env, uid)
    assert (node["status"], node["progress_percentage"]) == ("active", 50.0)
    assert node.get("achieved_date") is None


async def test_milestones_are_a_checklist_on_a_goal_they_do_not_measure(env: Env) -> None:
    uid = await _goal(env, "checklist")
    assert (await env.client.post(f"/api/goals/{uid}/progress", json={"progress": 40})).is_success
    only = await _add(env, uid, "Only")
    before = await _node(env, uid)

    with published(env.services.event_bus, GoalAchieved) as achieved:
        answer = await _complete(env, uid, only)

    assert answer.status_code == 200, answer.text
    after = await _node(env, uid)
    assert _changed(before, after) == {"milestones"}
    assert (after["progress_percentage"], after["status"]) == (40.0, "active")
    assert achieved == []


# ---------------------------------------------------------------------------
# An entered figure
# ---------------------------------------------------------------------------


async def test_an_entered_percentage_writes_its_own_fields_and_no_others(env: Env) -> None:
    uid = await _goal(env, "enter")
    await _add(env, uid, "A milestone the figure leaves alone")
    before = await _node(env, uid)

    with published(env.services.event_bus, GoalProgressUpdated) as moved:
        answer = await env.client.post(f"/api/goals/{uid}/progress", json={"progress": 37.5})

    assert answer.status_code == 200, answer.text
    assert answer.json()["progress_percentage"] == 37.5
    after = await _node(env, uid)
    assert _changed(before, after) == {
        "progress_percentage",
        "last_progress_update",
        "progress_history",
    }
    assert after["progress_percentage"] == 37.5
    assert [row["progress_percentage"] for row in _rows(after, "progress_history")] == [37.5]
    assert [(e.old_progress, e.new_progress, e.triggered_by_manual_update) for e in moved] == [
        (0.0, 37.5, True)
    ]

    same = await env.client.post(f"/api/goals/{uid}/progress", json={"progress": 37.5})
    assert same.status_code == 200, same.text
    assert _changed(after, await _node(env, uid)) == set()


async def test_a_numeric_goal_is_entered_in_its_own_unit(env: Env) -> None:
    uid = await _goal(env, "numeric", "numeric", target_value=50, unit_of_measurement="pages")
    before = await _node(env, uid)

    answer = await env.client.post(f"/api/goals/{uid}/progress", json={"progress": 30})

    assert answer.status_code == 200, answer.text
    after = await _node(env, uid)
    assert _changed(before, after) == {
        "current_value",
        "progress_percentage",
        "last_progress_update",
        "progress_history",
    }
    assert (after["current_value"], after["target_value"]) == (30.0, 50.0)
    assert after["progress_percentage"] == 60.0


@pytest.mark.parametrize("measurement", ["task_based", "habit_based", "milestone"])
async def test_a_goal_whose_figure_is_derived_refuses_an_entered_one(
    env: Env, measurement: str
) -> None:
    uid = await _goal(env, f"derived-{measurement}", measurement, target_value=30)
    before = await _node(env, uid)

    answer = await env.client.post(f"/api/goals/{uid}/progress", json={"progress": 80})

    assert answer.status_code == 422, answer.text
    assert _changed(before, await _node(env, uid)) == set()


async def test_a_percentage_above_100_is_refused(env: Env) -> None:
    uid = await _goal(env, "over")
    before = await _node(env, uid)

    answer = await env.client.post(f"/api/goals/{uid}/progress", json={"progress": 140})

    assert answer.status_code == 400, answer.text
    assert _changed(before, await _node(env, uid)) == set()


async def test_entering_100_achieves_the_goal_once_and_a_lower_figure_un_achieves_it(
    env: Env,
) -> None:
    uid = await _goal(env, "hundred")

    with published(env.services.event_bus, GoalAchieved) as achieved:
        reached = await env.client.post(f"/api/goals/{uid}/progress", json={"progress": 100})
        reached_node = await _node(env, uid)
        again = await env.client.post(f"/api/goals/{uid}/progress", json={"progress": 100})
        again_node = await _node(env, uid)
        lowered = await env.client.post(f"/api/goals/{uid}/progress", json={"progress": 80})

    assert (reached.status_code, again.status_code, lowered.status_code) == (200, 200, 200)
    assert reached_node["status"] == "completed"
    assert reached_node["achieved_date"] == today_in_current_zone().isoformat()
    assert _changed(reached_node, again_node) == set()
    assert [e.goal_uid for e in achieved] == [uid]
    node = await _node(env, uid)
    assert (node["status"], node["progress_percentage"]) == ("active", 80.0)
    assert node.get("achieved_date") is None


async def test_100_does_not_achieve_a_goal_its_owner_cancelled(env: Env) -> None:
    uid = await _goal(env, "cancelled")
    cancelled = await env.client.post(
        f"/api/goals/{uid}/status", data={"status": "cancelled"}, headers=HTMX
    )
    assert cancelled.status_code == 200, cancelled.text

    answer = await env.client.post(f"/api/goals/{uid}/progress", json={"progress": 100})

    assert answer.status_code == 200, answer.text
    node = await _node(env, uid)
    assert (node["status"], node["progress_percentage"]) == ("cancelled", 100.0)
    assert node.get("achieved_date") is None


# ---------------------------------------------------------------------------
# Another user's goal
# ---------------------------------------------------------------------------


async def test_another_users_goal_is_not_found_at_any_door_and_stays_as_it_was(env: Env) -> None:
    milestone = {"uid": "milestone_0000000000000001", "title": "Theirs", "is_completed": False}
    async with env.driver.session() as session:
        await session.run(
            """
            MERGE (u:User {uid: $stranger}) SET u.title = $stranger
            MERGE (g:Entity:Goal {uid: $goal})
            SET g.entity_type = 'goal', g.user_uid = $stranger, g.title = 'Not yours',
                g.status = 'active', g.measurement_type = 'percentage',
                g.progress_percentage = 10.0, g.milestones = $milestones
            MERGE (u)-[:OWNS]->(g)
            """,
            stranger=STRANGER,
            goal=STRANGERS_GOAL,
            milestones=json.dumps([milestone]),
        )
    before = await _node(env, STRANGERS_GOAL)

    answers = [
        await env.client.post(f"/api/goals/{STRANGERS_GOAL}/progress", json={"progress": 90}),
        await env.client.post(
            f"/api/goals/{STRANGERS_GOAL}/progress", json={"progress": 10, "note": "Mine now"}
        ),
        await env.client.post(f"/api/goals/{STRANGERS_GOAL}/milestones", json={"title": "Mine"}),
        await _complete(env, STRANGERS_GOAL, milestone["uid"]),
        await _reopen(env, STRANGERS_GOAL, milestone["uid"]),
    ]

    assert [answer.status_code for answer in answers] == [404, 404, 404, 404, 404]
    assert await _node(env, STRANGERS_GOAL) == before


# ---------------------------------------------------------------------------
# The page drives its own hx-post
# ---------------------------------------------------------------------------


def _attribute(tag: str, name: str) -> str:
    match = re.search(rf"""{name}=(?:"([^"]*)"|'([^']*)')""", tag)
    assert match is not None, (name, tag)
    return unescape(match.group(1) or match.group(2))


def _tag(html: str, marker: str) -> str:
    match = re.search(rf"<(?:form|button)[^>]*{marker}[^>]*>", html)
    assert match is not None, marker
    return match.group(0)


async def _page(env: Env, uid: str) -> str:
    shell = await env.client.get(f"/goals/detail?uid={uid}")
    assert shell.status_code == 200
    content = re.search(r'hx-get="(/goals/detail/content\?uid=[^"]*)"', shell.text)
    assert content is not None, "the detail shell loads its body over HTMX"
    page = await env.client.get(unescape(content.group(1)), headers=HTMX)
    assert page.status_code == 200
    return page.text


async def test_the_page_controls_post_to_their_own_doors(env: Env) -> None:
    uid = await _goal(env, "page", "milestone")
    page = await _page(env, uid)
    assert f'id="goal-detail-{uid}"' in page
    assert "data-goal-progress" not in page, "a milestone goal takes no entered figure"
    assert "Measured from this goal's milestones." in unescape(page)
    add_form = _tag(page, "data-goal-add-milestone")
    assert _attribute(add_form, "hx-target") == f"#goal-detail-{uid}"

    for title in ("Outline", "Draft"):
        swapped = await env.client.post(
            _attribute(add_form, "hx-post"),
            data={"title": title, "target_date": ""},
            headers=HTMX,
        )
        assert swapped.status_code == 200, swapped.text
        assert title in swapped.text
        add_form = _tag(swapped.text, "data-goal-add-milestone")
    assert f'id="goal-detail-{uid}"' in swapped.text

    outline, draft = (m["uid"] for m in await _milestones(env, uid))
    button = _tag(swapped.text, f'data-goal-milestone-complete="{outline}"')
    assert json.loads(_attribute(button, "hx-vals")) == {"milestone_uid": outline}
    half = await env.client.post(
        _attribute(button, "hx-post"), data=json.loads(_attribute(button, "hx-vals")), headers=HTMX
    )
    assert half.status_code == 200, half.text
    assert f'data-goal-milestone-complete="{outline}"' not in half.text
    assert "50%" in half.text

    button = _tag(half.text, f'data-goal-milestone-complete="{draft}"')
    done = await env.client.post(
        _attribute(button, "hx-post"), data=json.loads(_attribute(button, "hx-vals")), headers=HTMX
    )
    assert done.status_code == 200, done.text
    assert "data-goal-milestone-complete" not in done.text
    assert "100%" in done.text
    assert "Completed" in done.text
    assert (await _node(env, uid))["status"] == "completed"
    # The page a reload renders agrees with the fragment the door answered.
    assert "data-goal-milestone-complete" not in await _page(env, uid)


async def test_the_progress_form_posts_the_figure_the_page_asks_for(env: Env) -> None:
    percentage = await _goal(env, "page-percentage")
    numeric = await _goal(env, "page-numeric", "numeric", target_value=50, unit_of_measurement="km")

    form = _tag(await _page(env, percentage), "data-goal-progress")
    # The form's own encoding: FastHTML's ``Form`` declares multipart, and htmx sends it.
    assert _attribute(form, "enctype") == "multipart/form-data"
    saved = await env.client.post(
        _attribute(form, "hx-post"), files={"progress": (None, "45")}, headers=HTMX
    )
    assert saved.status_code == 200, saved.text
    assert "45%" in saved.text
    assert 'value="45"' in saved.text, "the form comes back holding the stored figure"

    numeric_page = await _page(env, numeric)
    assert "Progress so far (of 50 km)" in numeric_page
    form = _tag(numeric_page, "data-goal-progress")
    saved = await env.client.post(
        _attribute(form, "hx-post"), data={"progress": "12.5"}, headers=HTMX
    )
    assert saved.status_code == 200, saved.text
    assert "25%" in saved.text
    assert 'value="12.5"' in saved.text
    node = await _node(env, numeric)
    assert (node["current_value"], node["progress_percentage"]) == (12.5, 25.0)


# ---------------------------------------------------------------------------
# A progress note, kept on the history the page shows
# ---------------------------------------------------------------------------


async def test_a_figure_and_a_note_from_the_page_form_land_in_the_history_it_shows(
    env: Env,
) -> None:
    uid = await _goal(env, "page-note")
    page = await _page(env, uid)
    assert "No progress recorded yet." in page
    form = _tag(page, "data-goal-progress")

    # The form's own encoding (multipart), the note padded as a learner might type it.
    saved = await env.client.post(
        _attribute(form, "hx-post"),
        files={"progress": (None, "30"), "note": (None, "  Read chapter three \n")},
        headers=HTMX,
    )
    assert saved.status_code == 200, saved.text
    (entry,) = _rows(await _node(env, uid), "progress_history")
    assert (entry["progress_percentage"], entry["note"]) == (30.0, "Read chapter three")
    assert "note_only" not in entry

    # The same figure with a note: an entry of its own, marked, and no stamp moves.
    before = await _node(env, uid)
    form = _tag(saved.text, "data-goal-progress")
    held = await env.client.post(
        _attribute(form, "hx-post"),
        files={"progress": (None, "30"), "note": (None, "Stuck on four")},
        headers=HTMX,
    )
    assert held.status_code == 200, held.text
    after = await _node(env, uid)
    assert _changed(before, after) == {"progress_history"}
    assert [
        (row.get("note"), row.get("note_only")) for row in _rows(after, "progress_history")
    ] == [
        ("Read chapter three", None),
        ("Stuck on four", True),
    ]

    shown = unescape(await _page(env, uid))
    assert re.search(r">30%, unchanged</span>\s*</div>\s*<p[^>]*>Stuck on four</p>", shown)
    assert re.search(r">30%</span>\s*</div>\s*<p[^>]*>Read chapter three</p>", shown)
    assert shown.index("Stuck on four") < shown.index("Read chapter three"), "newest first"
    assert "No progress recorded yet." not in shown


async def test_notes_posted_at_once_are_all_kept(env: Env) -> None:
    uid = await _goal(env, "notes-race")

    for trial in range(_TRIALS):
        answers = await asyncio.gather(
            *(
                env.client.post(
                    f"/api/goals/{uid}/progress",
                    json={"progress": 10 * trial + racer, "note": f"t{trial}-r{racer}"},
                )
                for racer in range(_RACERS)
            )
        )
        assert [answer.status_code for answer in answers] == [200] * _RACERS

    notes = [row["note"] for row in _rows(await _node(env, uid), "progress_history")]
    assert sorted(notes) == sorted(
        f"t{trial}-r{racer}" for trial in range(_TRIALS) for racer in range(_RACERS)
    )


# ---------------------------------------------------------------------------
# Reopening: a milestone, and a goal
# ---------------------------------------------------------------------------

_FIRST_REACHED = date(2026, 1, 15)


async def test_the_page_reopens_a_reached_milestone_and_keeps_its_first_day(env: Env) -> None:
    uid = await _goal(env, "page-reopen", "milestone")
    outline = await _add(env, uid, "Outline")
    draft = await _add(env, uid, "Draft")
    for milestone in (outline, draft):
        assert (await _complete(env, uid, milestone)).status_code == 200
    await _backdate_milestones(env, uid, _FIRST_REACHED)
    assert (await _node(env, uid))["status"] == "completed"

    page = await _page(env, uid)
    assert "data-goal-milestone-complete" not in page
    button = _tag(page, f'data-goal-milestone-reopen="{draft}"')
    assert json.loads(_attribute(button, "hx-vals")) == {"milestone_uid": draft}
    assert _attribute(button, "hx-target") == f"#goal-detail-{uid}"
    with published(env.services.event_bus, GoalAchieved) as achieved:
        reopened = await env.client.post(
            _attribute(button, "hx-post"),
            data=json.loads(_attribute(button, "hx-vals")),
            headers=HTMX,
        )

    assert reopened.status_code == 200, reopened.text
    assert "50%" in reopened.text
    assert f'data-goal-milestone-complete="{draft}"' in reopened.text
    assert f'data-goal-milestone-reopen="{outline}"' in reopened.text
    node = await _node(env, uid)
    assert (node["progress_percentage"], node["status"]) == (50.0, "active")
    assert node.get("achieved_date") is None
    rows = {m["uid"]: m for m in _rows(node, "milestones")}
    assert (rows[draft]["is_completed"], rows[draft]["achieved_date"]) == (
        False,
        _FIRST_REACHED.isoformat(),
    )
    assert achieved == []

    button = _tag(reopened.text, f'data-goal-milestone-complete="{draft}"')
    done = await env.client.post(
        _attribute(button, "hx-post"), data=json.loads(_attribute(button, "hx-vals")), headers=HTMX
    )
    assert done.status_code == 200, done.text
    node = await _node(env, uid)
    assert (node["progress_percentage"], node["status"]) == (100.0, "completed")
    rows = {m["uid"]: m for m in _rows(node, "milestones")}
    assert rows[draft]["achieved_date"] == _FIRST_REACHED.isoformat(), "the first day stays"


async def test_a_goal_reopened_at_the_status_door_takes_its_measures_figure(env: Env) -> None:
    by_hand = await _goal(env, "reopen-by-hand", "milestone")
    first = await _add(env, by_hand, "One")
    await _add(env, by_hand, "Two")
    await _add(env, by_hand, "Three")
    assert (await _complete(env, by_hand, first)).status_code == 200
    measured = await _goal(env, "reopen-measured", "milestone")
    only = await _add(env, measured, "Only")
    assert (await _complete(env, measured, only)).status_code == 200
    numeric = await _goal(env, "reopen-units", "numeric", target_value=50)
    entered = await env.client.post(f"/api/goals/{numeric}/progress", json={"progress": 12.5})
    assert entered.status_code == 200, entered.text
    percentage = await _goal(env, "reopen-percentage")
    entered = await env.client.post(f"/api/goals/{percentage}/progress", json={"progress": 40})
    assert entered.status_code == 200, entered.text
    for uid in (by_hand, numeric, percentage):
        await _status(env, uid, "completed")

    with published(env.services.event_bus, GoalAchieved) as achieved:
        for uid in (by_hand, measured, numeric, percentage):
            assert (await _node(env, uid))["progress_percentage"] == 100.0, uid
            await _status(env, uid, "active")

    nodes = {uid: await _node(env, uid) for uid in (by_hand, measured, numeric, percentage)}
    for uid, node in nodes.items():
        assert node["status"] == "active", uid
        assert node.get("achieved_date") is None, uid
    # Completed by hand at 1 of 3: the milestones say a third.
    assert nodes[by_hand]["progress_percentage"] == pytest.approx(100 / 3)
    assert (nodes[by_hand]["current_value"], nodes[by_hand]["target_value"]) == (1.0, 3.0)
    # Every milestone still reached: 100% on a working goal, not re-achieved.
    assert nodes[measured]["progress_percentage"] == 100.0
    assert achieved == []
    # The units stay the learner's; the figure is derived from them.
    assert (nodes[numeric]["current_value"], nodes[numeric]["progress_percentage"]) == (
        12.5,
        25.0,
    )
    # The percentage is the whole measure: the reopen resets it.
    assert nodes[percentage]["progress_percentage"] == 0.0
