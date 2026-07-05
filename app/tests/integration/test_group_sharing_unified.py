"""
Unified Group Sharing Integration Tests
========================================

End-to-end: teacher creates a group, shares curriculum (Exercise, PathStep,
LearningPath) with it via UnifiedSharingService, and we verify:

1. All three curriculum types produce SHARED_WITH_GROUP edges.
2. No FOR_GROUP edges exist in the graph (legacy retired, ADR-053).
3. Students who are group members are reachable via the shared path.

See: ADR-053
"""

import pytest

from adapters.persistence.neo4j.backends.sharing_backend import SharingBackend
from core.models.entity import Entity
from core.models.enums.neo_labels import NeoLabel
from core.services.sharing.unified_sharing_service import UnifiedSharingService


@pytest.fixture
async def sharing_service(neo4j_driver):
    backend = SharingBackend(neo4j_driver, NeoLabel.ENTITY, Entity)
    return UnifiedSharingService(backend=backend)


@pytest.fixture
async def curriculum_group_fixture(neo4j_driver):
    """Create a teacher-owned group + one exercise, path_step, learning_path."""
    teacher_uid = "test_unified_sharing_teacher"
    student_uid = "test_unified_sharing_student"
    group_uid = "group_unified_sharing_test"

    entities = {
        "exercise": "ex_unified_sharing_test",
        "path_step": "ps_unified_sharing_test",
        "learning_path": "lp_unified_sharing_test",
    }

    # Create users, group, and curriculum entities authored by the teacher
    await neo4j_driver.execute_query(
        """
        MERGE (t:User {uid: $teacher_uid}) SET t.name = 'Teacher'
        MERGE (s:User {uid: $student_uid}) SET s.name = 'Student'
        MERGE (g:Group {uid: $group_uid})
          SET g.name = 'Unified Sharing Test',
              g.owner_uid = $teacher_uid,
              g.is_active = true
        MERGE (t)-[:OWNS]->(g)
        MERGE (s)-[:MEMBER_OF {role: 'student', joined_at: datetime()}]->(g)
        """,
        teacher_uid=teacher_uid,
        student_uid=student_uid,
        group_uid=group_uid,
    )

    for entity_type, uid in entities.items():
        await neo4j_driver.execute_query(
            """
            MERGE (e:Entity {uid: $uid})
              SET e.entity_type = $etype,
                  e.title = $title,
                  e.status = 'active',
                  e.user_uid = $teacher_uid,
                  e.created_at = datetime(),
                  e.updated_at = datetime()
            """,
            uid=uid,
            etype=entity_type,
            title=f"Test {entity_type}",
            teacher_uid=teacher_uid,
        )

    yield {
        "teacher_uid": teacher_uid,
        "student_uid": student_uid,
        "group_uid": group_uid,
        "entities": entities,
    }

    # Cleanup
    await neo4j_driver.execute_query(
        """
        UNWIND $uids AS uid
        OPTIONAL MATCH (e:Entity {uid: uid})
        DETACH DELETE e
        """,
        uids=list(entities.values()),
    )
    await neo4j_driver.execute_query("MATCH (g:Group {uid: $uid}) DETACH DELETE g", uid=group_uid)
    await neo4j_driver.execute_query(
        "MATCH (u:User) WHERE u.uid IN $uids DETACH DELETE u",
        uids=[teacher_uid, student_uid],
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_share_all_curriculum_types_with_group(
    sharing_service, curriculum_group_fixture, neo4j_driver
):
    ctx = curriculum_group_fixture
    teacher_uid = ctx["teacher_uid"]
    group_uid = ctx["group_uid"]

    # Share all three curriculum entity types with the group
    for entity_uid in ctx["entities"].values():
        result = await sharing_service.share_with_group(
            entity_uid=entity_uid,
            owner_uid=teacher_uid,
            group_uid=group_uid,
            share_version="original",
        )
        assert result.is_ok, f"share_with_group failed for {entity_uid}: {result.error}"

    # All three SHARED_WITH_GROUP edges exist
    count_result = await neo4j_driver.execute_query(
        """
        MATCH (e:Entity)-[r:SHARED_WITH_GROUP]->(g:Group {uid: $group_uid})
        WHERE e.uid IN $uids
        RETURN count(r) as c
        """,
        group_uid=group_uid,
        uids=list(ctx["entities"].values()),
    )
    records = count_result.records
    assert records[0]["c"] == 3

    # Metadata populated (shared_at + share_version)
    meta_result = await neo4j_driver.execute_query(
        """
        MATCH (e:Entity)-[r:SHARED_WITH_GROUP]->(g:Group {uid: $group_uid})
        WHERE e.uid IN $uids
        RETURN r.shared_at IS NOT NULL as has_shared_at,
               r.share_version as version
        """,
        group_uid=group_uid,
        uids=list(ctx["entities"].values()),
    )
    for row in meta_result.records:
        assert row["has_shared_at"] is True
        assert row["version"] == "original"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_for_group_edges_never_produced(
    sharing_service, curriculum_group_fixture, neo4j_driver
):
    """Regression: sharing through the unified path must not emit FOR_GROUP."""
    ctx = curriculum_group_fixture
    for entity_uid in ctx["entities"].values():
        result = await sharing_service.share_with_group(
            entity_uid=entity_uid,
            owner_uid=ctx["teacher_uid"],
            group_uid=ctx["group_uid"],
            share_version="original",
        )
        assert result.is_ok

    for_group_result = await neo4j_driver.execute_query(
        """
        MATCH (e:Entity)-[r:FOR_GROUP]->(g:Group {uid: $group_uid})
        WHERE e.uid IN $uids
        RETURN count(r) as c
        """,
        group_uid=ctx["group_uid"],
        uids=list(ctx["entities"].values()),
    )
    assert for_group_result.records[0]["c"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_student_reachable_via_shared_curriculum(
    sharing_service, curriculum_group_fixture, neo4j_driver
):
    """A member of a target group is reachable from every shared curriculum entity."""
    ctx = curriculum_group_fixture
    for entity_uid in ctx["entities"].values():
        result = await sharing_service.share_with_group(
            entity_uid=entity_uid,
            owner_uid=ctx["teacher_uid"],
            group_uid=ctx["group_uid"],
            share_version="original",
        )
        assert result.is_ok

    reach_result = await neo4j_driver.execute_query(
        """
        MATCH (e:Entity)-[:SHARED_WITH_GROUP]->(g:Group)<-[:MEMBER_OF]-(u:User {uid: $student_uid})
        WHERE e.uid IN $uids
        RETURN collect(e.entity_type) as types
        """,
        student_uid=ctx["student_uid"],
        uids=list(ctx["entities"].values()),
    )
    types = set(reach_result.records[0]["types"])
    assert types == {"exercise", "path_step", "learning_path"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_share_with_group_rejects_non_member_non_owner(
    sharing_service, curriculum_group_fixture, neo4j_driver
):
    """A user who neither OWNS nor is MEMBER_OF the group cannot share into it,
    and the Cypher guard leaves the graph untouched."""
    ctx = curriculum_group_fixture
    stranger_uid = "test_unified_sharing_stranger"

    # Stranger user + their own entity (so the ownership check passes)
    stranger_entity_uid = "ue_stranger_attempt"
    await neo4j_driver.execute_query(
        """
        MERGE (u:User {uid: $user_uid})
        MERGE (e:Entity {uid: $entity_uid})
          SET e.entity_type = 'user_entry',
              e.status = 'completed',
              e.user_uid = $user_uid,
              e.created_at = datetime(),
              e.updated_at = datetime()
        """,
        user_uid=stranger_uid,
        entity_uid=stranger_entity_uid,
    )

    try:
        result = await sharing_service.share_with_group(
            entity_uid=stranger_entity_uid,
            owner_uid=stranger_uid,
            group_uid=ctx["group_uid"],
        )

        assert result.is_error
        assert result.expect_error().category.value == "forbidden"

        # No SHARED_WITH_GROUP edge was produced.
        check = await neo4j_driver.execute_query(
            """
            MATCH (e:Entity {uid: $entity_uid})-[r:SHARED_WITH_GROUP]->(g:Group {uid: $group_uid})
            RETURN count(r) as c
            """,
            entity_uid=stranger_entity_uid,
            group_uid=ctx["group_uid"],
        )
        assert check.records[0]["c"] == 0
    finally:
        await neo4j_driver.execute_query(
            "MATCH (e:Entity {uid: $uid}) DETACH DELETE e",
            uid=stranger_entity_uid,
        )
        await neo4j_driver.execute_query(
            "MATCH (u:User {uid: $uid}) DETACH DELETE u",
            uid=stranger_uid,
        )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_unshare_removes_edge(sharing_service, curriculum_group_fixture, neo4j_driver):
    ctx = curriculum_group_fixture
    entity_uid = ctx["entities"]["exercise"]

    share = await sharing_service.share_with_group(
        entity_uid=entity_uid,
        owner_uid=ctx["teacher_uid"],
        group_uid=ctx["group_uid"],
    )
    assert share.is_ok

    unshare = await sharing_service.unshare_from_group(
        entity_uid=entity_uid,
        owner_uid=ctx["teacher_uid"],
        group_uid=ctx["group_uid"],
    )
    assert unshare.is_ok

    count = await neo4j_driver.execute_query(
        """
        MATCH (e:Entity {uid: $uid})-[r:SHARED_WITH_GROUP]->(g:Group {uid: $group_uid})
        RETURN count(r) as c
        """,
        uid=entity_uid,
        group_uid=ctx["group_uid"],
    )
    assert count.records[0]["c"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_share_entity_owned_via_owns_edge_only(
    sharing_service, curriculum_group_fixture, neo4j_driver
):
    """Curriculum entities created through ExerciseService carry ownership as the
    canonical :OWNS edge (plus an owner_uid property) — no user_uid property.
    The ownership check must honor the edge, or ADR-040 assigned-exercise
    auto-share silently fails ("Entity not found" on a node that exists)."""
    ctx = curriculum_group_fixture
    teacher_uid = ctx["teacher_uid"]
    entity_uid = "ex_owns_edge_only_test"

    await neo4j_driver.execute_query(
        """
        MATCH (t:User {uid: $teacher_uid})
        MERGE (e:Entity {uid: $entity_uid})
          SET e.entity_type = 'exercise',
              e.title = 'OWNS-edge-only exercise',
              e.status = 'draft',
              e.owner_uid = $teacher_uid,
              e.created_at = datetime(),
              e.updated_at = datetime()
        MERGE (t)-[:OWNS]->(e)
        """,
        teacher_uid=teacher_uid,
        entity_uid=entity_uid,
    )

    try:
        result = await sharing_service.share_with_group(
            entity_uid=entity_uid,
            owner_uid=teacher_uid,
            group_uid=ctx["group_uid"],
            share_version="original",
        )
        assert result.is_ok, f"share_with_group failed: {result.error}"

        count = await neo4j_driver.execute_query(
            """
            MATCH (e:Entity {uid: $uid})-[r:SHARED_WITH_GROUP]->(g:Group {uid: $group_uid})
            RETURN count(r) as c
            """,
            uid=entity_uid,
            group_uid=ctx["group_uid"],
        )
        assert count.records[0]["c"] == 1
    finally:
        await neo4j_driver.execute_query(
            "MATCH (e:Entity {uid: $uid}) DETACH DELETE e", uid=entity_uid
        )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_share_owns_edge_ownership_mismatch_still_rejected(
    sharing_service, curriculum_group_fixture, neo4j_driver
):
    """The :OWNS fallback must not weaken the check: an entity owned (via edge)
    by someone else is still not_found for the requesting user."""
    ctx = curriculum_group_fixture
    entity_uid = "ex_owns_edge_mismatch_test"

    await neo4j_driver.execute_query(
        """
        MATCH (s:User {uid: $student_uid})
        MERGE (e:Entity {uid: $entity_uid})
          SET e.entity_type = 'exercise',
              e.status = 'draft',
              e.created_at = datetime(),
              e.updated_at = datetime()
        MERGE (s)-[:OWNS]->(e)
        """,
        student_uid=ctx["student_uid"],
        entity_uid=entity_uid,
    )

    try:
        result = await sharing_service.share_with_group(
            entity_uid=entity_uid,
            owner_uid=ctx["teacher_uid"],
            group_uid=ctx["group_uid"],
        )
        assert result.is_error
        assert result.expect_error().category.value == "not_found"
    finally:
        await neo4j_driver.execute_query(
            "MATCH (e:Entity {uid: $uid}) DETACH DELETE e", uid=entity_uid
        )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_share_entity_owner_uid_property_without_owns_edge(
    sharing_service, curriculum_group_fixture, neo4j_driver
):
    """ExerciseService.create warns (does not fail) when the :OWNS edge write
    fails, so owner_uid-property-without-edge can exist. Sharing must resolve
    it the same way verify_ownership does (Kody #511 finding, accepted) —
    otherwise the same node passes CRUD ownership but fails sharing."""
    ctx = curriculum_group_fixture
    teacher_uid = ctx["teacher_uid"]
    entity_uid = "ex_owner_prop_no_edge_test"

    await neo4j_driver.execute_query(
        """
        MERGE (e:Entity {uid: $entity_uid})
          SET e.entity_type = 'exercise',
              e.status = 'draft',
              e.owner_uid = $teacher_uid,
              e.created_at = datetime(),
              e.updated_at = datetime()
        """,
        teacher_uid=teacher_uid,
        entity_uid=entity_uid,
    )

    try:
        result = await sharing_service.share_with_group(
            entity_uid=entity_uid,
            owner_uid=teacher_uid,
            group_uid=ctx["group_uid"],
            share_version="original",
        )
        assert result.is_ok, f"share_with_group failed: {result.error}"
    finally:
        await neo4j_driver.execute_query(
            "MATCH (e:Entity {uid: $uid}) DETACH DELETE e", uid=entity_uid
        )
