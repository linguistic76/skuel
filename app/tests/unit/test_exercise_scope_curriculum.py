"""
Unit Tests for ExerciseScope.CURRICULUM — the one exercise scope
=================================================================

An exercise is authored only in the content vault, owned by no user (ADR-091 S2,
S4): CURRICULUM is the one scope, the model's default, and the only value the
ingestion boundary admits.

Test Categories:
1. Enum + model (the one scope, the default, is_valid)
2. Ingestion boundary (validate_entity_data guard + config scope default)
3. Batch item preparation (edge-source survival)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.enums.user_entry_enums import ExerciseScope
from core.models.exercises.exercise import Exercise
from core.services.ingestion.preparer import prepare_entity_data
from core.services.ingestion.validator import validate_entity_data
from tests.helpers.ingestion_owner import INGESTION_TEST_OWNER

# ============================================================================
# 1. ENUM + MODEL
# ============================================================================


def _exercise(**overrides: object) -> Exercise:
    defaults: dict[str, object] = {
        "uid": "ex.test.sample",
        "entity_type": EntityType.EXERCISE,
        "title": "Sample",
        "instructions": "Do the thing.",
    }
    defaults.update(overrides)
    return Exercise(**defaults)  # type: ignore[arg-type]


def test_curriculum_is_the_one_scope() -> None:
    assert [member.value for member in ExerciseScope] == ["curriculum"]


def test_an_exercise_is_curriculum_by_default_and_valid() -> None:
    exercise = _exercise()
    assert exercise.scope is ExerciseScope.CURRICULUM
    assert exercise.is_valid()


def test_an_exercise_without_instructions_is_not_valid() -> None:
    assert not _exercise(instructions=None).is_valid()


# ============================================================================
# 2. INGESTION BOUNDARY
# ============================================================================

_FILE = Path("exercise-sample.md")
_TEACHER = "user_teacher"


def _prepared(data: dict[str, object]) -> dict[str, object]:
    return prepare_entity_data(EntityType.EXERCISE, dict(data), None, _FILE, INGESTION_TEST_OWNER)


def test_ingestion_defaults_absent_scope_to_curriculum() -> None:
    prepared = _prepared({"title": "Sample", "instructions": "Do.", "teacher": _TEACHER})
    assert prepared["scope"] == "curriculum"
    result = validate_entity_data(EntityType.EXERCISE, prepared, _FILE)
    assert result.is_ok


def test_ingestion_accepts_explicit_curriculum_scope() -> None:
    prepared = _prepared(
        {"title": "Sample", "instructions": "Do.", "scope": "curriculum", "teacher": _TEACHER}
    )
    result = validate_entity_data(EntityType.EXERCISE, prepared, _FILE)
    assert result.is_ok


def test_ingestion_requires_the_exercise_to_name_its_teacher() -> None:
    """ADR-091 S3: every exercise file names its teacher; the refusal names the file."""
    prepared = _prepared({"title": "Sample", "instructions": "Do."})
    result = validate_entity_data(EntityType.EXERCISE, prepared, _FILE)
    assert result.is_error
    error = result.expect_error()
    assert error.details["field"] == "teacher"
    assert _FILE.name in error.display_message


@pytest.mark.parametrize("scope", ["personal", "assigned", "assessment"])
def test_ingestion_rejects_any_other_scope(scope: str) -> None:
    """CURRICULUM is the one scope (ADR-091 S4); the retired values are refused."""
    prepared = _prepared({"title": "Sample", "instructions": "Do.", "scope": scope})
    result = validate_entity_data(EntityType.EXERCISE, prepared, _FILE)
    assert result.is_error
    assert "curriculum" in str(result.expect_error().message)


# ============================================================================
# 3. BATCH ITEM PREPARATION (edge-source survival)
# ============================================================================


def test_batch_items_keep_registry_edge_sources_dropped_by_mapper() -> None:
    """to_neo4j_node strips RELATIONSHIP_SKIP_FIELDS (e.g. exercise_uids), but
    the bulk-upsert Cypher template reads those keys off the item to MERGE the
    edges. prepare_batch_items must restore rel_config keys onto the item while
    keeping them out of _node_props (2026-07-03: PathStep exercise_uids anchors
    silently produced zero HAS_EXERCISE edges)."""
    from adapters.persistence.neo4j.batch_preparer import prepare_batch_items
    from core.services.ingestion.config import ENTITY_CONFIGS

    rel_config = ENTITY_CONFIGS[EntityType.PATH_STEP].relationship_config
    assert rel_config is not None and "exercise_uids" in rel_config

    entity = {
        "uid": "ps.test.step",
        "entity_type": "path_step",
        "title": "Test Step",
        "exercise_uids": ["ex.test.one"],  # in the mapper's skip set
        "uses_kus": ["ku.test.one"],  # NOT in the skip set (control)
    }
    item = prepare_batch_items([entity], rel_config=rel_config)[0]

    assert item["exercise_uids"] == ["ex.test.one"]
    assert item["uses_kus"] == ["ku.test.one"]
    assert "exercise_uids" not in item["_node_props"]
    assert "uses_kus" not in item["_node_props"]
