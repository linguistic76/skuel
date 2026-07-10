"""
Quick test to verify the new type system is working correctly.
Run with: uv run pytest tests/test_type_system.py -v
"""

__version__ = "1.0"


import pytest

from core.models.type_hints import (
    EntityUID,
    TypeConverter,
    UserUID,
    cached_property,
    is_valid_percentage,
    is_valid_score,
    is_valid_uid,
)
from core.services.user import UserContext


def test_newtype_definitions():
    """Test that NewType definitions work correctly"""
    user_id = UserUID("user_123")
    entity_id = EntityUID("entity_456")

    assert isinstance(user_id, str)
    assert isinstance(entity_id, str)
    assert user_id == "user_123"
    assert entity_id == "entity_456"


def test_type_guards():
    """Test type guard functions"""
    # Valid UIDs
    assert is_valid_uid("user_123")
    assert is_valid_uid("task_abc123")

    # Invalid UIDs
    assert not is_valid_uid("invalid-uid")
    assert not is_valid_uid("123_user")
    assert not is_valid_uid("")

    # Valid percentages
    assert is_valid_percentage(0.0)
    assert is_valid_percentage(50.0)
    assert is_valid_percentage(100.0)

    # Invalid percentages
    assert not is_valid_percentage(-1)
    assert not is_valid_percentage(101)
    assert not is_valid_percentage("50")

    # Valid scores
    assert is_valid_score(0.0)
    assert is_valid_score(0.5)
    assert is_valid_score(1.0)

    # Invalid scores
    assert not is_valid_score(-0.1)
    assert not is_valid_score(1.1)
    assert not is_valid_score("0.5")


def test_type_converter():
    """Test type conversion helpers"""
    # Valid conversions
    entity_uid = TypeConverter.to_entity_uid("entity_123")
    assert entity_uid == "entity_123"

    user_uid = TypeConverter.to_user_uid("user_456")
    assert user_uid == "user_456"

    percentage = TypeConverter.to_percentage(75.0)
    assert percentage == 75.0

    score = TypeConverter.to_score(0.8)
    assert score == 0.8

    # Invalid conversions should raise
    with pytest.raises(ValueError):
        TypeConverter.to_entity_uid("invalid-format")

    with pytest.raises(ValueError):
        TypeConverter.to_user_uid("task_123")  # Wrong prefix

    with pytest.raises(ValueError):
        TypeConverter.to_percentage(150.0)  # Out of range

    with pytest.raises(ValueError):
        TypeConverter.to_score(1.5)  # Out of range


def test_unified_user_context():
    """Test the simplified user context"""
    context = UserContext(
        user_uid=UserUID("user_123"),
        username="testuser",
        email="test@example.com",
    )

    assert context.user_uid == "user_123"
    assert context.username == "testuser"
    assert context.email == "test@example.com"

    # Test that context has expected fields with defaults
    assert context.active_task_uids == []  # Default empty list
    assert context.context_version == "3.0"  # Version tracking
    assert context.cache_ttl_seconds == 300  # 5 minute TTL


def test_cached_property():
    """Test that cached_property decorator works correctly"""
    computation_count = 0

    class TestClass:
        @cached_property
        def expensive_value(self) -> int:
            nonlocal computation_count
            computation_count += 1
            return 42

    obj = TestClass()

    # First access should compute
    assert obj.expensive_value == 42
    assert computation_count == 1

    # Second access should use cache
    assert obj.expensive_value == 42
    assert computation_count == 1  # Still 1, not recomputed

    # Third access should still use cache
    assert obj.expensive_value == 42
    assert computation_count == 1  # Still 1


if __name__ == "__main__":
    # Run tests manually
    test_newtype_definitions()
    test_type_guards()
    test_type_converter()
    test_unified_user_context()
    test_cached_property()
    print("✅ All type system tests passed!")
