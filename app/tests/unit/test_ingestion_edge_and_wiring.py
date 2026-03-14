"""
Tests for ingestion evolution: edge ingestion + relationship field wiring.

Covers:
- Edge detection (is_edge_type)
- Edge validation (validate_edge_data)
- Edge preparation (prepare_edge_data)
- Lesson USES_KU wiring via registry
- LS relationship field wiring (all 10+ fields)
- LS preparer normalization (single→list, UID normalization)
- Evidence relationship types on RelationshipName
"""

from pathlib import Path

from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.services.ingestion.config import generate_ingestion_relationship_config
from core.services.ingestion.detector import is_edge_type
from core.services.ingestion.preparer import prepare_edge_data, prepare_entity_data
from core.services.ingestion.validator import validate_edge_data

# ============================================================================
# EDGE DETECTION
# ============================================================================


class TestEdgeDetection:
    """Tests for is_edge_type() function."""

    def test_edge_type_detected(self):
        assert is_edge_type({"type": "Edge"}) is True

    def test_edge_type_case_insensitive(self):
        assert is_edge_type({"type": "edge"}) is True
        assert is_edge_type({"type": "EDGE"}) is True
        assert is_edge_type({"type": " Edge "}) is True

    def test_lesson_not_edge(self):
        assert is_edge_type({"type": "Lesson"}) is False

    def test_ku_not_edge(self):
        assert is_edge_type({"type": "ku"}) is False

    def test_missing_type_not_edge(self):
        assert is_edge_type({}) is False

    def test_empty_type_not_edge(self):
        assert is_edge_type({"type": ""}) is False


# ============================================================================
# EDGE VALIDATION
# ============================================================================


class TestEdgeValidation:
    """Tests for validate_edge_data() function."""

    def test_valid_edge(self):
        data = {
            "type": "edge",
            "from": "ku:caffeine",
            "to": "ku:tinnitus-buzzing",
            "relationship": "EXACERBATED_BY",
            "confidence": 0.8,
            "polarity": -1,
        }
        result = validate_edge_data(data)
        assert result.is_ok

    def test_missing_from(self):
        data = {"to": "ku:b", "relationship": "CAUSES"}
        result = validate_edge_data(data)
        assert result.is_error

    def test_missing_to(self):
        data = {"from": "ku:a", "relationship": "CAUSES"}
        result = validate_edge_data(data)
        assert result.is_error

    def test_missing_relationship(self):
        data = {"from": "ku:a", "to": "ku:b"}
        result = validate_edge_data(data)
        assert result.is_error

    def test_unknown_relationship(self):
        data = {"from": "ku:a", "to": "ku:b", "relationship": "TOTALLY_FAKE"}
        result = validate_edge_data(data)
        assert result.is_error
        assert "Unknown relationship" in str(result.expect_error())

    def test_confidence_out_of_range(self):
        data = {"from": "ku:a", "to": "ku:b", "relationship": "CAUSES", "confidence": 1.5}
        result = validate_edge_data(data)
        assert result.is_error
        assert "confidence" in str(result.expect_error())

    def test_confidence_negative(self):
        data = {"from": "ku:a", "to": "ku:b", "relationship": "CAUSES", "confidence": -0.1}
        result = validate_edge_data(data)
        assert result.is_error

    def test_invalid_polarity(self):
        data = {"from": "ku:a", "to": "ku:b", "relationship": "CAUSES", "polarity": 2}
        result = validate_edge_data(data)
        assert result.is_error
        assert "polarity" in str(result.expect_error())

    def test_invalid_temporality(self):
        data = {"from": "ku:a", "to": "ku:b", "relationship": "CAUSES", "temporality": "forever"}
        result = validate_edge_data(data)
        assert result.is_error
        assert "temporality" in str(result.expect_error())

    def test_valid_temporalities(self):
        for temp in ("minutes", "hours", "days", "chronic"):
            data = {"from": "ku:a", "to": "ku:b", "relationship": "CAUSES", "temporality": temp}
            assert validate_edge_data(data).is_ok

    def test_invalid_source(self):
        data = {"from": "ku:a", "to": "ku:b", "relationship": "CAUSES", "source": "gossip"}
        result = validate_edge_data(data)
        assert result.is_error
        assert "source" in str(result.expect_error())

    def test_valid_sources(self):
        for src in ("self_observation", "research", "teacher", "clinical"):
            data = {"from": "ku:a", "to": "ku:b", "relationship": "CAUSES", "source": src}
            assert validate_edge_data(data).is_ok


# ============================================================================
# EDGE PREPARATION
# ============================================================================


class TestEdgePreparer:
    """Tests for prepare_edge_data() function."""

    def test_basic_preparation(self):
        data = {
            "from": "ku:caffeine",
            "to": "ku:buzzing",
            "relationship": "EXACERBATED_BY",
        }
        result = prepare_edge_data(data)
        assert result["from_uid"] == "ku.caffeine"
        assert result["to_uid"] == "ku.buzzing"
        assert result["relationship"] == "EXACERBATED_BY"
        assert "created_at" in result["properties"]
        assert "updated_at" in result["properties"]

    def test_uid_normalization(self):
        data = {
            "from": "ku:deep-breathing",
            "to": "ku:anxiety-response",
            "relationship": "REDUCED_BY",
        }
        result = prepare_edge_data(data)
        assert result["from_uid"] == "ku.deep-breathing"
        assert result["to_uid"] == "ku.anxiety-response"

    def test_evidence_properties_extracted(self):
        data = {
            "from": "ku:a",
            "to": "ku:b",
            "relationship": "CAUSES",
            "evidence": "Observed repeatedly",
            "confidence": 0.9,
            "polarity": -1,
            "temporality": "hours",
            "source": "self_observation",
            "observed_at": "2026-03-01",
        }
        result = prepare_edge_data(data)
        props = result["properties"]
        assert props["evidence"] == "Observed repeatedly"
        assert props["confidence"] == 0.9
        assert props["polarity"] == -1
        assert props["temporality"] == "hours"
        assert props["source"] == "self_observation"
        assert props["observed_at"] == "2026-03-01"

    def test_tags_extracted(self):
        data = {
            "from": "ku:a",
            "to": "ku:b",
            "relationship": "CAUSES",
            "tags": ["health", "nervous-system"],
        }
        result = prepare_edge_data(data)
        assert result["properties"]["tags"] == ["health", "nervous-system"]

    def test_source_file_recorded(self):
        data = {"from": "ku:a", "to": "ku:b", "relationship": "CAUSES"}
        result = prepare_edge_data(data, file_path=Path("/vault/edges/test.yaml"))
        assert result["properties"]["source_file"] == "/vault/edges/test.yaml"


# ============================================================================
# LESSON USES_KU WIRING
# ============================================================================


class TestLessonUsesKuWiring:
    """Tests for Lesson USES_KU ingestion wiring."""

    def test_registry_includes_uses_kus(self):
        config = generate_ingestion_relationship_config(EntityType.LESSON)
        assert config is not None
        assert "uses_kus" in config
        assert config["uses_kus"]["rel_type"] == "USES_KU"
        assert config["uses_kus"]["target_label"] == "Ku"
        assert config["uses_kus"]["direction"] == "outgoing"

    def test_preparer_normalizes_uses_kus(self):
        data = {
            "type": "lesson",
            "title": "Test Lesson",
            "uses_kus": ["ku:meditation-basics", "ku:breathwork"],
        }
        result = prepare_entity_data(EntityType.LESSON, data, "body content", Path("test.md"))
        assert result["uses_kus"] == ["ku.meditation-basics", "ku.breathwork"]

    def test_preparer_skips_non_list_uses_kus(self):
        data = {
            "type": "lesson",
            "title": "Test Lesson",
            "uses_kus": "not-a-list",
        }
        result = prepare_entity_data(EntityType.LESSON, data, "body content", Path("test.md"))
        # Non-list value left unchanged
        assert result["uses_kus"] == "not-a-list"


# ============================================================================
# LS RELATIONSHIP FIELD WIRING
# ============================================================================


class TestLsFieldWiring:
    """Tests for Learning Step relationship field wiring in the registry."""

    def test_primary_knowledge_uids(self):
        config = generate_ingestion_relationship_config(EntityType.LEARNING_STEP)
        assert config is not None
        assert "primary_knowledge_uids" in config
        assert config["primary_knowledge_uids"]["rel_type"] == "CONTAINS_KNOWLEDGE"

    def test_trains_ku_uids(self):
        config = generate_ingestion_relationship_config(EntityType.LEARNING_STEP)
        assert config is not None
        assert "trains_ku_uids" in config
        assert config["trains_ku_uids"]["rel_type"] == "TRAINS_KU"
        assert config["trains_ku_uids"]["target_label"] == "Ku"

    def test_prerequisite_step_uids(self):
        config = generate_ingestion_relationship_config(EntityType.LEARNING_STEP)
        assert config is not None
        assert "prerequisite_step_uids" in config
        assert config["prerequisite_step_uids"]["rel_type"] == "REQUIRES_STEP"

    def test_prerequisite_knowledge_uids(self):
        config = generate_ingestion_relationship_config(EntityType.LEARNING_STEP)
        assert config is not None
        assert "prerequisite_knowledge_uids" in config
        assert config["prerequisite_knowledge_uids"]["rel_type"] == "REQUIRES_KNOWLEDGE"

    def test_supporting_knowledge_uids(self):
        config = generate_ingestion_relationship_config(EntityType.LEARNING_STEP)
        assert config is not None
        assert "supporting_knowledge_uids" in config
        assert config["supporting_knowledge_uids"]["rel_type"] == "REQUIRES_KNOWLEDGE"

    def test_principle_uids(self):
        config = generate_ingestion_relationship_config(EntityType.LEARNING_STEP)
        assert config is not None
        assert "principle_uids" in config
        assert config["principle_uids"]["rel_type"] == "GUIDED_BY_PRINCIPLE"

    def test_choice_uids(self):
        config = generate_ingestion_relationship_config(EntityType.LEARNING_STEP)
        assert config is not None
        assert "choice_uids" in config
        assert config["choice_uids"]["rel_type"] == "INFORMS_CHOICE"

    def test_habit_uids(self):
        config = generate_ingestion_relationship_config(EntityType.LEARNING_STEP)
        assert config is not None
        assert "habit_uids" in config
        assert config["habit_uids"]["rel_type"] == "BUILDS_HABIT"

    def test_task_uids(self):
        config = generate_ingestion_relationship_config(EntityType.LEARNING_STEP)
        assert config is not None
        assert "task_uids" in config
        assert config["task_uids"]["rel_type"] == "ASSIGNS_TASK"

    def test_event_template_uids(self):
        config = generate_ingestion_relationship_config(EntityType.LEARNING_STEP)
        assert config is not None
        assert "event_template_uids" in config
        assert config["event_template_uids"]["rel_type"] == "SCHEDULES_EVENT"

    def test_learning_path_uids(self):
        config = generate_ingestion_relationship_config(EntityType.LEARNING_STEP)
        assert config is not None
        assert "learning_path_uids" in config
        assert config["learning_path_uids"]["rel_type"] == "HAS_STEP"
        assert config["learning_path_uids"]["direction"] == "incoming"

    def test_total_field_count(self):
        """LS should have at least 11 relationship fields wired."""
        config = generate_ingestion_relationship_config(EntityType.LEARNING_STEP)
        assert config is not None
        assert len(config) >= 11


# ============================================================================
# LS PREPARER NORMALIZATION
# ============================================================================


class TestLsPreparerNormalization:
    """Tests for LS-specific field normalization in the preparer."""

    def test_learning_path_uid_to_list(self):
        """Single learning_path_uid should be converted to learning_path_uids list."""
        data = {
            "type": "ls",
            "title": "Step 1",
            "learning_path_uid": "lp:mindfulness-101",
        }
        result = prepare_entity_data(EntityType.LEARNING_STEP, data, None, Path("step1.yaml"))
        assert "learning_path_uid" not in result
        assert result["learning_path_uids"] == ["lp.mindfulness-101"]

    def test_knowledge_uid_merged(self):
        """Single knowledge_uid should merge into primary_knowledge_uids."""
        data = {
            "type": "ls",
            "title": "Step 1",
            "knowledge_uid": "ku:breathing",
        }
        result = prepare_entity_data(EntityType.LEARNING_STEP, data, None, Path("step1.yaml"))
        assert "knowledge_uid" not in result
        assert "ku.breathing" in result["primary_knowledge_uids"]

    def test_knowledge_uid_no_duplicate(self):
        """knowledge_uid should not duplicate existing primary_knowledge_uids entry."""
        data = {
            "type": "ls",
            "title": "Step 1",
            "knowledge_uid": "ku:breathing",
            "primary_knowledge_uids": ["ku:breathing"],
        }
        result = prepare_entity_data(EntityType.LEARNING_STEP, data, None, Path("step1.yaml"))
        assert result["primary_knowledge_uids"].count("ku.breathing") == 1

    def test_uid_normalization_in_list_fields(self):
        """All UID list fields should have colon→dot normalization."""
        data = {
            "type": "ls",
            "title": "Step 1",
            "trains_ku_uids": ["ku:concept-a", "ku:concept-b"],
            "principle_uids": ["principle:honesty"],
            "task_uids": ["task:practice-1"],
        }
        result = prepare_entity_data(EntityType.LEARNING_STEP, data, None, Path("step1.yaml"))
        assert result["trains_ku_uids"] == ["ku.concept-a", "ku.concept-b"]
        assert result["principle_uids"] == ["principle.honesty"]
        assert result["task_uids"] == ["task.practice-1"]


# ============================================================================
# EVIDENCE RELATIONSHIP TYPES
# ============================================================================


class TestEvidenceRelationshipTypes:
    """Tests for evidence relationship types on RelationshipName."""

    def test_evidence_types_exist(self):
        assert RelationshipName.EXACERBATED_BY.value == "EXACERBATED_BY"
        assert RelationshipName.REDUCED_BY.value == "REDUCED_BY"
        assert RelationshipName.CORRELATED_WITH.value == "CORRELATED_WITH"
        assert RelationshipName.CAUSES.value == "CAUSES"
        assert RelationshipName.PRECEDES.value == "PRECEDES"

    def test_is_evidence_relationship(self):
        assert RelationshipName.EXACERBATED_BY.is_evidence_relationship()
        assert RelationshipName.REDUCED_BY.is_evidence_relationship()
        assert RelationshipName.CORRELATED_WITH.is_evidence_relationship()
        assert RelationshipName.CAUSES.is_evidence_relationship()
        assert RelationshipName.PRECEDES.is_evidence_relationship()

    def test_non_evidence_not_evidence(self):
        assert not RelationshipName.REQUIRES_KNOWLEDGE.is_evidence_relationship()
        assert not RelationshipName.OWNS.is_evidence_relationship()

    def test_is_valid_for_edge_validation(self):
        assert RelationshipName.is_valid("EXACERBATED_BY")
        assert RelationshipName.is_valid("REDUCED_BY")
        assert RelationshipName.is_valid("CORRELATED_WITH")
        assert RelationshipName.is_valid("CAUSES")
        assert RelationshipName.is_valid("PRECEDES")
