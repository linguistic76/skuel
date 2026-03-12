"""
Integration tests for Askesis Core Service (Priority 1.1)
===========================================================

Tests CRUD operations for Askesis AI assistant instances.

Test Coverage:
- get_or_create_for_user(): Get/create Askesis instance
- create_askesis(): Create new instance
- get_askesis(): Get by UID
- get_user_askesis(): Get user's instance
- update_askesis(): Update settings
- delete_askesis(): Delete instance
- list_user_instances(): List user instances
- record_conversation(): Increment metrics
"""

import pytest

from core.models.askesis.askesis import Askesis
from core.models.askesis.askesis_request import (
    AskesisCreateRequest,
    AskesisUpdateRequest,
)
from core.models.enums import GuidanceMode
from core.models.enums.askesis_enums import QueryComplexity
from core.services.askesis.askesis_core_service import AskesisCoreService
from core.utils.uid_generator import UIDGenerator


@pytest.fixture
async def core_service(neo4j_driver):
    """Create AskesisCoreService for testing."""
    from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend

    backend = UniversalNeo4jBackend[Askesis](
        driver=neo4j_driver, label="Askesis", entity_class=Askesis
    )

    return AskesisCoreService(backend=backend)


@pytest.fixture
def test_user_uid() -> str:
    """Generate test user UID."""
    return UIDGenerator.generate_random_uid("user")


@pytest.mark.asyncio
async def test_get_or_create_for_user_creates_default(core_service, test_user_uid):
    """Test get_or_create_for_user creates default instance."""
    # Act
    result = await core_service.get_or_create_for_user(test_user_uid)

    # Assert
    assert result.is_ok
    askesis = result.value
    assert askesis.user_uid == test_user_uid
    assert askesis.name == "Askesis"
    assert askesis.version == "1.0"
    assert askesis.uid.startswith("askesis_")


@pytest.mark.asyncio
async def test_get_or_create_for_user_returns_existing(core_service, test_user_uid):
    """Test get_or_create_for_user returns existing instance."""
    # Arrange - create first instance
    first_result = await core_service.get_or_create_for_user(test_user_uid)
    assert first_result.is_ok
    first_uid = first_result.value.uid

    # Act - call again
    second_result = await core_service.get_or_create_for_user(test_user_uid)

    # Assert - returns same instance
    assert second_result.is_ok
    assert second_result.value.uid == first_uid


@pytest.mark.asyncio
async def test_create_askesis_with_custom_settings(core_service, test_user_uid):
    """Test create_askesis with custom settings."""
    # Arrange
    create_request = AskesisCreateRequest(
        name="My AI Assistant",
        version="2.0",
        preferred_guidance_mode=GuidanceMode.SOCRATIC,
        preferred_complexity_level=QueryComplexity.COMPLEX,
    )

    # Act
    result = await core_service.create_askesis(test_user_uid, create_request)

    # Assert
    assert result.is_ok
    askesis = result.value
    assert askesis.name == "My AI Assistant"
    assert askesis.version == "2.0"
    assert askesis.preferred_guidance_mode == GuidanceMode.SOCRATIC.value
    assert askesis.preferred_complexity_level == QueryComplexity.COMPLEX.value


@pytest.mark.asyncio
async def test_create_askesis_prevents_duplicates(core_service, test_user_uid):
    """Test create_askesis prevents duplicate instances per user."""
    # Arrange - create first instance
    create_request = AskesisCreateRequest(
        name="First Instance",
        version="1.0",
    )
    first_result = await core_service.create_askesis(test_user_uid, create_request)
    assert first_result.is_ok

    # Act - try to create second instance
    second_result = await core_service.create_askesis(test_user_uid, create_request)

    # Assert - should fail
    assert second_result.is_error
    assert "already has an Askesis instance" in second_result.error.message


@pytest.mark.asyncio
async def test_get_askesis_by_uid(core_service, test_user_uid):
    """Test get_askesis retrieves by UID."""
    # Arrange
    create_result = await core_service.get_or_create_for_user(test_user_uid)
    assert create_result.is_ok
    askesis_uid = create_result.value.uid

    # Act
    result = await core_service.get_askesis(askesis_uid)

    # Assert
    assert result.is_ok
    assert result.value.uid == askesis_uid


@pytest.mark.asyncio
async def test_get_askesis_not_found(core_service):
    """Test get_askesis returns error for non-existent UID."""
    # Act
    result = await core_service.get_askesis("askesis:nonexistent")

    # Assert
    assert result.is_error
    assert "not found" in result.error.message.lower()


@pytest.mark.asyncio
async def test_update_askesis_settings(core_service, test_user_uid):
    """Test update_askesis modifies settings."""
    # Arrange
    create_result = await core_service.get_or_create_for_user(test_user_uid)
    assert create_result.is_ok
    askesis_uid = create_result.value.uid

    update_request = AskesisUpdateRequest(
        name="Updated Assistant",
        preferred_guidance_mode=GuidanceMode.DIRECT,
        preferred_complexity_level=QueryComplexity.SIMPLE,
    )

    # Act
    result = await core_service.update_askesis(askesis_uid, update_request)

    # Assert
    assert result.is_ok
    updated = result.value
    assert updated.name == "Updated Assistant"
    assert updated.preferred_guidance_mode == GuidanceMode.DIRECT.value
    assert updated.preferred_complexity_level == QueryComplexity.SIMPLE.value


@pytest.mark.asyncio
async def test_delete_askesis(core_service, test_user_uid):
    """Test delete_askesis removes instance."""
    # Arrange
    create_result = await core_service.get_or_create_for_user(test_user_uid)
    assert create_result.is_ok
    askesis_uid = create_result.value.uid

    # Act
    delete_result = await core_service.delete_askesis(askesis_uid)

    # Assert
    assert delete_result.is_ok
    assert delete_result.value is True

    # Verify deleted
    get_result = await core_service.get_askesis(askesis_uid)
    assert get_result.is_error


@pytest.mark.asyncio
async def test_list_user_instances(core_service, test_user_uid):
    """Test list_user_instances returns all instances."""
    # Arrange
    create_result = await core_service.get_or_create_for_user(test_user_uid)
    assert create_result.is_ok

    # Act
    result = await core_service.list_user_instances(test_user_uid)

    # Assert
    assert result.is_ok
    instances = result.value
    assert len(instances) == 1
    assert instances[0].user_uid == test_user_uid


@pytest.mark.asyncio
async def test_record_conversation(core_service, test_user_uid):
    """Test record_conversation increments metrics."""
    # Arrange
    create_result = await core_service.get_or_create_for_user(test_user_uid)
    assert create_result.is_ok
    askesis_uid = create_result.value.uid
    initial_count = create_result.value.total_conversations

    # Act
    result = await core_service.record_conversation(askesis_uid)

    # Assert
    assert result.is_ok
    updated = result.value
    assert updated.total_conversations == initial_count + 1
    assert updated.last_interaction is not None


@pytest.mark.asyncio
async def test_get_user_askesis_alias(core_service, test_user_uid):
    """Test get_user_askesis is an alias for get_or_create_for_user."""
    # Act
    result = await core_service.get_user_askesis(test_user_uid)

    # Assert
    assert result.is_ok
    assert result.value.user_uid == test_user_uid
    assert result.value.uid.startswith("askesis_")
