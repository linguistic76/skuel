"""The two group-link kinds, exercised against real Neo4j (ADR-088 §2).

A feedback request (``SUBMITTED_TO_GROUP``) and a share (``SHARED_WITH_GROUP``)
are different edges read by different readers, never crossed:

    teacher ─OWNS─▶ group ◀─MEMBER_OF─ student_1, student_2

    entry_submitted   student_1 ─SUBMITTED_TO_GROUP─▶ group   (asks the teacher)
    entry_shared      student_1 ─SHARED_WITH_GROUP──▶ group   (lets the class see)

The classmate (student_2) reads the group through the member reader and must
see the share and not the request; the teacher reads the queue and must see
the request and not the share. Both are pinned against the real Cypher: an
unknown relationship name matches zero rows rather than erroring, so a mocked
backend would prove only that a query was asked, not what it answered.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.sharing_backend import SharingBackend
from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from core.models.entity import Entity
from core.models.enums.neo_labels import NeoLabel
from core.models.type_hints import EntityUID, UserUID
from core.services.sharing.unified_sharing_service import UnifiedSharingService

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PREFIX = "sssplit"
TEACHER = f"{PREFIX}_teacher"
STUDENT_1 = f"{PREFIX}_student_1"
STUDENT_2 = f"{PREFIX}_student_2"
OUTSIDER = f"{PREFIX}_outsider"
GROUP = f"{PREFIX}_group"
INACTIVE_GROUP = f"{PREFIX}_group_inactive"
ENTRY_SUBMITTED = f"{PREFIX}_ue_submitted"
ENTRY_SHARED = f"{PREFIX}_ue_shared"

_SEED = """
CREATE (t:User {uid: $teacher, is_active: true}),
       (s1:User {uid: $s1, is_active: true}),
       (s2:User {uid: $s2, is_active: true}),
       (o:User {uid: $outsider, is_active: true}),
       (g:Group {uid: $group, name: 'Class', is_active: true}),
       (gi:Group {uid: $inactive, name: 'Old class', is_active: false})
CREATE (t)-[:OWNS]->(g), (t)-[:OWNS]->(gi)
CREATE (s1)-[:MEMBER_OF {role: 'student'}]->(g), (s2)-[:MEMBER_OF {role: 'student'}]->(g),
       (s1)-[:MEMBER_OF {role: 'student'}]->(gi)
CREATE (sub:Entity:UserEntry {
    uid: $submitted, entity_type: 'user_entry', title: 'For my teacher',
    status: 'submitted', pipeline: 'teacher_review', user_uid: $s1,
    created_at: datetime(), updated_at: datetime()
})
CREATE (sh:Entity:UserEntry {
    uid: $shared, entity_type: 'user_entry', title: 'For my class',
    status: 'active', pipeline: 'none', user_uid: $s1,
    created_at: datetime(), updated_at: datetime()
})
CREATE (s1)-[:OWNS]->(sub), (s1)-[:OWNS]->(sh)
"""

_CLEANUP = f"MATCH (n) WHERE n.uid STARTS WITH '{PREFIX}' DETACH DELETE n"

_PARAMS = {
    "teacher": TEACHER,
    "s1": STUDENT_1,
    "s2": STUDENT_2,
    "outsider": OUTSIDER,
    "group": GROUP,
    "inactive": INACTIVE_GROUP,
    "submitted": ENTRY_SUBMITTED,
    "shared": ENTRY_SHARED,
}


@pytest_asyncio.fixture
async def split_graph(neo4j_driver: Any) -> Any:
    """Seed the classroom; yield ``(sharing_service, sharing_backend, user_entry_backend)``."""
    sharing_backend = SharingBackend(
        driver=neo4j_driver,
        label=NeoLabel.ENTITY,
        entity_class=Entity,
        base_label=NeoLabel.ENTITY,
    )
    await sharing_backend.execute_query(_CLEANUP)
    await sharing_backend.execute_query(_SEED, _PARAMS)
    yield (
        UnifiedSharingService(backend=sharing_backend),
        sharing_backend,
        UserEntryBackend(driver=neo4j_driver),
    )
    await sharing_backend.execute_query(_CLEANUP)


async def _edges(backend: Any, entry_uid: str) -> list[tuple[str, str]]:
    result = await backend.execute_query(
        """
        MATCH (e:Entity {uid: $uid})-[r]->(g:Group)
        RETURN type(r) AS kind, g.uid AS group_uid ORDER BY kind, group_uid
        """,
        {"uid": entry_uid},
    )
    assert result.is_ok, result.error
    return [(str(row["kind"]), str(row["group_uid"])) for row in result.value or []]


class TestTheWriter:
    async def test_a_new_request_is_created_and_a_re_filed_one_is_matched(
        self, split_graph: Any
    ) -> None:
        sharing, backend, _ = split_graph

        first = await sharing.submit_to_group(
            entity_uid=EntityUID(ENTRY_SUBMITTED), owner_uid=STUDENT_1, group_uid=GROUP
        )
        assert first.is_ok, first.error
        assert first.value is True  # created

        second = await sharing.submit_to_group(
            entity_uid=EntityUID(ENTRY_SUBMITTED), owner_uid=STUDENT_1, group_uid=GROUP
        )
        assert second.is_ok, second.error
        assert second.value is False  # the request already stood — still a success

        assert await _edges(backend, ENTRY_SUBMITTED) == [("SUBMITTED_TO_GROUP", GROUP)]

    async def test_the_request_stamps_submitted_at_once(self, split_graph: Any) -> None:
        sharing, backend, _ = split_graph
        await sharing.submit_to_group(
            entity_uid=EntityUID(ENTRY_SUBMITTED), owner_uid=STUDENT_1, group_uid=GROUP
        )
        result = await backend.execute_query(
            """
            MATCH (:Entity {uid: $uid})-[r:SUBMITTED_TO_GROUP]->(:Group {uid: $g})
            RETURN r.submitted_at AS stamp, r.shared_at AS shared_at
            """,
            {"uid": ENTRY_SUBMITTED, "g": GROUP},
        )
        assert result.is_ok, result.error
        rows = result.value or []
        assert len(rows) == 1
        assert rows[0]["stamp"] is not None
        assert rows[0]["shared_at"] is None  # a request carries no share stamps

    async def test_a_non_member_is_refused(self, split_graph: Any) -> None:
        """The outsider owns nothing in the group. The seed gives them no entry,
        so the check is on the guard: an owned entry submitted to a group the
        owner is in neither as member nor owner is forbidden."""
        sharing, backend, _ = split_graph
        await backend.execute_query(
            """
            MATCH (o:User {uid: $o})
            CREATE (e:Entity:UserEntry {
                uid: $uid, entity_type: 'user_entry', title: 'Outsider work',
                status: 'submitted', pipeline: 'teacher_review', user_uid: $o,
                created_at: datetime(), updated_at: datetime()
            })
            CREATE (o)-[:OWNS]->(e)
            """,
            {"o": OUTSIDER, "uid": f"{PREFIX}_ue_outsider"},
        )
        result = await sharing.submit_to_group(
            entity_uid=EntityUID(f"{PREFIX}_ue_outsider"), owner_uid=OUTSIDER, group_uid=GROUP
        )
        assert result.is_error
        assert result.expect_error().category.value == "forbidden"
        assert await _edges(backend, f"{PREFIX}_ue_outsider") == []

    async def test_a_deactivated_group_is_refused(self, split_graph: Any) -> None:
        """Strict ``is_active = true``: a deactivated group grants nothing, so
        nothing is filed with it (ADR-088 §3)."""
        sharing, backend, _ = split_graph
        result = await sharing.submit_to_group(
            entity_uid=EntityUID(ENTRY_SUBMITTED), owner_uid=STUDENT_1, group_uid=INACTIVE_GROUP
        )
        assert result.is_error
        assert result.expect_error().category.value == "forbidden"
        assert await _edges(backend, ENTRY_SUBMITTED) == []


class TestTheTwoReadersNeverCross:
    @pytest_asyncio.fixture
    async def linked(self, split_graph: Any) -> Any:
        sharing, backend, user_entry_backend = split_graph
        submitted = await sharing.submit_to_group(
            entity_uid=EntityUID(ENTRY_SUBMITTED), owner_uid=STUDENT_1, group_uid=GROUP
        )
        assert submitted.is_ok, submitted.error
        shared = await sharing.share_with_group(
            entity_uid=EntityUID(ENTRY_SHARED), owner_uid=STUDENT_1, group_uid=GROUP
        )
        assert shared.is_ok, shared.error
        return sharing, backend, user_entry_backend

    async def test_the_classmate_sees_the_share_and_not_the_request(self, linked: Any) -> None:
        """The member reader (``/groups``) lists what was shared with the
        class; a turn-in sent to the teacher is not on it."""
        sharing, _, _ = linked
        result = await sharing.get_user_entries_shared_with_group(
            user_uid=UserUID(STUDENT_2), group_uid=GROUP
        )
        assert result.is_ok, result.error
        uids = [item["entity"]["uid"] for item in result.value]
        assert uids == [ENTRY_SHARED]

        peek = await sharing.get_user_entry_shared_with_group(
            user_uid=UserUID(STUDENT_2), group_uid=GROUP, entry_uid=EntityUID(ENTRY_SUBMITTED)
        )
        assert peek.is_ok, peek.error
        assert peek.value is None  # the single-entry peer read hides it too

    async def test_the_teacher_queue_lists_the_request_and_not_the_share(self, linked: Any) -> None:
        _, _, user_entry_backend = linked
        result = await user_entry_backend.get_review_queue_by_groups(TEACHER)
        assert result.is_ok, result.error
        uids = [str(row["entry_uid"]) for row in result.value or []]
        assert uids == [ENTRY_SUBMITTED]

    async def test_the_teacher_detail_opens_the_request_and_not_the_share(
        self, linked: Any
    ) -> None:
        _, _, user_entry_backend = linked
        opened = await user_entry_backend.get_entry_detail_for_teacher(ENTRY_SUBMITTED, TEACHER)
        assert opened.is_ok, opened.error
        assert [str(row["uid"]) for row in opened.value or []] == [ENTRY_SUBMITTED]

        refused = await user_entry_backend.get_entry_detail_for_teacher(ENTRY_SHARED, TEACHER)
        assert refused.is_ok, refused.error
        assert refused.value == []

    async def test_a_request_to_a_deactivated_group_is_not_pending_anywhere(
        self, linked: Any
    ) -> None:
        """Every teacher reader requires an active group: deactivating the
        class after a request was filed removes it from the queue, the
        dashboard's pending count and the students summary alike."""
        _, backend, user_entry_backend = linked
        await backend.execute_query(
            "MATCH (g:Group {uid: $g}) SET g.is_active = false", {"g": GROUP}
        )

        queue = await user_entry_backend.get_review_queue_by_groups(TEACHER)
        assert queue.is_ok and queue.value == []
        stats = await user_entry_backend.get_dashboard_stats(TEACHER)
        assert stats.is_ok, stats.error
        assert int((stats.value or [{}])[0].get("pending_count", 0)) == 0
        students = await user_entry_backend.get_students_summary(TEACHER)
        assert students.is_ok and students.value == []
