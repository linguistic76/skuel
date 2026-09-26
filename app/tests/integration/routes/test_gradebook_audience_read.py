"""``GET /gradebook/{uid}`` opens for the owner or a recipient, and for nobody else.

The recipient read (ADR-088 §3, §5): a UserEntry's by-UID read
composes ``read_visibility`` OWNER_OR_AUDIENCE — the owner arm OR the audience
fragment (a direct ``SHARES_WITH``, or ``MEMBER_OF`` / ``OWNS`` of an ACTIVE
group the entry is ``SHARED_WITH_GROUP`` to). The access matrix:

    alice      owner                                   → the owner's page
    bob        SHARES_WITH the entry                   → the recipient card
    carol      MEMBER_OF the active group it is shared to → the recipient card
    teacher    OWNS that group                         → the recipient card
    teacher    the entry only SUBMITTED_TO_GROUP to it → 404 (a feedback request is not a share)
    dan        MEMBER_OF a DEACTIVATED group it is shared to → 404
    eve        an ex-member (edge removed)             → 404
    frank      a revoked share (edge removed)          → 404
    stranger   no link                                 → 404

A recipient's response — the card and the ``.md`` download — carries the
title, description and body and never the status, the processed body,
feedback or the exchange (R6). Run against a real Neo4j: the audience
predicate is Cypher composed by ``build_search_visibility_clause``, so a
mocked backend would only prove that the route calls a method.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fasthtml.common import FT, FtResponse, to_xml
from starlette.responses import Response

from adapters.inbound.fasthtml_types import RouteDecorator
from adapters.inbound.user_entry_ui import create_user_entry_ui_routes
from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from core.orchestrator.user_entry_orchestrator import UserEntryOrchestrator
from core.services.user_entry.user_entry_service import UserEntryService
from core.utils.result_simplified import Result

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PREFIX = "gbaud"
ALICE = f"user_{PREFIX}_alice"
BOB = f"user_{PREFIX}_bob"
CAROL = f"user_{PREFIX}_carol"
TEACHER = f"user_{PREFIX}_teacher"
DAN = f"user_{PREFIX}_dan"
EVE = f"user_{PREFIX}_eve"
FRANK = f"user_{PREFIX}_frank"
STRANGER = f"user_{PREFIX}_stranger"
GROUP = f"group_{PREFIX}_class"
INACTIVE_GROUP = f"group_{PREFIX}_old_class"
ENTRY_SHARED = f"ue_{PREFIX}_shared"
ENTRY_SUBMITTED = f"ue_{PREFIX}_submitted"

TITLE = "Breath awareness, week one"
DESCRIPTION = "What changed after five days of counting breaths."
BODY = "Day one felt forced; by day four the count came on its own."
PROCESSED = "PROCESSED-BODY-NEVER-FOR-A-RECIPIENT"
FEEDBACK = "TEACHER-FEEDBACK-NEVER-FOR-A-RECIPIENT"
OWNER_NAME = "Alice Ardent"

DETAIL_PATH = "/gradebook/{uid}"
DOWNLOAD_PATH = "/gradebook/{uid}/download"

Handler = Callable[..., Awaitable[FT | FtResponse | Response]]

_SEED = """
MERGE (alice:User {uid: $alice}) SET alice.is_active = true
MERGE (bob:User {uid: $bob}) SET bob.is_active = true
MERGE (carol:User {uid: $carol}) SET carol.is_active = true
MERGE (teacher:User {uid: $teacher}) SET teacher.is_active = true
MERGE (dan:User {uid: $dan}) SET dan.is_active = true
MERGE (eve:User {uid: $eve}) SET eve.is_active = true
MERGE (frank:User {uid: $frank}) SET frank.is_active = true
MERGE (stranger:User {uid: $stranger}) SET stranger.is_active = true
CREATE (g:Group {uid: $group, name: 'Class', is_active: true}),
       (gi:Group {uid: $inactive, name: 'Old class', is_active: false})
CREATE (teacher)-[:OWNS]->(g), (teacher)-[:OWNS]->(gi)
CREATE (carol)-[:MEMBER_OF {role: 'student'}]->(g),
       (dan)-[:MEMBER_OF {role: 'student'}]->(gi),
       (eve)-[:MEMBER_OF {role: 'student'}]->(g)
CREATE (shared:Entity:UserEntry {
    uid: $shared, entity_type: 'user_entry', title: $title, description: $description,
    content: $body, processed_content: $processed,
    status: 'submitted', pipeline: 'teacher_review', user_uid: $alice,
    created_at: datetime(), updated_at: datetime()
})
CREATE (submitted:Entity:UserEntry {
    uid: $submitted, entity_type: 'user_entry', title: 'For my teacher only',
    content: $body, status: 'submitted', pipeline: 'teacher_review', user_uid: $alice,
    created_at: datetime(), updated_at: datetime()
})
CREATE (alice)-[:OWNS]->(shared), (alice)-[:OWNS]->(submitted)
CREATE (bob)-[:SHARES_WITH {shared_at: datetime(), role: 'viewer'}]->(shared),
       (frank)-[:SHARES_WITH {shared_at: datetime(), role: 'viewer'}]->(shared)
CREATE (shared)-[:SHARED_WITH_GROUP {shared_at: datetime()}]->(g),
       (shared)-[:SHARED_WITH_GROUP {shared_at: datetime()}]->(gi)
CREATE (submitted)-[:SUBMITTED_TO_GROUP {submitted_at: datetime()}]->(g)
RETURN count(*) AS seeded
"""

# The ex-member and the revoked share: the links existed and are gone.
_RETRACT = """
MATCH (:User {uid: $eve})-[m:MEMBER_OF]->(:Group {uid: $group}) DELETE m
WITH count(*) AS _
MATCH (:User {uid: $frank})-[s:SHARES_WITH]->(:Entity {uid: $shared}) DELETE s
"""

_CLEANUP = f"""
MATCH (n) WHERE n.uid STARTS WITH 'ue_{PREFIX}' OR n.uid STARTS WITH 'group_{PREFIX}'
   OR n.uid STARTS WITH 'user_{PREFIX}'
DETACH DELETE n
"""

_PARAMS = {
    "alice": ALICE,
    "bob": BOB,
    "carol": CAROL,
    "teacher": TEACHER,
    "dan": DAN,
    "eve": EVE,
    "frank": FRANK,
    "stranger": STRANGER,
    "group": GROUP,
    "inactive": INACTIVE_GROUP,
    "shared": ENTRY_SHARED,
    "submitted": ENTRY_SUBMITTED,
    "title": TITLE,
    "description": DESCRIPTION,
    "body": BODY,
    "processed": PROCESSED,
}


def _make_request(user_uid: str, path: str) -> SimpleNamespace:
    """Session-backed request stub for ``require_authenticated_user`` + page chrome."""
    return SimpleNamespace(
        method="GET",
        session={"user_uid": user_uid},
        url=SimpleNamespace(path=path),
        query_params={},
        headers={},
        cookies={},
    )


def _collector() -> tuple[RouteDecorator, dict[str, Handler]]:
    registered: dict[str, Handler] = {}

    def rt(path: str, methods: list[str] | None = None) -> Callable[[Handler], Handler]:
        def decorator(fn: Handler) -> Handler:
            registered[path] = fn
            return fn

        return decorator

    return rt, registered


@pytest_asyncio.fixture
async def handlers(neo4j_driver: Any) -> Any:
    """Seed the matrix; yield the two registered handlers over the real read."""
    backend = UserEntryBackend(driver=neo4j_driver)
    await backend.execute_query(_CLEANUP)
    seeded = await backend.execute_query(_SEED, _PARAMS)
    assert seeded.is_ok and seeded.value and seeded.value[0]["seeded"] == 1, seeded
    retracted = await backend.execute_query(_RETRACT, _PARAMS)
    assert retracted.is_ok, retracted.error

    entries = UserEntryService(backend=backend)
    user_service = SimpleNamespace(
        get_user=AsyncMock(
            return_value=Result.ok(SimpleNamespace(display_name=OWNER_NAME, title="alice"))
        )
    )
    orchestrator = UserEntryOrchestrator(
        user_entry_service=entries,
        exercises_service=None,  # type: ignore[arg-type]
        teacher_review_service=None,  # type: ignore[arg-type]
        user_service=user_service,  # type: ignore[arg-type]
        activity_report_service=None,  # type: ignore[arg-type]
        revised_exercise_service=None,  # type: ignore[arg-type]
        entry_report_service=None,  # type: ignore[arg-type]
        report_relationship_service=None,  # type: ignore[arg-type]
    )
    # The owner's page reads its chain, MOC and respond eligibility through
    # the orchestrator; the audience read under test is the entry itself.
    # The chain carries feedback so the recipient assertions prove it is
    # never fetched for them, not merely absent from the seed.
    orchestrator.get_entry_chain = AsyncMock(  # type: ignore[method-assign]
        return_value=Result.ok({"exercise": None, "feedback": [{"uid": "er_1", "title": FEEDBACK}]})
    )
    orchestrator.get_entry_organized_children = AsyncMock(  # type: ignore[method-assign]
        return_value=Result.ok([])
    )
    # The recipient card's derived badges (PR 6c) — read after the audience
    # read admitted the viewer; the derivation itself is pinned on a real
    # graph in test_review_standing_read.py.
    orchestrator.get_entry_review_standing = AsyncMock(  # type: ignore[method-assign]
        return_value=Result.ok({"reviewed_by": "human", "revised_after_feedback": True})
    )
    orchestrator.is_entry_response_eligible = AsyncMock(  # type: ignore[method-assign]
        return_value=Result.ok(False)
    )

    rt, registered = _collector()
    create_user_entry_ui_routes(None, rt, entries, orchestrator=orchestrator)
    yield registered
    await backend.execute_query(_CLEANUP)


async def _open(handlers: dict[str, Handler], user_uid: str, uid: str) -> tuple[int, str]:
    """Render the detail page as the given user → (status, markup)."""
    response = await handlers[DETAIL_PATH](
        request=_make_request(user_uid, f"/gradebook/{uid}"), uid=uid
    )
    if isinstance(response, FtResponse):
        return response.status_code, to_xml(response.content)
    return 200, to_xml(response)


async def _download(handlers: dict[str, Handler], user_uid: str, uid: str) -> Response:
    response = await handlers[DOWNLOAD_PATH](
        request=_make_request(user_uid, f"/gradebook/{uid}/download"), uid=uid
    )
    assert isinstance(response, Response)
    return response


def _assert_recipient_card(html: str) -> None:
    assert TITLE in html
    assert DESCRIPTION in html
    assert f"From {OWNER_NAME}" in html
    assert "Shared with you" in html
    assert "Revised after feedback" in html and "Reviewed · Teacher" in html
    assert f"/gradebook/{ENTRY_SHARED}/download" in html
    # R6: never the status, the processed body, feedback or the exchange.
    assert "Status:" not in html
    assert PROCESSED not in html
    assert FEEDBACK not in html
    assert "/exchange" not in html
    assert "Submission Details" not in html


def _assert_not_found(status: int, html: str) -> None:
    assert status == 404
    assert "Submission not found" in html
    assert TITLE not in html
    assert BODY not in html
    assert PROCESSED not in html


class TestTheOwner:
    async def test_the_owner_gets_the_full_page(self, handlers: Any) -> None:
        status, html = await _open(handlers, ALICE, ENTRY_SHARED)
        assert status == 200
        assert "Submission Details" in html
        assert "Status:" in html
        assert PROCESSED in html
        assert FEEDBACK in html
        assert "Shared with you" not in html


class TestRecipients:
    async def test_a_person_share_opens_the_recipient_card(self, handlers: Any) -> None:
        status, html = await _open(handlers, BOB, ENTRY_SHARED)
        assert status == 200
        _assert_recipient_card(html)

    async def test_a_member_of_the_active_group_opens_it(self, handlers: Any) -> None:
        status, html = await _open(handlers, CAROL, ENTRY_SHARED)
        assert status == 200
        _assert_recipient_card(html)

    async def test_the_owner_of_the_active_group_opens_it(self, handlers: Any) -> None:
        """A share reaches members AND owners of an active group (ADR-042 §7, amended)."""
        status, html = await _open(handlers, TEACHER, ENTRY_SHARED)
        assert status == 200
        _assert_recipient_card(html)


class TestRefusals:
    async def test_a_feedback_request_is_not_a_share(self, handlers: Any) -> None:
        """The SUBMITTED-only teacher reviews it on the teaching surface, never here."""
        status, html = await _open(handlers, TEACHER, ENTRY_SUBMITTED)
        assert status == 404
        assert "For my teacher only" not in html

    async def test_a_deactivated_group_grants_nothing(self, handlers: Any) -> None:
        _assert_not_found(*await _open(handlers, DAN, ENTRY_SHARED))

    async def test_an_ex_member_is_refused(self, handlers: Any) -> None:
        _assert_not_found(*await _open(handlers, EVE, ENTRY_SHARED))

    async def test_a_revoked_share_is_refused(self, handlers: Any) -> None:
        _assert_not_found(*await _open(handlers, FRANK, ENTRY_SHARED))

    async def test_a_stranger_is_refused(self, handlers: Any) -> None:
        _assert_not_found(*await _open(handlers, STRANGER, ENTRY_SHARED))

    async def test_a_missing_uid_is_the_same_404(self, handlers: Any) -> None:
        """Absent and out-of-audience are one outcome — no existence oracle."""
        status, html = await _open(handlers, BOB, f"ue_{PREFIX}_does_not_exist")
        assert status == 404
        assert "Submission not found" in html


class TestTheDownload:
    async def test_a_recipient_gets_the_markdown_without_the_processed_body(
        self, handlers: Any
    ) -> None:
        response = await _download(handlers, BOB, ENTRY_SHARED)
        assert response.status_code == 200
        assert response.media_type == "text/markdown"
        assert (
            response.headers["content-disposition"]
            == 'attachment; filename="entry-breath-awareness--week-one.md"'
        )
        text = bytes(response.body).decode()
        assert text.startswith(f"# {TITLE}\n")
        assert DESCRIPTION in text
        assert BODY in text
        assert PROCESSED not in text
        assert "submitted" not in text

    async def test_the_owner_gets_the_same_file(self, handlers: Any) -> None:
        response = await _download(handlers, ALICE, ENTRY_SHARED)
        assert response.status_code == 200
        assert BODY in bytes(response.body).decode()

    async def test_a_stranger_gets_404_and_no_body(self, handlers: Any) -> None:
        response = await _download(handlers, STRANGER, ENTRY_SHARED)
        assert response.status_code == 404
        assert response.media_type == "text/plain"
        assert BODY not in bytes(response.body).decode()

    async def test_a_feedback_request_does_not_download_for_its_teacher(
        self, handlers: Any
    ) -> None:
        response = await _download(handlers, TEACHER, ENTRY_SUBMITTED)
        assert response.status_code == 404
