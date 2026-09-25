"""R8 co-membership against real Neo4j (ADR-088 §7).

The one predicate — ``build_co_membership_fragment`` — decides who a person
may share with, and it is pinned here on the real Cypher because the
default-group carve-out is a *shape* rule (which edge reaches the group), not
a name rule a mocked backend could answer:

    admin ─OWNS─▶ group_default_admin ◀─MEMBER_OF─ alice, bob   (the enrolled platform)
    teacher ─OWNS─▶ class ◀─MEMBER_OF─ alice, carol              (a real class)
    teacher ─OWNS─▶ old_class (inactive) ◀─MEMBER_OF─ alice, dave

    alice ↔ carol   co-members (the class)
    alice ↔ teacher co-members (the class, through its owner)
    alice ↔ admin   co-members (the default group, through its OWNER)
    alice ↔ bob     NOT co-members (default-group roster only)
    alice ↔ dave    NOT co-members (an inactive group grants nothing)
    alice ↔ erin    NOT co-members (no group at all)

The same predicate guards the person-share MERGE, so ``share()`` refuses what
the read refuses — and the forms' ``share_with_admin`` exemption bypasses it.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.sharing_backend import SharingBackend
from core.models.entity import Entity
from core.models.enums.neo_labels import NeoLabel
from core.models.group.group import default_group_uid
from core.models.type_hints import EntityUID, UserUID
from core.services.sharing.unified_sharing_service import UnifiedSharingService

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PREFIX = "r8comem"
ADMIN = f"{PREFIX}_admin"
TEACHER = f"{PREFIX}_teacher"
ALICE = f"{PREFIX}_alice"
BOB = f"{PREFIX}_bob"
CAROL = f"{PREFIX}_carol"
DAVE = f"{PREFIX}_dave"
ERIN = f"{PREFIX}_erin"
DEFAULT_GROUP = default_group_uid(ADMIN)
CLASS = f"{PREFIX}_class"
OLD_CLASS = f"{PREFIX}_old_class"
ENTRY = f"{PREFIX}_ue_alice"

_SEED = """
CREATE (admin:User {uid: $admin, title: $admin_name, is_active: true}),
       (teacher:User {uid: $teacher, title: $teacher_name, is_active: true}),
       (alice:User {uid: $alice, title: $alice_name, is_active: true}),
       (bob:User {uid: $bob, title: $bob_name, is_active: true}),
       (carol:User {uid: $carol, title: $carol_name, is_active: true}),
       (dave:User {uid: $dave, title: $dave_name, is_active: true}),
       (erin:User {uid: $erin, title: $erin_name, is_active: true}),
       (dg:Group {uid: $default_group, name: 'Default Group', is_active: true}),
       (cl:Group {uid: $class, name: 'Class', is_active: true}),
       (old:Group {uid: $old_class, name: 'Old class', is_active: false})
CREATE (admin)-[:OWNS]->(dg), (teacher)-[:OWNS]->(cl), (teacher)-[:OWNS]->(old)
CREATE (alice)-[:MEMBER_OF {role: 'student'}]->(dg), (bob)-[:MEMBER_OF {role: 'student'}]->(dg),
       (alice)-[:MEMBER_OF {role: 'student'}]->(cl), (carol)-[:MEMBER_OF {role: 'student'}]->(cl),
       (alice)-[:MEMBER_OF {role: 'student'}]->(old), (dave)-[:MEMBER_OF {role: 'student'}]->(old)
CREATE (e:Entity:UserEntry {
    uid: $entry, entity_type: 'user_entry', title: 'Draft', status: 'active',
    pipeline: 'none', user_uid: $alice, created_at: datetime(), updated_at: datetime()
})
CREATE (alice)-[:OWNS]->(e)
"""

_CLEANUP = (
    f"MATCH (n) WHERE n.uid STARTS WITH '{PREFIX}' OR n.uid = '{DEFAULT_GROUP}' DETACH DELETE n"
)

_PARAMS = {
    "admin": ADMIN,
    "admin_name": "r8_admin_name",
    "teacher": TEACHER,
    "teacher_name": "r8_teacher_name",
    "alice": ALICE,
    "alice_name": "r8_Alice",
    "bob": BOB,
    "bob_name": "r8_bob_name",
    "carol": CAROL,
    "carol_name": "r8_Carol",
    "dave": DAVE,
    "dave_name": "r8_dave_name",
    "erin": ERIN,
    "erin_name": "r8_erin_name",
    "default_group": DEFAULT_GROUP,
    "class": CLASS,
    "old_class": OLD_CLASS,
    "entry": ENTRY,
}


@pytest_asyncio.fixture
async def graph(neo4j_driver: Any) -> Any:
    backend = SharingBackend(
        driver=neo4j_driver,
        label=NeoLabel.ENTITY,
        entity_class=Entity,
        base_label=NeoLabel.ENTITY,
    )
    await backend.execute_query(_CLEANUP)
    seeded = await backend.execute_query(_SEED + " RETURN count(e) AS n", _PARAMS)
    assert seeded.is_ok and seeded.value and seeded.value[0]["n"] == 1, seeded
    yield UnifiedSharingService(backend=backend), backend
    await backend.execute_query(_CLEANUP)


async def _shares_with_count(backend: Any) -> int:
    result = await backend.execute_query(
        "MATCH (:User)-[r:SHARES_WITH]->(e:Entity {uid: $uid}) RETURN count(r) AS c",
        {"uid": ENTRY},
    )
    assert result.is_ok, result.error
    return int(result.value[0]["c"]) if result.value else 0


class TestTheReads:
    async def test_a_classmate_resolves_by_exact_username(self, graph: Any) -> None:
        sharing, _ = graph
        assert (await sharing.resolve_co_member(ALICE, "r8_Carol")).value == CAROL
        # Case is preserved: the lowercase spelling is not a user.
        assert (await sharing.resolve_co_member(ALICE, "r8_carol")).value is None

    async def test_the_class_owner_and_the_default_group_owner_are_co_members(
        self, graph: Any
    ) -> None:
        sharing, _ = graph
        assert (await sharing.shares_group_with(ALICE, TEACHER)).value is True
        assert (await sharing.shares_group_with(ALICE, ADMIN)).value is True
        # And in the other direction: the admin may share with their student.
        assert (await sharing.shares_group_with(ADMIN, ALICE)).value is True

    async def test_the_default_group_roster_does_not_count(self, graph: Any) -> None:
        sharing, _ = graph
        assert (await sharing.shares_group_with(ALICE, BOB)).value is False
        assert (await sharing.resolve_co_member(ALICE, "r8_bob_name")).value is None

    async def test_an_inactive_group_grants_nothing(self, graph: Any) -> None:
        sharing, _ = graph
        assert (await sharing.shares_group_with(ALICE, DAVE)).value is False

    async def test_a_stranger_and_an_unknown_name_read_the_same(self, graph: Any) -> None:
        sharing, _ = graph
        assert (await sharing.resolve_co_member(ALICE, "r8_erin_name")).value is None
        assert (await sharing.resolve_co_member(ALICE, "nobody_at_all")).value is None
        assert (await sharing.shares_group_with(ALICE, ERIN)).value is False
        assert (await sharing.shares_group_with(ALICE, "user_does_not_exist")).value is False

    async def test_ones_own_username_resolves_to_oneself(self, graph: Any) -> None:
        """The resolver refuses the owner; the read must hand it the uid to compare."""
        sharing, _ = graph
        assert (await sharing.resolve_co_member(ALICE, "r8_Alice")).value == ALICE
        assert (await sharing.shares_group_with(ALICE, ALICE)).value is False

    async def test_reachable_groups_are_active_and_joined_or_owned(self, graph: Any) -> None:
        sharing, _ = graph
        alice = await sharing.reachable_groups(ALICE, [DEFAULT_GROUP, CLASS, OLD_CLASS, "g_none"])
        assert alice.value == frozenset({DEFAULT_GROUP, CLASS})
        teacher = await sharing.reachable_groups(TEACHER, [CLASS, OLD_CLASS, DEFAULT_GROUP])
        assert teacher.value == frozenset({CLASS})
        erin = await sharing.reachable_groups(ERIN, [CLASS])
        assert erin.value == frozenset()


class TestTheGuardedWrite:
    async def test_a_co_member_share_lands_once(self, graph: Any) -> None:
        sharing, backend = graph
        first = await sharing.share(EntityUID(ENTRY), ALICE, CAROL)
        again = await sharing.share(EntityUID(ENTRY), ALICE, CAROL)
        assert first.is_ok and first.value is True
        assert again.is_ok and again.value is False
        assert await _shares_with_count(backend) == 1

    async def test_the_default_group_owner_may_be_shared_with(self, graph: Any) -> None:
        sharing, backend = graph
        result = await sharing.share(EntityUID(ENTRY), ALICE, ADMIN)
        assert result.is_ok, result.error
        assert await _shares_with_count(backend) == 1

    @pytest.mark.parametrize("recipient", [BOB, DAVE, ERIN, "user_does_not_exist"])
    async def test_the_statement_refuses_what_the_read_refuses(
        self, graph: Any, recipient: str
    ) -> None:
        """Validation and the write are separate operations; the MERGE carries
        the same predicate so a change in between never lands an edge."""
        sharing, backend = graph
        result = await sharing.share(EntityUID(ENTRY), ALICE, recipient)
        assert result.is_error
        assert result.expect_error().category.value == "not_found"
        assert await _shares_with_count(backend) == 0

    async def test_the_owner_is_refused_by_the_statement_too(self, graph: Any) -> None:
        sharing, backend = graph
        result = await sharing.share(EntityUID(ENTRY), ALICE, ALICE)
        assert result.is_error
        assert await _shares_with_count(backend) == 0

    async def test_the_admin_exemption_bypasses_the_guard(self, graph: Any) -> None:
        """The forms' ``share_with_admin`` (ADR-088 §7) — the one writer that
        may reach a non-co-member."""
        sharing, backend = graph
        result = await sharing.share(EntityUID(ENTRY), ALICE, ERIN, require_co_membership=False)
        assert result.is_ok, result.error
        assert await _shares_with_count(backend) == 1

    async def test_the_guard_uses_the_owner_not_the_caller_label(self, graph: Any) -> None:
        """Ownership is checked first: a non-owner cannot use the guard to
        probe co-membership — the entity read is the not-found."""
        sharing, backend = graph
        result = await sharing.share(EntityUID(ENTRY), UserUID(CAROL), ALICE)
        assert result.is_error
        assert await _shares_with_count(backend) == 0
