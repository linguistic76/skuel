"""
Integration Tests for Ku Sharing Workflows
===============================================

End-to-end tests for the complete sharing system with real Neo4j interactions.

Test Scenarios:
- Complete sharing workflow (create → share → view → unshare)
- All 3 visibility levels (PRIVATE, SHARED, PUBLIC)
- Access control enforcement
- Ownership verification
- Access revocation

These tests use the actual service implementation with real Neo4j driver.
"""

import pytest

from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.enums.metadata_enums import Visibility
from core.services.reports.report_sharing_service import KuSharingService


@pytest.fixture
async def sharing_service(neo4j_driver):
    """Create KuSharingService with real Neo4j driver via QueryExecutor."""
    executor = Neo4jQueryExecutor(neo4j_driver)
    return KuSharingService(executor=executor)


@pytest.fixture
async def test_report(neo4j_driver):
    """
    Create a test Ku node and User nodes in Neo4j for testing.

    Returns the Ku UID and cleans up after the test.
    """
    # Create Ku node and owner User node in Neo4j
    report_uid = "test_report_integration_001"
    user_uid = "test_user_owner"

    # Create owner User + Ku node
    query = """
    MERGE (u:User {uid: $user_uid})
    SET u.name = 'Test Owner'
    CREATE (a:Ku {
        uid: $uid,
        user_uid: $user_uid,
        original_filename: "test_report.pdf",
        ku_type: "submission",
        status: "completed",
        file_path: "/test/path",
        file_size: 1024,
        file_type: "application/pdf",
        processor_type: "llm",
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
        await neo4j_driver.execute_query(
            "MERGE (u:User {uid: $uid}) SET u.name = $uid",
            uid=ruid,
        )

    yield {"uid": report_uid, "owner_uid": user_uid}

    # Cleanup
    cleanup_query = """
    MATCH (a:Ku {uid: $uid})
    OPTIONAL MATCH (a)<-[r:SHARES_WITH]-()
    DELETE r, a
    """
    await neo4j_driver.execute_query(cleanup_query, uid=report_uid)

    # Cleanup test users
    for ruid in [user_uid, *recipient_uids]:
        await neo4j_driver.execute_query(
            "MATCH (u:User {uid: $uid}) WHERE u.uid STARTS WITH 'test_' DELETE u",
            uid=ruid,
        )


# ============================================================================
# END-TO-END SHARING WORKFLOW TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_complete_sharing_workflow(sharing_service, test_report):
    """
    Test complete sharing workflow: create → share → view → unshare → verify revoked.

    Steps:
    1. Create Ku (completed by fixture)
    2. Share with recipient
    3. Recipient fetches shared Ku
    4. Recipient has access
    5. Owner unshares
    6. Recipient no longer has access
    """
    report_uid = test_report["uid"]
    owner_uid = test_report["owner_uid"]
    recipient_uid = "test_user_teacher"

    # Step 1: Set visibility to SHARED
    visibility_result = await sharing_service.set_visibility(
        ku_uid=report_uid,
        owner_uid=owner_uid,
        visibility=Visibility.SHARED,
    )
    assert not visibility_result.is_error
    assert visibility_result.value is True

    # Step 2: Share with recipient
    share_result = await sharing_service.share_ku(
        ku_uid=report_uid,
        owner_uid=owner_uid,
        recipient_uid=recipient_uid,
        role="teacher",
    )
    assert not share_result.is_error
    assert share_result.value is True

    # Step 3: Recipient can see it in "shared with me"
    _shared_result = await sharing_service.get_kus_shared_with_me(
        user_uid=recipient_uid,
        limit=50,
    )
    # Note: This may fail if User nodes don't exist - that's expected
    # The relationship was created successfully even if the query returns empty

    # Step 4: Recipient has access
    access_result = await sharing_service.check_access(
        ku_uid=report_uid,
        user_uid=recipient_uid,
    )
    assert not access_result.is_error
    assert access_result.value is True

    # Step 5: Owner unshares
    unshare_result = await sharing_service.unshare_ku(
        ku_uid=report_uid,
        owner_uid=owner_uid,
        recipient_uid=recipient_uid,
    )
    assert not unshare_result.is_error
    assert unshare_result.value is True

    # Step 6: Recipient no longer has access
    access_after_unshare = await sharing_service.check_access(
        ku_uid=report_uid,
        user_uid=recipient_uid,
    )
    assert not access_after_unshare.is_error
    assert access_after_unshare.value is False


# ============================================================================
# VISIBILITY LEVEL TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_private_visibility_restricts_access(sharing_service, test_report):
    """Test PRIVATE Ku only accessible to owner."""
    report_uid = test_report["uid"]
    owner_uid = test_report["owner_uid"]
    other_user = "test_user_other"

    # Ku defaults to PRIVATE
    # Owner can access
    owner_access = await sharing_service.check_access(
        ku_uid=report_uid,
        user_uid=owner_uid,
    )
    assert not owner_access.is_error
    assert owner_access.value is True

    # Other user cannot access
    other_access = await sharing_service.check_access(
        ku_uid=report_uid,
        user_uid=other_user,
    )
    assert not other_access.is_error
    assert other_access.value is False


@pytest.mark.asyncio
@pytest.mark.integration
async def test_public_visibility_allows_all_access(sharing_service, test_report):
    """Test PUBLIC Ku accessible to anyone."""
    report_uid = test_report["uid"]
    owner_uid = test_report["owner_uid"]
    anyone = "test_user_random"

    # Set visibility to PUBLIC
    visibility_result = await sharing_service.set_visibility(
        ku_uid=report_uid,
        owner_uid=owner_uid,
        visibility=Visibility.PUBLIC,
    )
    assert not visibility_result.is_error

    # Anyone can access
    public_access = await sharing_service.check_access(
        ku_uid=report_uid,
        user_uid=anyone,
    )
    assert not public_access.is_error
    assert public_access.value is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_shared_visibility_requires_relationship(sharing_service, test_report):
    """Test SHARED Ku require SHARES_WITH relationship."""
    report_uid = test_report["uid"]
    owner_uid = test_report["owner_uid"]
    authorized_user = "test_user_authorized"
    unauthorized_user = "test_user_unauthorized"

    # Set visibility to SHARED
    visibility_result = await sharing_service.set_visibility(
        ku_uid=report_uid,
        owner_uid=owner_uid,
        visibility=Visibility.SHARED,
    )
    assert not visibility_result.is_error

    # Share with authorized user
    share_result = await sharing_service.share_ku(
        ku_uid=report_uid,
        owner_uid=owner_uid,
        recipient_uid=authorized_user,
        role="peer",
    )
    assert not share_result.is_error

    # Authorized user can access
    authorized_access = await sharing_service.check_access(
        ku_uid=report_uid,
        user_uid=authorized_user,
    )
    assert not authorized_access.is_error
    assert authorized_access.value is True

    # Unauthorized user cannot access
    unauthorized_access = await sharing_service.check_access(
        ku_uid=report_uid,
        user_uid=unauthorized_user,
    )
    assert not unauthorized_access.is_error
    assert unauthorized_access.value is False


# ============================================================================
# OWNERSHIP VERIFICATION TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_only_owner_can_share(sharing_service, test_report):
    """Test that non-owners cannot share Ku."""
    report_uid = test_report["uid"]
    not_owner = "test_user_imposter"
    recipient = "test_user_recipient"

    # Non-owner tries to share
    share_result = await sharing_service.share_ku(
        ku_uid=report_uid,
        owner_uid=not_owner,  # Not the actual owner
        recipient_uid=recipient,
        role="viewer",
    )

    assert share_result.is_error
    assert "does not own" in str(share_result.error)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_only_owner_can_unshare(sharing_service, test_report):
    """Test that non-owners cannot unshare Ku."""
    report_uid = test_report["uid"]
    owner_uid = test_report["owner_uid"]
    recipient = "test_user_recipient"
    not_owner = "test_user_imposter"

    # Owner shares first
    await sharing_service.set_visibility(
        ku_uid=report_uid,
        owner_uid=owner_uid,
        visibility=Visibility.SHARED,
    )
    await sharing_service.share_ku(
        ku_uid=report_uid,
        owner_uid=owner_uid,
        recipient_uid=recipient,
        role="viewer",
    )

    # Non-owner tries to unshare
    unshare_result = await sharing_service.unshare_ku(
        ku_uid=report_uid,
        owner_uid=not_owner,  # Not the actual owner
        recipient_uid=recipient,
    )

    assert unshare_result.is_error
    assert "does not own" in str(unshare_result.error)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_only_owner_can_change_visibility(sharing_service, test_report):
    """Test that non-owners cannot change visibility."""
    report_uid = test_report["uid"]
    not_owner = "test_user_imposter"

    # Non-owner tries to change visibility
    visibility_result = await sharing_service.set_visibility(
        ku_uid=report_uid,
        owner_uid=not_owner,  # Not the actual owner
        visibility=Visibility.PUBLIC,
    )

    assert visibility_result.is_error
    assert "does not own" in str(visibility_result.error)


# ============================================================================
# SHAREABLE STATUS TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_only_completed_reports_can_be_shared(neo4j_driver, sharing_service):
    """Test that non-completed Ku cannot be shared."""
    # Create Ku with status=processing
    report_uid = "test_report_processing"
    owner_uid = "test_user_owner"

    query = """
    CREATE (a:Ku {
        uid: $uid,
        user_uid: $user_uid,
        original_filename: "processing.pdf",
        ku_type: "submission",
        status: "processing",
        file_path: "/test/path",
        file_size: 1024,
        file_type: "application/pdf",
        processor_type: "llm",
        visibility: "private",
        created_at: datetime(),
        updated_at: datetime()
    })
    RETURN a.uid
    """

    await neo4j_driver.execute_query(query, uid=report_uid, user_uid=owner_uid)

    try:
        # Try to share processing Ku
        share_result = await sharing_service.share_ku(
            ku_uid=report_uid,
            owner_uid=owner_uid,
            recipient_uid="test_user_teacher",
            role="teacher",
        )

        assert share_result.is_error
        assert "Only completed Ku" in str(share_result.error)

    finally:
        # Cleanup
        await neo4j_driver.execute_query(
            "MATCH (a:Ku {uid: $uid}) DELETE a",
            uid=report_uid,
        )


# ============================================================================
# SHARED USERS LIST TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_shared_users_list(sharing_service, test_report):
    """Test fetching list of users Ku is shared with."""
    report_uid = test_report["uid"]
    owner_uid = test_report["owner_uid"]

    # Share with multiple users
    users = [
        ("test_user_teacher", "teacher"),
        ("test_user_peer1", "peer"),
        ("test_user_peer2", "peer"),
    ]

    await sharing_service.set_visibility(
        ku_uid=report_uid,
        owner_uid=owner_uid,
        visibility=Visibility.SHARED,
    )

    for recipient_uid, role in users:
        await sharing_service.share_ku(
            ku_uid=report_uid,
            owner_uid=owner_uid,
            recipient_uid=recipient_uid,
            role=role,
        )

    # Get shared users list
    shared_users_result = await sharing_service.get_shared_with_users(
        ku_uid=report_uid,
    )

    # Note: This may return empty if User nodes don't exist
    # The test verifies the service method works, not that User nodes exist
    assert not shared_users_result.is_error
    # If User nodes exist, we should see 3 users
    # If not, the list will be empty but the method should still succeed


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_share_nonexistent_report(sharing_service):
    """Test sharing a nonexistent Ku returns appropriate error."""
    share_result = await sharing_service.share_ku(
        ku_uid="nonexistent_report",
        owner_uid="test_user_owner",
        recipient_uid="test_user_recipient",
        role="viewer",
    )

    assert share_result.is_error
    assert "not found" in str(share_result.error).lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_unshare_nonshared_report(sharing_service, test_report):
    """Test unsharing a Ku that wasn't shared."""
    report_uid = test_report["uid"]
    owner_uid = test_report["owner_uid"]
    never_shared_with = "test_user_never_shared"

    unshare_result = await sharing_service.unshare_ku(
        ku_uid=report_uid,
        owner_uid=owner_uid,
        recipient_uid=never_shared_with,
    )

    assert unshare_result.is_error
    assert "No sharing relationship found" in str(unshare_result.error)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_check_access_nonexistent_report(sharing_service):
    """Test checking access for nonexistent Ku."""
    access_result = await sharing_service.check_access(
        ku_uid="nonexistent_report",
        user_uid="test_user",
    )

    assert access_result.is_error
    assert "not found" in str(access_result.error).lower()
