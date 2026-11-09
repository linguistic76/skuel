"""A learner asks for a personal review; an admin answers it from the queue.

Over the bootstrapped app (``_activity_link_rig``), each step is driven by the page's
own control: the learner's card on ``/submit-activity-report`` posts what its form
holds to its own ``hx-post``; the admin follows the queue card's link, loads the
snapshot through the snapshot form's ``hx-get``, and posts the feedback form with
what its ``hx-include`` names. The graph is then read raw: one pending request per
learner, answered and linked to the report (``ANSWERED_BY``) once the review is
written, and the report carries the snapshot the admin read.
"""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.relationship_names import RelationshipName
from core.models.type_hints import UserUID
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import signed_in_client

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

MARK = "zzzreviewask"
LEARNER_MARK = f"{MARK}l"
ADMIN_MARK = f"{MARK}a"
LEARNER = seed_user_uid(LEARNER_MARK)
ADMIN = seed_user_uid(ADMIN_MARK)
REPORT_PAGE = "/submit-activity-report"
QUEUE = "/activity-review/queue"
FEEDBACK = "/activity-review/submit-feedback"
FORM_ENCODED = {"content-type": "application/x-www-form-urlencoded", "HX-Request": "true"}


class _Forms(HTMLParser):
    """Every form on a page, by its ``hx-post`` / ``hx-get``, with what a browser submits.

    Also every named control outside a form, so an ``hx-include`` selector by name
    can be resolved against the whole page.
    """

    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, Any]] = []  # boundary: parsed attributes and fields
        self.controls: list[tuple[str, str]] = []  # every submittable (name, value) on the page
        self._form: dict[str, Any] | None = None  # boundary: the form being read
        self._select: str | None = None
        self._first_option: str | None = None
        self._selected: str | None = None
        self._textarea: str | None = None
        self._text: list[str] = []

    def _add(self, name: str, value: str) -> None:
        self.controls.append((name, value))
        if self._form is not None:
            self._form["fields"].append((name, value))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "form":
            self._form = {"attrs": a, "fields": []}
            self.forms.append(self._form)
        elif tag == "input" and a.get("name"):
            if a.get("type") == "checkbox" and "checked" not in a:
                return
            self._add(a["name"], a.get("value", ""))
        elif tag == "select":
            self._select, self._first_option, self._selected = a.get("name"), None, None
        elif tag == "option" and self._select is not None:
            value = a.get("value", "")
            if self._first_option is None:
                self._first_option = value
            if "selected" in a:
                self._selected = value
        elif tag == "textarea":
            self._textarea, self._text = a.get("name"), []

    def handle_data(self, data: str) -> None:
        if self._textarea is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._form = None
        elif tag == "select" and self._select is not None:
            self._add(self._select, self._selected or self._first_option or "")
            self._select = None
        elif tag == "textarea" and self._textarea is not None:
            self._add(self._textarea, "".join(self._text))
            self._textarea = None


def _forms(page: str) -> _Forms:
    parsed = _Forms()
    parsed.feed(page)
    return parsed


def _form(page: str, attr: str, target: str) -> dict[str, Any]:  # boundary: a parsed form
    matches = [f for f in _forms(page).forms if f["attrs"].get(attr) == target]
    assert len(matches) == 1, f"{len(matches)} forms with {attr}={target}"
    return matches[0]


def _included(page: str, selector: str) -> list[tuple[str, str]]:
    """The page's controls an ``hx-include`` of ``[name='…']`` selectors names."""
    names = {part.split("'")[1] for part in selector.split(",")}
    return [(n, v) for n, v in _forms(page).controls if n in names]


async def _requests(driver: AsyncDriver) -> list[dict[str, Any]]:  # boundary: raw rows
    async with driver.session() as session:
        result = await session.run(
            f"""
            MATCH (:User {{uid: $uid}})-[:{RelationshipName.REQUESTED.value}]->(r:ReviewRequest)
            OPTIONAL MATCH (r)-[:{RelationshipName.ANSWERED_BY.value}]->(report:ActivityReport)
            RETURN r.uid AS uid, r.status AS status, r.time_period AS time_period,
                   r.domains AS domains, r.message AS message, report.uid AS report_uid
            """,
            uid=LEARNER,
        )
        return [dict(row) async for row in result]


async def _set_role(driver: AsyncDriver, uid: str, role: str) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (u:User {uid: $uid})
            SET u.username = $uid, u.display_name = $uid, u.email = $uid + '@example.com',
                u.role = $role, u.created_at = datetime(), u.updated_at = datetime()
            """,
            uid=uid,
            role=role,
        )


class _World:
    def __init__(self, driver: AsyncDriver, learner: httpx.AsyncClient, admin: httpx.AsyncClient):
        self.driver, self.learner, self.admin = driver, learner, admin

    async def ask(self, message: str) -> httpx.Response:
        """The learner's card, submitted as the page renders it with a message typed."""
        page = (await self.learner.get(REPORT_PAGE)).text
        card = _form(page, "hx-post", "/api/activity-reviews/request")
        fields = [(n, message if n == "message" else v) for n, v in card["fields"]]
        return await self.learner.post(
            "/api/activity-reviews/request", content=urlencode(fields), headers=FORM_ENCODED
        )


@pytest_asyncio.fixture(loop_scope="session")
async def world(skuel_app: FastHTMLApp) -> AsyncIterator[_World]:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with (
        signed_in_client(skuel_app, LEARNER, LEARNER_MARK) as learner,
        signed_in_client(skuel_app, ADMIN, ADMIN_MARK) as admin,
    ):
        await _set_role(driver, LEARNER, "member")
        await _set_role(driver, ADMIN, "admin")
        yield _World(driver, learner, admin)


async def test_a_learners_request_reaches_the_queue_once(world: _World) -> None:
    first = await world.ask("Look at my habits, please")

    assert first.status_code == 201
    assert "it's waiting" in unescape(first.text)
    [request] = await _requests(world.driver)
    assert request["status"] == "pending"
    assert request["time_period"] == "7d"
    assert set(request["domains"]) == {
        "tasks",
        "goals",
        "habits",
        "events",
        "choices",
        "principles",
    }
    assert request["message"] == "Look at my habits, please"

    # The page then shows the open request and offers no second ask.
    page = unescape((await world.learner.get(REPORT_PAGE)).text)
    assert "it's waiting" in page
    assert 'hx-post="/api/activity-reviews/request"' not in page

    # Asked again (a stale tab), the open request answers and nothing more is queued.
    again = await world.learner.post("/api/activity-reviews/request", json={"time_period": "30d"})
    assert again.status_code == 200
    assert again.json()["uid"] == request["uid"]
    assert len(await _requests(world.driver)) == 1

    queue = unescape((await world.admin.get(QUEUE)).text)
    assert LEARNER in queue
    assert f"review_request_uid={request['uid']}" in queue


async def test_a_review_from_the_queue_stores_its_snapshot_and_closes_the_request(
    skuel_app: FastHTMLApp, world: _World
) -> None:
    assert (await world.ask("")).status_code == 201
    [request] = await _requests(world.driver)

    # The queue card's link opens the review form with the request.
    queue = (await world.admin.get(QUEUE)).text
    [href] = [
        unescape(h) for h in _hrefs(queue) if h.startswith("/activity-review/new?") and LEARNER in h
    ]
    review_page = (await world.admin.get(href)).text

    # Load the snapshot as the snapshot form does.
    snapshot_form = _form(review_page, "hx-get", "/activity-review/snapshot-fragment")
    fragment = await world.admin.get(
        "/activity-review/snapshot-fragment?" + urlencode(snapshot_form["fields"])
    )
    assert fragment.status_code == 200
    page = review_page.replace(
        '<div id="snapshot-display">', f'<div id="snapshot-display">{fragment.text}', 1
    )

    # Post the feedback form: its own fields, plus what its hx-include names.
    feedback_form = _form(page, "hx-post", FEEDBACK)
    fields = [
        (n, "A steady week." if n == "feedback_text" else v) for n, v in feedback_form["fields"]
    ] + _included(page, feedback_form["attrs"]["hx-include"])
    sent = await world.admin.post(FEEDBACK, content=urlencode(fields), headers=FORM_ENCODED)

    assert sent.status_code == 200, sent.text
    assert "answered and leaves the queue" in sent.text

    [closed] = await _requests(world.driver)
    assert closed["uid"] == request["uid"]
    assert closed["status"] == "answered"
    assert closed["report_uid"] is not None
    report = await skuel_app.state.services.activity_report.get_for_user(
        closed["report_uid"], UserUID(LEARNER)
    )
    snapshot = report.value.metadata["snapshot"]
    assert snapshot["subject_uid"] == LEARNER
    assert set(snapshot["domains"]) >= {"tasks", "habits"}
    assert set(report.value.domains_covered) == {
        "tasks",
        "goals",
        "habits",
        "events",
        "choices",
        "principles",
    }

    # The learner reads it: the snapshot the admin read is its domain breakdown, and
    # the Markdown download renders the stored metadata.
    detail = await world.learner.get(f"/activity-reports/detail/content?uid={closed['report_uid']}")
    assert detail.status_code == 200
    assert "Domain Breakdown" in detail.text
    assert "A steady week." in detail.text
    md = await world.learner.get(f"/activity-reports/md?uid={closed['report_uid']}")
    assert md.status_code == 200
    assert "A steady week." in md.text

    # Answered, it leaves the queue; the learner can ask again.
    assert LEARNER not in unescape((await world.admin.get(QUEUE)).text)
    learner_page = (await world.learner.get(REPORT_PAGE)).text
    assert 'hx-post="/api/activity-reviews/request"' in learner_page

    # Submitting the same review again is refused: the request is no longer pending.
    again = await world.admin.post(FEEDBACK, content=urlencode(fields), headers=FORM_ENCODED)
    assert again.status_code == 400
    assert "no longer pending" in again.text


async def test_a_non_admin_is_refused_at_the_feedback_door(world: _World) -> None:
    refused = await world.learner.post(
        FEEDBACK,
        content=urlencode({"subject_uid": LEARNER, "feedback_text": "I'm great."}),
        headers=FORM_ENCODED,
    )

    assert refused.status_code == 403
    async with world.driver.session() as session:
        written = await (
            await session.run(
                "MATCH (r:ActivityReport {user_uid: $uid}) RETURN count(r) AS n", uid=LEARNER
            )
        ).single()
    assert written is not None and written["n"] == 0


def _hrefs(page: str) -> list[str]:
    class _Links(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.hrefs: list[str] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag == "a":
                self.hrefs.extend(v or "" for k, v in attrs if k == "href")

    links = _Links()
    links.feed(page)
    return links.hrefs


async def test_a_generated_reports_stored_metadata_reads_back_on_its_pages(
    skuel_app: FastHTMLApp, world: _World
) -> None:
    """Two machine reports from the card: each page and download reads its metadata, and
    the second compares itself with the first (the prior report's metadata is read)."""

    async def generate(period: str) -> str:
        page = (await world.learner.get(REPORT_PAGE)).text
        card = _form(page, "hx-post", "/api/reports/progress/generate")
        fields = [(n, period if n == "time_period" else v) for n, v in card["fields"]]
        generated = await world.learner.post(
            "/api/reports/progress/generate", content=urlencode(fields), headers=FORM_ENCODED
        )
        assert generated.status_code == 200, generated.text
        [href] = [h for h in _hrefs(generated.text) if h.startswith("/activity-reports/detail?")]
        return href.split("uid=", 1)[1]

    first, second = await generate("7d"), await generate("14d")
    reports = skuel_app.state.services.activity_report
    prior = (await reports.get_for_user(first, UserUID(LEARNER))).value
    latest = (await reports.get_for_user(second, UserUID(LEARNER))).value

    assert prior.metadata["time_period"] == "7d"
    assert prior.metadata["intelligence"]
    assert latest.metadata["comparison"]["previous_report_uid"] == first
    for uid in (first, second):
        detail = await world.learner.get(f"/activity-reports/detail/content?uid={uid}")
        assert detail.status_code == 200, detail.text
        md = await world.learner.get(f"/activity-reports/md?uid={uid}")
        assert md.status_code == 200, md.text
