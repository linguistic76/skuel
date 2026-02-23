"""
Unit tests for VectorSearchConfig.

Tests configuration defaults and entity-specific thresholds.
"""

from core.config.unified_config import VectorSearchConfig


def test_vector_config_defaults():
    """Test default configuration values."""
    config = VectorSearchConfig()

    assert config.default_limit == 10
    assert config.default_min_score == 0.7
    assert config.batch_size == 25
    assert config.vector_weight == 0.5
    assert config.text_weight == 0.5
    assert config.rrf_k == 60


def test_entity_specific_thresholds():
    """Test entity-specific minimum scores."""
    config = VectorSearchConfig()

    # High precision entities (knowledge-focused)
    assert config.get_min_score_for_entity("Entity") == 0.75
    assert config.get_min_score_for_entity("entity") == 0.75  # Case insensitive
    assert config.get_min_score_for_entity("Lpstep") == 0.75

    # Medium precision entities
    assert config.get_min_score_for_entity("Goal") == 0.70
    assert config.get_min_score_for_entity("Habit") == 0.70

    # Lower precision entities (broader matching)
    assert config.get_min_score_for_entity("Task") == 0.65
    assert config.get_min_score_for_entity("Event") == 0.65


def test_unknown_entity_uses_default():
    """Test unknown entity types fall back to default threshold."""
    config = VectorSearchConfig()

    assert config.get_min_score_for_entity("UnknownType") == 0.7
    assert config.get_min_score_for_entity("unknown") == 0.7


def test_custom_config():
    """Test custom configuration values."""
    config = VectorSearchConfig(
        default_limit=20,
        default_min_score=0.8,
        ku_min_score=0.85,
        task_min_score=0.6,
    )

    assert config.default_limit == 20
    assert config.default_min_score == 0.8
    assert config.get_min_score_for_entity("Entity") == 0.85
    assert config.get_min_score_for_entity("Task") == 0.6


def test_hybrid_search_weights():
    """Test hybrid search weight configuration."""
    config = VectorSearchConfig()

    # Weights should sum to 1.0
    assert config.vector_weight + config.text_weight == 1.0

    # Custom weights
    config_custom = VectorSearchConfig(vector_weight=0.7, text_weight=0.3)
    assert config_custom.vector_weight == 0.7
    assert config_custom.text_weight == 0.3


def test_rrf_parameter():
    """Test RRF (Reciprocal Rank Fusion) parameter."""
    config = VectorSearchConfig()

    # Standard RRF k value is 60
    assert config.rrf_k == 60

    # Custom k value
    config_custom = VectorSearchConfig(rrf_k=100)
    assert config_custom.rrf_k == 100
