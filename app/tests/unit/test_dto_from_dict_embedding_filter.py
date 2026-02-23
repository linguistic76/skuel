"""
Test Infrastructure Field Filtering in DTOs (ADR-037)

Tests that dto_from_dict automatically filters out infrastructure fields
(embeddings, embedding metadata) that are stored in Neo4j but excluded
from DTOs.

Architectural Decision:
Embeddings are search infrastructure, not domain data. They are stored
in Neo4j for vector search but filtered out when converting to DTOs.
Application code doesn't need raw 1536-dimensional vectors.

See: /docs/decisions/ADR-037-embedding-infrastructure-separation.md
"""

from datetime import datetime

from core.models.enums import Domain, EntityStatus, Priority
from core.models.goal.goal_dto import GoalDTO
from core.models.task.task_dto import TaskDTO


def test_task_dto_from_dict_filters_embedding():
    """Test that TaskDTO.from_dict ignores 'embedding' field from Neo4j."""
    # Simulate data from Neo4j with embedding field
    neo4j_data = {
        "uid": "task_test_abc123",
        "user_uid": "user_test",
        "title": "Test Task",
        "description": "Test description",
        "status": "draft",  # Correct enum value
        "priority": "medium",
        "embedding": [0.1, 0.2, 0.3],  # This field should be filtered out
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    # Should not raise TypeError about unexpected 'embedding' argument
    task_dto = TaskDTO.from_dict(neo4j_data)

    # Verify core fields are correctly parsed
    assert task_dto.uid == "task_test_abc123"
    assert task_dto.title == "Test Task"
    assert task_dto.status == EntityStatus.DRAFT
    assert task_dto.priority == Priority.MEDIUM

    # Verify embedding field doesn't exist in DTO
    assert not hasattr(task_dto, "embedding")


def test_goal_dto_from_dict_filters_embedding():
    """Test that GoalDTO.from_dict ignores 'embedding' field from Neo4j."""
    # Simulate data from Neo4j with embedding field
    neo4j_data = {
        "uid": "goal_test_xyz789",
        "user_uid": "user_test",
        "title": "Test Goal",
        "description": "Test goal description",
        "goal_type": "outcome",
        "domain": "knowledge",
        "timeframe": "quarterly",
        "measurement_type": "percentage",
        "status": "active",  # Valid EntityStatus value
        "priority": "high",
        "embedding": [0.5, 0.6, 0.7],  # This field should be filtered out
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    # Should not raise TypeError about unexpected 'embedding' argument
    goal_dto = GoalDTO.from_dict(neo4j_data)

    # Verify core fields are correctly parsed
    assert goal_dto.uid == "goal_test_xyz789"
    assert goal_dto.title == "Test Goal"
    assert goal_dto.domain == Domain.KNOWLEDGE
    assert goal_dto.status == EntityStatus.ACTIVE
    assert goal_dto.priority == Priority.HIGH

    # Verify embedding field doesn't exist in DTO
    assert not hasattr(goal_dto, "embedding")


def test_dto_from_dict_preserves_all_valid_fields():
    """Test that filtering doesn't remove valid fields."""
    task_data = {
        "uid": "task_comprehensive_abc123",
        "user_uid": "user_test",
        "title": "Comprehensive Test",
        "description": "Full field test",
        "status": "active",  # Correct EntityStatus enum value
        "priority": "high",
        "project": "test-project",
        "assignee": "test-assignee",
        "tags": ["tag1", "tag2"],
        "duration_minutes": 60,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "embedding": [1.0, 2.0, 3.0],  # Should be filtered
        "some_random_field": "should also be filtered",
    }

    task_dto = TaskDTO.from_dict(task_data)

    # All valid fields should be preserved
    assert task_dto.uid == "task_comprehensive_abc123"
    assert task_dto.title == "Comprehensive Test"
    assert task_dto.project == "test-project"
    assert task_dto.assignee == "test-assignee"
    assert task_dto.tags == ["tag1", "tag2"]
    assert task_dto.duration_minutes == 60
    assert task_dto.status == EntityStatus.ACTIVE
    assert task_dto.priority == Priority.HIGH

    # Invalid fields should not exist
    assert not hasattr(task_dto, "embedding")
    assert not hasattr(task_dto, "some_random_field")
