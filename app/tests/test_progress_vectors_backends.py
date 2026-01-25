"""
Tests for Progress and Vector Backends
=======================================

Integration tests to verify UniversalNeo4jBackend works with:
- UserProgress model (progress tracking)
- EmbeddingVector model (semantic search)
"""

from datetime import date, datetime, timedelta

import pytest

from core.models.progress import UserProgress, generate_progress_uid
from core.models.shared_enums import Domain
from core.models.vectors import EmbeddingVector, generate_embedding_uid, hash_source_text

# ============================================================================
# PROGRESS MODEL TESTS
# ============================================================================


def test_user_progress_creation():
    """Test creating a valid UserProgress instance."""
    uid = generate_progress_uid("user_123", "task_456")

    progress = UserProgress(
        uid=uid,
        user_uid="user_123",
        entity_uid="task_456",
        entity_type="task",
        progress_value=0.5,
        status="in_progress",
        tracked_at=datetime.now(),
        started_at=datetime.now(),
        time_invested_minutes=30,
        domain=Domain.TECH,
    )

    assert progress.uid == uid
    assert progress.user_uid == "user_123"
    assert progress.entity_uid == "task_456"
    assert progress.progress_value == 0.5
    assert not progress.is_completed
    assert not progress.is_mastered
    assert progress.completion_percentage == 50.0


def test_user_progress_completion():
    """Test marking progress as completed."""
    uid = generate_progress_uid("user_123", "task_456")

    progress = UserProgress(
        uid=uid,
        user_uid="user_123",
        entity_uid="task_456",
        entity_type="task",
        progress_value=0.5,
        status="in_progress",
        tracked_at=datetime.now(),
        started_at=datetime.now(),
    )

    # Update progress to completion
    completed = progress.with_updated_progress(1.0, time_invested=15)

    assert completed.progress_value == 1.0
    assert completed.status == "completed"
    assert completed.is_completed
    assert completed.time_invested_minutes == 15
    assert completed.completed_at is not None


def test_user_progress_mastery():
    """Test marking progress as mastered (learning)."""
    uid = generate_progress_uid("user_123", "ku_python_basics")

    progress = UserProgress(
        uid=uid,
        user_uid="user_123",
        entity_uid="ku_python_basics",
        entity_type="knowledge",
        progress_value=0.9,
        status="in_progress",
        tracked_at=datetime.now(),
        started_at=datetime.now(),
    )

    # Mark as mastered
    mastered = progress.with_mastery(mastery_score=0.95, confidence=0.9)

    assert mastered.mastery_score == 0.95
    assert mastered.confidence_level == 0.9
    assert mastered.status == "mastered"
    assert mastered.is_mastered
    assert mastered.progress_value == 1.0


def test_user_progress_validation():
    """Test progress value validation."""
    uid = generate_progress_uid("user_123", "task_456")

    # Invalid progress value
    with pytest.raises(ValueError, match="progress_value must be 0.0-1.0"):
        UserProgress(
            uid=uid,
            user_uid="user_123",
            entity_uid="task_456",
            entity_type="task",
            progress_value=1.5,  # Invalid
            status="in_progress",
            tracked_at=datetime.now(),
        )


def test_user_progress_review_scheduling():
    """Test review scheduling for spaced repetition."""
    uid = generate_progress_uid("user_123", "ku_algorithms")

    progress = UserProgress(
        uid=uid,
        user_uid="user_123",
        entity_uid="ku_algorithms",
        entity_type="knowledge",
        progress_value=1.0,
        status="mastered",
        tracked_at=datetime.now(),
        mastery_score=0.9,
        last_reviewed=datetime.now(),
        next_review_due=date.today(),  # Due today
        review_interval_days=7,
    )

    assert progress.needs_review

    # Future review - use dynamic future date to avoid test rot
    future_date = date.today() + timedelta(days=30)
    future_progress = UserProgress(
        uid=generate_progress_uid("user_123", "ku_data_structures"),
        user_uid="user_123",
        entity_uid="ku_data_structures",
        entity_type="knowledge",
        progress_value=1.0,
        status="mastered",
        tracked_at=datetime.now(),
        mastery_score=0.9,
        next_review_due=future_date,  # Dynamic future date
    )

    assert not future_progress.needs_review


# ============================================================================
# EMBEDDING VECTOR TESTS
# ============================================================================


def test_embedding_vector_creation():
    """Test creating a valid EmbeddingVector instance."""
    source_text = "Python is a high-level programming language"
    embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

    uid = generate_embedding_uid("ku_python_basics", "ada002")
    source_hash = hash_source_text(source_text)

    vector = EmbeddingVector(
        uid=uid,
        entity_uid="ku_python_basics",
        entity_type="knowledge",
        embedding=embedding,
        embedding_model="text-embedding-ada-002",
        embedding_dimension=5,
        source_text=source_text,
        source_hash=source_hash,
        created_at=datetime.now(),
        domain=Domain.TECH,
    )

    assert vector.uid == uid
    assert vector.entity_uid == "ku_python_basics"
    assert len(vector.embedding) == 5
    assert vector.embedding_dimension == 5
    assert vector.is_valid  # Non-zero embedding


def test_embedding_vector_validation():
    """Test embedding dimension validation."""
    source_text = "Test text"
    source_hash = hash_source_text(source_text)

    # Dimension mismatch
    with pytest.raises(ValueError, match="does not match declared dimension"):
        EmbeddingVector(
            uid=generate_embedding_uid("test", "ada002"),
            entity_uid="test",
            entity_type="knowledge",
            embedding=[0.1, 0.2, 0.3],  # 3 dimensions
            embedding_model="ada-002",
            embedding_dimension=5,  # Claims 5 dimensions
            source_text=source_text,
            source_hash=source_hash,
            created_at=datetime.now(),
        )


def test_embedding_vector_normalization():
    """Test L2 normalization of embedding vector."""
    source_text = "Test"
    source_hash = hash_source_text(source_text)

    vector = EmbeddingVector(
        uid=generate_embedding_uid("test", "ada002"),
        entity_uid="test",
        entity_type="knowledge",
        embedding=[3.0, 4.0],  # Magnitude = 5.0
        embedding_model="ada-002",
        embedding_dimension=2,
        source_text=source_text,
        source_hash=source_hash,
        created_at=datetime.now(),
    )

    normalized = vector.normalized()

    # Normalized vector should have magnitude = 1.0
    magnitude = sum(v * v for v in normalized) ** 0.5
    assert abs(magnitude - 1.0) < 0.0001  # Approximately 1.0

    # Values should be [0.6, 0.8] (3/5, 4/5)
    assert abs(normalized[0] - 0.6) < 0.0001
    assert abs(normalized[1] - 0.8) < 0.0001


def test_cosine_similarity():
    """Test cosine similarity calculation between vectors."""
    source_hash = hash_source_text("test")

    # Create two similar vectors
    vector1 = EmbeddingVector(
        uid=generate_embedding_uid("test1", "ada002"),
        entity_uid="test1",
        entity_type="knowledge",
        embedding=[1.0, 0.0, 0.0],
        embedding_model="ada-002",
        embedding_dimension=3,
        source_text="test",
        source_hash=source_hash,
        created_at=datetime.now(),
    )

    vector2 = EmbeddingVector(
        uid=generate_embedding_uid("test2", "ada002"),
        entity_uid="test2",
        entity_type="knowledge",
        embedding=[1.0, 0.0, 0.0],  # Identical direction
        embedding_model="ada-002",
        embedding_dimension=3,
        source_text="test",
        source_hash=source_hash,
        created_at=datetime.now(),
    )

    similarity = vector1.cosine_similarity(vector2)
    assert abs(similarity - 1.0) < 0.0001  # Should be 1.0 (identical)

    # Orthogonal vectors
    vector3 = EmbeddingVector(
        uid=generate_embedding_uid("test3", "ada002"),
        entity_uid="test3",
        entity_type="knowledge",
        embedding=[0.0, 1.0, 0.0],  # Perpendicular
        embedding_model="ada-002",
        embedding_dimension=3,
        source_text="test",
        source_hash=source_hash,
        created_at=datetime.now(),
    )

    similarity_orthogonal = vector1.cosine_similarity(vector3)
    assert abs(similarity_orthogonal - 0.0) < 0.0001  # Should be 0.0 (orthogonal)


def test_euclidean_distance():
    """Test Euclidean distance calculation between vectors."""
    source_hash = hash_source_text("test")

    vector1 = EmbeddingVector(
        uid=generate_embedding_uid("test1", "ada002"),
        entity_uid="test1",
        entity_type="knowledge",
        embedding=[0.0, 0.0],
        embedding_model="ada-002",
        embedding_dimension=2,
        source_text="test",
        source_hash=source_hash,
        created_at=datetime.now(),
    )

    vector2 = EmbeddingVector(
        uid=generate_embedding_uid("test2", "ada002"),
        entity_uid="test2",
        entity_type="knowledge",
        embedding=[3.0, 4.0],  # Distance = 5.0 from origin
        embedding_model="ada-002",
        embedding_dimension=2,
        source_text="test",
        source_hash=source_hash,
        created_at=datetime.now(),
    )

    distance = vector1.euclidean_distance(vector2)
    assert abs(distance - 5.0) < 0.0001  # Should be 5.0


def test_source_hash_consistency():
    """Test that source text hashing is consistent."""
    text = "This is a test"

    hash1 = hash_source_text(text)
    hash2 = hash_source_text(text)

    assert hash1 == hash2  # Same text → same hash

    # Different text → different hash
    hash3 = hash_source_text("Different text")
    assert hash1 != hash3


# ============================================================================
# UID GENERATION TESTS
# ============================================================================


def test_progress_uid_generation():
    """Test progress UID generation format."""
    uid = generate_progress_uid("user_123", "task_456", timestamp=datetime(2025, 10, 14, 12, 0, 0))

    assert uid.startswith("progress.user_123.task_456.")
    assert len(uid.split(".")) == 4  # Four parts: progress, user, entity, timestamp


def test_embedding_uid_generation():
    """Test embedding UID generation format."""
    uid = generate_embedding_uid(
        "ku_python", "text-embedding-ada-002", timestamp=datetime(2025, 10, 14, 12, 0, 0)
    )

    assert uid.startswith("embedding.ku_python.ada002.")
    assert "text-embedding-" not in uid  # Model name normalized
    assert len(uid.split(".")) == 4  # Four parts: embedding, entity, model, timestamp
