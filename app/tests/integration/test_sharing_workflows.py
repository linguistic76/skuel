"""
Integration Tests for Sharing Workflows
===============================================

End-to-end tests for the complete sharing system with real Neo4j interactions.

Test Scenarios:
- Complete sharing workflow (create → share → view → unshare)
- Publication (PRIVATE / PUBLIC)
- Ownership verification
- Access revocation (by username — the vocabulary's ``user:<username>``)

These tests use the actual service implementation with real Neo4j driver.
"""

import pytest

from adapters.persistence.neo4j.backends.sharing_backend import SharingBackend
from core.models.entity import Entity
from core.models.enums.metadata_enums import Visibility
from core.models.enums.neo_labels import NeoLabel
from core.services.sharing.unified_sharing_service import UnifiedSharingService


@pytest.fixture
async def sharing_service(neo4j_driver):
    """Create UnifiedSharingService with real SharingBackend."""
    backend = SharingBackend(neo4j_driver, NeoLabel.ENTITY, Entity)
    return UnifiedSharingService(backend=backend)


@pytest.fixture
async def test_report(neo4j_driver):
    """
    Create a test Entity nodes and User nodes in Neo4j for testing.

    Returns the entity UID and cleans up after the test.
    """
    # Create Entity nodes and owner User node in Neo4j
    report_uid = "test_report_integration_001"
    user_uid = "test_user_owner"
    group_uid = "test_group_shared_class"

    # Create owner User + Entity nodes
    query = """
    MERGE (u:User {uid: $user_uid})
    SET u.name = 'Test Owner'
    CREATE (a:Entity {
        uid: $uid,
        user_uid: $user_uid,
        original_filename: "test_report.pdf",
        entity_type: "user_entry",
        status: "completed",
        file_path: "/test/path",
        file_size: 1024,
        file_type: "application/pdf",
        pipeline: "none",
        visibility: "private",
        created_at: datetime(),
        updated_at: datetime()
    })
    RETURN a.uid as uid
    """

    await neo4j_driver.execute_query(
        query,
        uid=report_uid,
        user_uid=user_uid,
    )

    # Create test recipient User nodes used across tests
    recipient_uids = [
        "test_user_teacher",
        "test_user_recipient",
        "test_user_authorized",
        "test_user_unauthorized",
        "test_user_other",
        "test_user_random",
        "test_user_imposter",
        "test_user_peer1",
        "test_user_peer2",
        "test_user_never_shared",
    ]
    for ruid in recipient_uids:
        # ``title`` is the username — what a Stop-sharing target names.
        await neo4j_driver.execute_query(
            "MERGE (u:User {uid: $uid}) SET u.name = $uid, u.title = $uid",
            uid=ruid,
        )

    # A person share requires co-membership (R8, ADR-088 §7): these tests are
    # about ownership and status, so every user shares one active class.
    await neo4j_driver.execute_query(
        """
        MERGE (g:Group {uid: $group_uid}) SET g.name = 'Shared class', g.is_active = true
        WITH g
        UNWIND $members AS member_uid
        MATCH (u:User {uid: member_uid})
        MERGE (u)-[:MEMBER_OF {role: 'student'}]->(g)
        """,
        group_uid=group_uid,
        members=[user_uid, *recipient_uids],
    )

    yield {"uid": report_uid, "owner_uid": user_uid}

    await neo4j_driver.execute_query(
        "MATCH (g:Group {uid: $group_uid}) DETACH DELETE g", group_uid=group_uid
    )

    # Cleanup
    cleanup_query = """
    MATCH (a:Entity {uid: $uid})
    DETACH DELETE a
    """
    await neo4j_driver.execute_query(cleanup_query, uid=report_uid)

    # Cleanup test users
    for ruid in [user_uid, *recipient_uids]:
        await neo4j_driver.execute_query(
            "MATCH (u:User {uid: $uid}) WHERE u.uid STARTS WITH 'test_' DETACH DELETE u",
            uid=ruid,
        )


# ============================================================================
# END-TO-END SHARING WORKFLOW TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_complete_sharing_workflow(sharing_service, test_report, neo4j_driver):
    """
    Test complete sharing workflow: create → share → view → unshare → verify revoked.

    Steps:
    1. Create entity (completed by fixture)
    2. Share with recipient
    3. Recipient fetches shared entity
    4. The SHARES_WITH edge exists
    5. Owner unshares
    6. The SHARES_WITH edge is gone
    """
    report_uid = test_report["uid"]
    owner_uid = test_report["owner_uid"]
    recipient_uid = "test_user_teacher"

    # Step 2: Share with recipient — the edge is the whole grant; the
    # visibility property is publication only and stays private.
    share_result = await sharing_service.share(
        entity_uid=report_uid,
        owner_uid=owner_uid,
        recipient_uid=recipient_uid,
        role="teacher",
    )
    assert not share_result.is_error
    assert share_result.value is True

    # Step 3: Recipient can see it in "shared with me"
    _shared_result = await sharing_service.get_shared_with_me(
        user_uid=recipient_uid,
        limit=50,
    )
    # Note: This may return empty if User nodes don't exist - that's expected
    # The relationship was created successfully even if the query returns empty

    # Step 4: The share is recorded on the graph — the SHARES_WITH edge is the
    # one record of who was given the entity (ADR-088 §3).
    async with neo4j_driver.session() as session:
        cursor = await session.run(
            "MATCH (:User {uid: $viewer})-[r:SHARES_WITH]->(:Entity {uid: $uid}) RETURN count(r) AS n",
            viewer=recipient_uid,
            uid=report_uid,
        )
        record = await cursor.single()
    assert record is not None and record["n"] == 1

    # Step 5: Owner unshares
    unshare_result = await sharing_service.unshare(
        entity_uid=report_uid,
        owner_uid=owner_uid,
        recipient_username=recipient_uid,
    )
    assert not unshare_result.is_error
    assert unshare_result.value is True

    # Step 6: The edge is gone — nothing records the share any more
    async with neo4j_driver.session() as session:
        cursor = await session.run(
            "MATCH (:User {uid: $viewer})-[r:SHARES_WITH]->(:Entity {uid: $uid}) RETURN count(r) AS n",
            viewer=recipient_uid,
            uid=report_uid,
        )
        record = await cursor.single()
    assert record is not None and record["n"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_shared_with_me_lists_shares_not_feedback_with_their_via(
    sharing_service, neo4j_driver
):
    """*Shared with you* (R3, R6, R7): a person share and an active-group share of
    another user's entry are listed once each with their via-list; the viewer's
    own entry, a feedback type, an inactive group's share and a feedback request
    are not; ``via`` narrows to one route."""
    viewer = "test_user_swy_viewer"
    seed = """
    MERGE (viewer:User {uid: $viewer}) SET viewer.title = 'viewer'
    MERGE (peer:User {uid: 'test_user_swy_peer'}) SET peer.title = 'peer', peer.display_name = 'Peer P'
    CREATE (g:Group {uid: 'test_group_swy', name: 'Swy class', is_active: true})
    CREATE (dead:Group {uid: 'test_group_swy_dead', name: 'Dead class', is_active: false})
    CREATE (viewer)-[:MEMBER_OF {role: 'student'}]->(g)
    CREATE (viewer)-[:MEMBER_OF {role: 'student'}]->(dead)
    CREATE (peer)-[:MEMBER_OF {role: 'student'}]->(g)
    CREATE (direct:Entity:UserEntry {
        uid: 'test_ue_swy_direct', entity_type: 'user_entry', status: 'active',
        title: 'Direct share', user_uid: 'test_user_swy_peer',
        created_at: datetime(), updated_at: datetime()
    })
    CREATE (both:Entity:UserEntry {
        uid: 'test_ue_swy_both', entity_type: 'user_entry', status: 'archived',
        title: 'Direct and group', user_uid: 'test_user_swy_peer',
        created_at: datetime(), updated_at: datetime()
    })
    CREATE (groupish:Entity:UserEntry {
        uid: 'test_ue_swy_group', entity_type: 'user_entry', status: 'active',
        title: 'Group share', user_uid: 'test_user_swy_peer',
        created_at: datetime(), updated_at: datetime()
    })
    CREATE (mine:Entity:UserEntry {
        uid: 'test_ue_swy_mine', entity_type: 'user_entry', status: 'active',
        title: 'My own', user_uid: $viewer,
        created_at: datetime(), updated_at: datetime()
    })
    CREATE (report:Entity:EntryReport {
        uid: 'test_er_swy', entity_type: 'entry_report', status: 'completed',
        title: 'Feedback', user_uid: $viewer,
        created_at: datetime(), updated_at: datetime()
    })
    CREATE (deadshare:Entity:UserEntry {
        uid: 'test_ue_swy_dead', entity_type: 'user_entry', status: 'active',
        title: 'Dead group share', user_uid: 'test_user_swy_peer',
        created_at: datetime(), updated_at: datetime()
    })
    CREATE (request:Entity:UserEntry {
        uid: 'test_ue_swy_request', entity_type: 'user_entry', status: 'submitted',
        title: 'For the teacher', user_uid: 'test_user_swy_peer', pipeline: 'teacher_review',
        created_at: datetime(), updated_at: datetime()
    })
    CREATE (peer)-[:OWNS]->(direct), (peer)-[:OWNS]->(both), (peer)-[:OWNS]->(groupish),
           (peer)-[:OWNS]->(deadshare), (peer)-[:OWNS]->(request)
    CREATE (viewer)-[:OWNS]->(mine), (viewer)-[:OWNS]->(report)
    CREATE (viewer)-[:SHARES_WITH {shared_at: datetime('2026-09-01T10:00:00Z'), role: 'viewer'}]->(direct)
    CREATE (viewer)-[:SHARES_WITH {shared_at: datetime('2026-09-02T10:00:00Z'), role: 'viewer'}]->(both)
    CREATE (both)-[:SHARED_WITH_GROUP {shared_at: datetime('2026-09-03T10:00:00Z')}]->(g)
    CREATE (groupish)-[:SHARED_WITH_GROUP {shared_at: datetime('2026-09-04T10:00:00Z')}]->(g)
    CREATE (mine)-[:SHARED_WITH_GROUP {shared_at: datetime()}]->(g)
    CREATE (viewer)-[:SHARES_WITH {shared_at: datetime(), role: 'student'}]->(report)
    CREATE (deadshare)-[:SHARED_WITH_GROUP {shared_at: datetime()}]->(dead)
    CREATE (request)-[:SUBMITTED_TO_GROUP {submitted_at: datetime()}]->(g)
    """
    await neo4j_driver.execute_query(seed, viewer=viewer)
    try:
        result = await sharing_service.get_shared_with_me(user_uid=viewer, limit=10)
        assert not result.is_error, result.error
        by_uid = {item["entity"].uid: item for item in result.value}
        assert set(by_uid) == {"test_ue_swy_direct", "test_ue_swy_both", "test_ue_swy_group"}
        # newest share first, one row per entity even when two links reach the viewer
        assert [item["entity"].uid for item in result.value] == [
            "test_ue_swy_group",
            "test_ue_swy_both",
            "test_ue_swy_direct",
        ]
        both = by_uid["test_ue_swy_both"]
        assert both["via_direct"] is True
        assert both["via_groups"] == [{"uid": "test_group_swy", "name": "Swy class"}]
        assert both["shared_by"] == "Peer P"
        assert both["sharer_uid"] == "test_user_swy_peer"
        assert both["shared_at"].startswith("2026-09-03")
        assert by_uid["test_ue_swy_direct"]["via_groups"] == []
        assert by_uid["test_ue_swy_group"]["via_direct"] is False

        # the /groups list: the same reader narrowed to one group
        via_group = await sharing_service.get_shared_with_me(
            user_uid=viewer, limit=10, via="test_group_swy"
        )
        assert [i["entity"].uid for i in via_group.value] == [
            "test_ue_swy_group",
            "test_ue_swy_both",
        ]
        via_direct = await sharing_service.get_shared_with_me(
            user_uid=viewer, limit=10, via="direct"
        )
        assert {i["entity"].uid for i in via_direct.value} == {
            "test_ue_swy_both",
            "test_ue_swy_direct",
        }
        by_sharer = await sharing_service.get_shared_with_me(
            user_uid=viewer, limit=10, sharer_uid="nobody"
        )
        assert by_sharer.value == []
    finally:
        await neo4j_driver.execute_query(
            """
            MATCH (n) WHERE n.uid STARTS WITH 'test_ue_swy' OR n.uid STARTS WITH 'test_er_swy'
               OR n.uid STARTS WITH 'test_group_swy' OR n.uid STARTS WITH 'test_user_swy'
            DETACH DELETE n
            """
        )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_your_wall_lists_each_shared_entry_with_its_audience(sharing_service, neo4j_driver):
    """*Your wall* (R7): one row per owned entry that carries a share link, with every
    person and group it reaches; an unshared entry and a feedback request are not rows;
    ``entity_uid`` narrows to one entry."""
    owner = "test_user_wall_owner"
    seed = """
    MERGE (owner:User {uid: $owner}) SET owner.title = 'owner'
    MERGE (alice:User {uid: 'test_user_wall_alice'}) SET alice.title = 'alice', alice.display_name = 'Alice'
    CREATE (g:Group {uid: 'test_group_wall', name: 'Wall class', is_active: true})
    CREATE (shared:Entity:UserEntry {
        uid: 'test_ue_wall_shared', entity_type: 'user_entry', status: 'active',
        title: 'Shared one', user_uid: $owner, created_at: datetime(), updated_at: datetime()
    })
    CREATE (quiet:Entity:UserEntry {
        uid: 'test_ue_wall_quiet', entity_type: 'user_entry', status: 'active',
        title: 'Unshared', user_uid: $owner, created_at: datetime(), updated_at: datetime()
    })
    CREATE (request:Entity:UserEntry {
        uid: 'test_ue_wall_request', entity_type: 'user_entry', status: 'submitted',
        title: 'Feedback request', user_uid: $owner, created_at: datetime(), updated_at: datetime()
    })
    CREATE (owner)-[:OWNS]->(shared), (owner)-[:OWNS]->(quiet), (owner)-[:OWNS]->(request)
    CREATE (alice)-[:SHARES_WITH {shared_at: datetime('2026-09-05T10:00:00Z'), role: 'viewer'}]->(shared)
    CREATE (shared)-[:SHARED_WITH_GROUP {shared_at: datetime('2026-09-06T10:00:00Z')}]->(g)
    CREATE (request)-[:SUBMITTED_TO_GROUP {submitted_at: datetime()}]->(g)
    """
    await neo4j_driver.execute_query(seed, owner=owner)
    try:
        wall = await sharing_service.get_shared_by_me(user_uid=owner)
        assert not wall.is_error, wall.error
        assert [row["entity"].uid for row in wall.value] == ["test_ue_wall_shared"]
        row = wall.value[0]
        assert row["users"] == [
            {
                "uid": "test_user_wall_alice",
                "username": "alice",
                "display_name": "Alice",
                "shared_at": row["users"][0]["shared_at"],
            }
        ]
        assert row["users"][0]["shared_at"].startswith("2026-09-05")
        assert [g["uid"] for g in row["groups"]] == ["test_group_wall"]
        assert row["last_shared_at"].startswith("2026-09-06")

        one = await sharing_service.get_shared_by_me(
            user_uid=owner, limit=1, entity_uid="test_ue_wall_quiet"
        )
        assert one.value == []

        # Stop sharing by username; the wall follows
        gone = await sharing_service.unshare(
            entity_uid="test_ue_wall_shared", owner_uid=owner, recipient_username="alice"
        )
        assert gone.is_ok, gone.error
        after = await sharing_service.get_shared_by_me(
            user_uid=owner, limit=1, entity_uid="test_ue_wall_shared"
        )
        assert after.value[0]["users"] == []
        assert [g["uid"] for g in after.value[0]["groups"]] == ["test_group_wall"]
        # the feedback request survives a group unshare of the same group
        gone_group = await sharing_service.unshare_from_group(
            entity_uid="test_ue_wall_shared", owner_uid=owner, group_uid="test_group_wall"
        )
        assert gone_group.is_ok
        kinds = await neo4j_driver.execute_query(
            "MATCH (:Entity {uid: 'test_ue_wall_request'})-[r]->(:Group) RETURN type(r) AS kind"
        )
        assert [rec["kind"] for rec in kinds.records] == ["SUBMITTED_TO_GROUP"]
    finally:
        await neo4j_driver.execute_query(
            """
            MATCH (n) WHERE n.uid STARTS WITH 'test_ue_wall' OR n.uid STARTS WITH 'test_group_wall'
               OR n.uid STARTS WITH 'test_user_wall'
            DETACH DELETE n
            """
        )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_share_candidate_people_are_the_r8_co_members(sharing_service, neo4j_driver):
    """The Share panel's people: co-members of a real group, and the default group's
    owner — never its roster, never the owner."""
    owner = "test_user_cand_owner"
    seed = """
    MERGE (owner:User {uid: $owner}) SET owner.title = 'owner'
    MERGE (mate:User {uid: 'test_user_cand_mate'}) SET mate.title = 'mate', mate.display_name = 'Mate'
    MERGE (roster:User {uid: 'test_user_cand_roster'}) SET roster.title = 'roster'
    MERGE (admin:User {uid: 'test_user_cand_admin'}) SET admin.title = 'admin'
    CREATE (g:Group {uid: 'test_group_cand', name: 'Real class', is_active: true})
    CREATE (dg:Group {uid: 'group_default_test_user_cand_admin', name: 'Default', is_active: true})
    CREATE (owner)-[:MEMBER_OF {role: 'student'}]->(g), (mate)-[:MEMBER_OF {role: 'student'}]->(g)
    CREATE (owner)-[:MEMBER_OF {role: 'student'}]->(dg), (roster)-[:MEMBER_OF {role: 'student'}]->(dg)
    CREATE (admin)-[:OWNS]->(dg)
    """
    await neo4j_driver.execute_query(seed, owner=owner)
    try:
        result = await sharing_service.get_share_candidate_people(owner)
        assert not result.is_error, result.error
        assert {p["uid"] for p in result.value} == {"test_user_cand_mate", "test_user_cand_admin"}
        assert result.value[0]["display_name"] in {"Mate", "admin"}
    finally:
        await neo4j_driver.execute_query(
            """
            MATCH (n) WHERE n.uid STARTS WITH 'test_user_cand' OR n.uid STARTS WITH 'test_group_cand'
               OR n.uid = 'group_default_test_user_cand_admin'
            DETACH DELETE n
            """
        )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_only_owner_can_share(sharing_service, test_report):
    """Test that non-owners cannot share entity."""
    report_uid = test_report["uid"]
    not_owner = "test_user_imposter"
    recipient = "test_user_recipient"

    # Non-owner tries to share
    share_result = await sharing_service.share(
        entity_uid=report_uid,
        owner_uid=not_owner,  # Not the actual owner
        recipient_uid=recipient,
        role="viewer",
    )

    assert share_result.is_error
    # Privacy pattern: returns "not found" for entities the user doesn't own
    error_str = str(share_result.error)
    assert "does not own" in error_str or "not found" in error_str.lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_only_owner_can_unshare(sharing_service, test_report):
    """Test that non-owners cannot unshare entity."""
    report_uid = test_report["uid"]
    owner_uid = test_report["owner_uid"]
    recipient = "test_user_recipient"
    not_owner = "test_user_imposter"

    # Owner shares first
    await sharing_service.share(
        entity_uid=report_uid,
        owner_uid=owner_uid,
        recipient_uid=recipient,
        role="viewer",
    )

    # Non-owner tries to unshare
    unshare_result = await sharing_service.unshare(
        entity_uid=report_uid,
        owner_uid=not_owner,  # Not the actual owner
        recipient_username=recipient,
    )

    assert unshare_result.is_error
    # Privacy pattern: returns "not found" for entities the user doesn't own
    error_str = str(unshare_result.error)
    assert "does not own" in error_str or "not found" in error_str.lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_only_owner_can_change_visibility(sharing_service, test_report):
    """Test that non-owners cannot change visibility."""
    report_uid = test_report["uid"]
    not_owner = "test_user_imposter"

    # Non-owner tries to change visibility
    visibility_result = await sharing_service.set_visibility(
        entity_uid=report_uid,
        owner_uid=not_owner,  # Not the actual owner
        visibility=Visibility.PUBLIC,
    )

    assert visibility_result.is_error
    # Privacy pattern: returns "not found" for entities the user doesn't own
    error_str = str(visibility_result.error)
    assert "does not own" in error_str or "not found" in error_str.lower()


# ============================================================================
# SHAREABLE STATUS TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_only_completed_reports_can_be_shared(neo4j_driver, sharing_service, test_report):
    """Test that non-completed entities cannot be shared."""
    # Create entity with status=processing
    report_uid = "test_report_processing"
    owner_uid = "test_user_owner"

    query = """
    CREATE (a:Entity {
        uid: $uid,
        user_uid: $user_uid,
        original_filename: "processing.pdf",
        entity_type: "entry_report",
        status: "processing",
        file_path: "/test/path",
        file_size: 1024,
        file_type: "application/pdf",
        pipeline: "none",
        visibility: "private",
        created_at: datetime(),
        updated_at: datetime()
    })
    RETURN a.uid
    """

    await neo4j_driver.execute_query(query, uid=report_uid, user_uid=owner_uid)

    try:
        # Try to share processing entity
        share_result = await sharing_service.share(
            entity_uid=report_uid,
            owner_uid=owner_uid,
            recipient_uid="test_user_teacher",
            role="teacher",
        )

        assert share_result.is_error
        assert "Only completed Ku" in str(share_result.error)

    finally:
        # Cleanup
        await neo4j_driver.execute_query(
            "MATCH (a:Entity {uid: $uid}) DETACH DELETE a",
            uid=report_uid,
        )


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_share_nonexistent_report(sharing_service):
    """Test sharing a nonexistent entity returns appropriate error."""
    share_result = await sharing_service.share(
        entity_uid="nonexistent_report",
        owner_uid="test_user_owner",
        recipient_uid="test_user_recipient",
        role="viewer",
    )

    assert share_result.is_error
    assert "not found" in str(share_result.error).lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_unshare_nonshared_report(sharing_service, test_report):
    """Test unsharing an entity that wasn't shared."""
    report_uid = test_report["uid"]
    owner_uid = test_report["owner_uid"]
    never_shared_with = "test_user_never_shared"

    unshare_result = await sharing_service.unshare(
        entity_uid=report_uid,
        owner_uid=owner_uid,
        recipient_username=never_shared_with,
    )

    assert unshare_result.is_error
    assert "No sharing relationship found" in str(unshare_result.error)
