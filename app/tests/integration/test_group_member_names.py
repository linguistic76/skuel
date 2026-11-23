"""A group's members are named as a page names a user: display name, else username.

``GroupBackend.get_members`` — what ``GET /api/groups/{uid}/members`` answers through
``GroupService.get_members`` — reads each member's name off their node. A user's name is a
field of the User class (``display_name``, else ``title``, the username), so the read takes
it from those, as the teacher's roster read does: a key no field names would read null for
every user a door wrote.

Members join through the backend's own writer (``add_member``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.persistence.neo4j.backends.collab_backends import GroupBackend
from core.models.type_hints import UserUID
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

GROUP = "group.member-names"
OWNER = seed_user_uid("member_names_owner")
NAMED = seed_user_uid("member_names_named")  # holds a display name
UNNAMED = seed_user_uid("member_names_unnamed")  # holds only a username
_USERS = [OWNER, NAMED, UNNAMED]


@pytest_asyncio.fixture(loop_scope="session")
async def group(neo4j_driver: AsyncDriver) -> AsyncIterator[GroupBackend]:
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (owner:User {uid: $owner, title: 'member-names-owner'})
            CREATE (:User {uid: $named, title: 'member-names-named', display_name: 'Ada Named'})
            CREATE (:User {uid: $unnamed, title: 'member-names-unnamed'})
            CREATE (owner)-[:OWNS]->(:Group {uid: $group, name: 'Member names',
                                             owner_uid: $owner, is_active: true})
            """,
            owner=OWNER,
            named=NAMED,
            unnamed=UNNAMED,
            group=GROUP,
        )
    backend: GroupBackend = build_production_backends(neo4j_driver)["group_backend"]
    joined = datetime.now(UTC).isoformat()
    for uid in (NAMED, UNNAMED):
        added = await backend.add_member(GROUP, UserUID(uid), joined_at=joined)
        assert added.is_ok, added
    yield backend
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid = $group OR n.uid IN $users DETACH DELETE n",
            group=GROUP,
            users=_USERS,
        )


async def test_each_member_is_named_by_display_name_else_username(group: GroupBackend) -> None:
    members = await group.get_members(GROUP)

    assert members.is_ok, members
    assert {row["user_uid"]: row["user_name"] for row in members.value} == {
        NAMED: "Ada Named",
        UNNAMED: "member-names-unnamed",
    }
