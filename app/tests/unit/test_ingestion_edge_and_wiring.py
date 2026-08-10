"""
Tests for ingestion evolution: edge ingestion + relationship field wiring.

Covers:
- Edge detection (is_edge_type)
- Edge validation (validate_edge_data)
- Edge preparation (prepare_edge_data)
- PathStep USES_KU wiring via registry
- PS relationship field wiring (all 10+ fields)
- PS preparer normalization (single→list, UID normalization)
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

    def test_locator_property_extracted(self):
        data = {
            "from": "ku:values:tao-te-ching-v1",
            "to": "resource:tao-of-pooh",
            "relationship": "CITES_RESOURCE",
            "locator": "ch. 4",
        }
        result = prepare_edge_data(data)
        assert result["properties"]["locator"] == "ch. 4"

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
# PATHSTEP USES_KU WIRING
# ============================================================================


class TestPathStepUsesKuWiring:
    """Tests for PathStep USES_KU ingestion wiring."""

    def test_registry_includes_uses_kus(self):
        config = generate_ingestion_relationship_config(EntityType.PATH_STEP)
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
        result = prepare_entity_data(EntityType.PATH_STEP, data, "body content", Path("test.md"))
        assert result["uses_kus"] == ["ku.meditation-basics", "ku.breathwork"]

    def test_preparer_skips_non_list_uses_kus(self):
        data = {
            "type": "lesson",
            "title": "Test Lesson",
            "uses_kus": "not-a-list",
        }
        result = prepare_entity_data(EntityType.PATH_STEP, data, "body content", Path("test.md"))
        # Non-list value left unchanged
        assert result["uses_kus"] == "not-a-list"

    def test_preparer_never_stamps_created_at(self):
        """``created_at`` must NOT ride in the props dict.

        The bulk upsert stamps it in ``ON CREATE`` and merges props in
        ``ON MATCH`` — a "now" stamp here lands inside props and so overwrote
        the real creation date on every re-sync (one ``--force`` run reset the
        whole content corpus). ``updated_at`` IS stamped: it means "this sync".
        """
        data = {"type": "lesson", "title": "Test Lesson"}
        result = prepare_entity_data(EntityType.PATH_STEP, data, "body", Path("test.md"))
        assert "created_at" not in result
        assert "updated_at" in result

    def test_validator_rejects_unparseable_created_at(self):
        """Codex #1005: un-stripping ``created_at`` opened a path for garbage.

        The read boundary parses it with ``datetime.fromisoformat`` and RAISES,
        so an unparseable value makes the ENTITY unloadable — not merely
        `datetime(n.created_at)` in analytics. Reject at the write door.
        """
        from core.services.ingestion.validator import validate_entity_data

        for bad in ("unknown", "2026-13-45", ["a", "b"], 12345):
            data = prepare_entity_data(
                EntityType.PATH_STEP,
                {"type": "lesson", "title": "T", "uid": "ps:x:y", "created_at": bad},
                "body",
                Path("t.md"),
            )
            result = validate_entity_data(EntityType.PATH_STEP, data, Path("t.md"))
            assert result.is_error, f"{bad!r} should be rejected"
            assert "created_at" in str(result.expect_error().display_message).lower()

    def test_validator_accepts_the_shapes_the_reader_accepts(self):
        """Mirror the read boundary's tolerance exactly — no wider, no narrower."""
        from datetime import date as _date
        from datetime import datetime as _datetime

        from core.services.ingestion.validator import validate_entity_data

        for good in (
            "2026-03-29T00:00:00Z",  # quoted ISO string
            "2026-03-29T00:00:00+00:00",
            "2026-03-29",
            _datetime(2026, 3, 29),  # PyYAML parses bare ISO into these
            _date(2026, 3, 29),
        ):
            data = prepare_entity_data(
                EntityType.PATH_STEP,
                {"type": "lesson", "title": "T", "uid": "ps:x:y", "created_at": good},
                "body",
                Path("t.md"),
            )
            result = validate_entity_data(EntityType.PATH_STEP, data, Path("t.md"))
            assert not result.is_error, f"{good!r} should be accepted"

    def test_preparer_preserves_authored_created_at(self):
        """An authored creation date is content — it survives into props and wins."""
        data = {
            "type": "lesson",
            "title": "Test Lesson",
            "created_at": "2026-03-29T00:00:00Z",
        }
        result = prepare_entity_data(EntityType.PATH_STEP, data, "body", Path("test.md"))
        assert result["created_at"] == "2026-03-29T00:00:00Z"


# ============================================================================
# PS RELATIONSHIP FIELD WIRING
# ============================================================================


class TestLsFieldWiring:
    """Tests for PathStep relationship field wiring in the registry."""

    def test_knowledge_uids(self):
        config = generate_ingestion_relationship_config(EntityType.PATH_STEP)
        assert config is not None
        assert "knowledge_uids" in config
        assert config["knowledge_uids"]["rel_type"] == "CONTAINS_KNOWLEDGE"

    def test_trains_ku_uids(self):
        config = generate_ingestion_relationship_config(EntityType.PATH_STEP)
        assert config is not None
        assert "trains_ku_uids" in config
        assert config["trains_ku_uids"]["rel_type"] == "TRAINS_KU"
        assert config["trains_ku_uids"]["target_label"] == "Ku"

    def test_prerequisite_step_uids(self):
        config = generate_ingestion_relationship_config(EntityType.PATH_STEP)
        assert config is not None
        assert "prerequisite_step_uids" in config
        assert config["prerequisite_step_uids"]["rel_type"] == "REQUIRES_STEP"

    def test_prerequisite_knowledge_uids(self):
        config = generate_ingestion_relationship_config(EntityType.PATH_STEP)
        assert config is not None
        assert "prerequisite_knowledge_uids" in config
        assert config["prerequisite_knowledge_uids"]["rel_type"] == "REQUIRES_KNOWLEDGE"

    def test_learning_path_uids(self):
        config = generate_ingestion_relationship_config(EntityType.PATH_STEP)
        assert config is not None
        assert "learning_path_uids" in config
        assert config["learning_path_uids"]["rel_type"] == "HAS_STEP"
        assert config["learning_path_uids"]["direction"] == "incoming"

    def test_activity_wiring_present(self):
        """Activity domain wiring on PathStep."""
        config = generate_ingestion_relationship_config(EntityType.PATH_STEP)
        assert config is not None
        for field in (
            "principle_uids",
            "choice_uids",
            "habit_uids",
            "task_uids",
            "event_template_uids",
        ):
            assert field in config

    def test_total_field_count(self):
        """PS should have 17 relationship fields wired (knowledge + steps + paths + activity wiring + connections + exercises + resources)."""
        config = generate_ingestion_relationship_config(EntityType.PATH_STEP)
        assert config is not None
        assert len(config) == 17


# ============================================================================
# PS PREPARER NORMALIZATION
# ============================================================================


class TestLsPreparerNormalization:
    """Tests for PS-specific field normalization in the preparer."""

    def test_learning_path_uid_to_list(self):
        """Single learning_path_uid should be converted to learning_path_uids list."""
        data = {
            "type": "ps",
            "title": "Step 1",
            "learning_path_uid": "lp:mindfulness-101",
        }
        result = prepare_entity_data(EntityType.PATH_STEP, data, None, Path("step1.yaml"))
        assert "learning_path_uid" not in result
        assert result["learning_path_uids"] == ["lp.mindfulness-101"]

    def test_knowledge_uid_merged(self):
        """Single knowledge_uid should merge into knowledge_uids."""
        data = {
            "type": "ps",
            "title": "Step 1",
            "knowledge_uid": "ku:breathing",
        }
        result = prepare_entity_data(EntityType.PATH_STEP, data, None, Path("step1.yaml"))
        assert "knowledge_uid" not in result
        assert "ku.breathing" in result["knowledge_uids"]

    def test_knowledge_uid_no_duplicate(self):
        """knowledge_uid should not duplicate existing knowledge_uids entry."""
        data = {
            "type": "ps",
            "title": "Step 1",
            "knowledge_uid": "ku:breathing",
            "knowledge_uids": ["ku:breathing"],
        }
        result = prepare_entity_data(EntityType.PATH_STEP, data, None, Path("step1.yaml"))
        assert result["knowledge_uids"].count("ku.breathing") == 1

    def test_uid_normalization_in_list_fields(self):
        """All UID list fields should have colon→dot normalization."""
        data = {
            "type": "ps",
            "title": "Step 1",
            "trains_ku_uids": ["ku:concept-a", "ku:concept-b"],
            "knowledge_uids": ["ku:concept-c"],
        }
        result = prepare_entity_data(EntityType.PATH_STEP, data, None, Path("step1.yaml"))
        assert result["trains_ku_uids"] == ["ku.concept-a", "ku.concept-b"]
        assert result["knowledge_uids"] == ["ku.concept-c"]


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
