"""
Unit tests for VectorSearchConfig.

Tests configuration defaults and entity-specific thresholds.
"""

from core.config.unified_config import VectorSearchConfig
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.orchestrator.search_router import SearchRouter


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


def test_canonical_neo4j_labels_get_their_configured_threshold():
    """The labels the SearchRouter hybrid rung actually passes.

    It derives labels from `NeoLabel.from_entity_type(...).value` — "Ku",
    "PathStep", "LearningPath". These missed the mapping (which only knew the
    base "entity" label and the retired "lpstep" spelling), so curriculum
    vector search silently ran at the generic 0.70 instead of its calibrated
    0.75, admitting weaker candidates into the RRF merge (Codex, PR #1074).
    """
    config = VectorSearchConfig()

    assert config.get_min_score_for_entity("Ku") == 0.75
    assert config.get_min_score_for_entity("PathStep") == 0.75
    assert config.get_min_score_for_entity("LearningPath") == 0.75


def test_entity_type_spelling_resolves_too():
    """EntityType values are snake_case where NeoLabel is PascalCase, and
    callers arrive from both directions."""
    config = VectorSearchConfig()

    assert config.get_min_score_for_entity(EntityType.PATH_STEP) == 0.75
    assert config.get_min_score_for_entity(EntityType.LEARNING_PATH) == 0.75
    assert config.get_min_score_for_entity(EntityType.KU) == 0.75
    assert config.get_min_score_for_entity("path_step") == 0.75
    assert config.get_min_score_for_entity("learning_path") == 0.75


def test_every_hybrid_rung_label_is_configured():
    """A label the rung can pass must never fall through to the default.

    Keyed off the router's own allowlist so adding a domain there without a
    threshold fails here rather than silently searching at 0.70.
    """
    config = VectorSearchConfig()

    for domain_value in SearchRouter._HYBRID_TEXT_DOMAIN_VALUES:
        entity_type = EntityType(domain_value)
        label = NeoLabel.from_entity_type(entity_type).value
        assert config.get_min_score_for_entity(label) != config.default_min_score, (
            f"{label} has no configured threshold — it would search at the generic default"
        )


def test_retired_lpstep_spelling_is_gone():
    """`LpStep` became `PathStep`; the schema manager drops its indexes as stale."""
    config = VectorSearchConfig()

    assert config.get_min_score_for_entity("Lpstep") == config.default_min_score
    assert not hasattr(config, "lpstep_min_score")
