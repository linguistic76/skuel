"""
Unit Tests for ExerciseScope.CURRICULUM and the optional PathStep anchor
=========================================================================

Covers the 2026-07-03 scope-semantics ruling:
- CURRICULUM is the scope for content-vault-authored shared exercises
  (no user OWNS edge; anchored via ``exercise_uids`` in PathStep YAML).
- PERSONAL exercises no longer require a PathStep anchor — unanchored
  personal templates (the /submit save-template flow) are legitimate.
- The API rejects CURRICULUM (vault-ingested only); ingestion rejects
  everything EXCEPT curriculum (no owner mechanism at the file boundary).

Test Categories:
1. Enum + model validity (Exercise.is_valid across scopes)
2. API boundary (ExerciseCreateRequest model_validator)
3. Ingestion boundary (validate_entity_data guard + config scope default)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from core.models.enums.entity_enums import EntityType
from core.models.enums.user_entry_enums import ExerciseScope
from core.models.exercises.exercise import Exercise
from core.models.exercises.exercise_request import ExerciseCreateRequest
from core.services.exercises.exercise_service import ExerciseService
from core.services.ingestion.preparer import prepare_entity_data
from core.services.ingestion.validator import validate_entity_data

# ============================================================================
# 1. ENUM + MODEL VALIDITY
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


def test_curriculum_scope_exists() -> None:
    assert ExerciseScope.CURRICULUM.value == "curriculum"
    assert ExerciseScope("curriculum") is ExerciseScope.CURRICULUM


def test_personal_exercise_valid_without_path_step_anchor() -> None:
    """The bless: unanchored personal templates are legitimate."""
    exercise = _exercise(scope=ExerciseScope.PERSONAL)
    assert exercise.path_step_uid is None
    assert exercise.is_valid()


def test_curriculum_exercise_valid_without_owner_or_anchor() -> None:
    exercise = _exercise(scope=ExerciseScope.CURRICULUM)
    assert exercise.owner_uid is None
    assert exercise.is_valid()


def test_assigned_exercise_still_requires_group() -> None:
    assert not _exercise(scope=ExerciseScope.ASSIGNED).is_valid()
    assert _exercise(scope=ExerciseScope.ASSIGNED, group_uid="group_x").is_valid()


def test_assessment_exercise_still_requires_rubric() -> None:
    assert not _exercise(scope=ExerciseScope.ASSESSMENT).is_valid()
    assert _exercise(
        scope=ExerciseScope.ASSESSMENT,
        scoring_rubric=({"name": "clarity", "weight": 1.0},),
    ).is_valid()


# ============================================================================
# 2. API BOUNDARY
# ============================================================================


def test_api_accepts_unanchored_personal() -> None:
    request = ExerciseCreateRequest(name="My template", instructions="Reflect.")
    assert request.scope is ExerciseScope.PERSONAL
    assert request.path_step_uid is None


def test_api_rejects_curriculum_scope() -> None:
    with pytest.raises(ValidationError, match="content vault"):
        ExerciseCreateRequest(
            name="Vault thing",
            instructions="Nope.",
            scope=ExerciseScope.CURRICULUM,
        )


def test_api_still_enforces_assigned_group() -> None:
    with pytest.raises(ValidationError, match="group_uid"):
        ExerciseCreateRequest(
            name="Class task",
            instructions="Do.",
            scope=ExerciseScope.ASSIGNED,
        )


def test_api_rejects_invalid_domain() -> None:
    """Conversion does ``Domain(schema.domain)`` — an unvalidated string used to
    surface as a 500 there instead of a 422 here."""
    with pytest.raises(ValidationError, match="invalid domain"):
        ExerciseCreateRequest(
            name="Bad domain",
            instructions="Do.",
            domain="Activity Domains",
        )


def test_api_accepts_valid_domain() -> None:
    request = ExerciseCreateRequest(name="Tasks list", instructions="List.", domain="tasks")
    assert request.domain == "tasks"


def test_update_api_rejects_invalid_domain() -> None:
    from core.models.exercises.exercise_request import ExerciseUpdateRequest

    with pytest.raises(ValidationError, match="invalid domain"):
        ExerciseUpdateRequest(domain="not-a-domain")


# ============================================================================
# 3. INGESTION BOUNDARY
# ============================================================================

_FILE = Path("exercise_sample.md")


def _prepared(data: dict[str, object]) -> dict[str, object]:
    return prepare_entity_data(EntityType.EXERCISE, dict(data), None, _FILE)


def test_ingestion_defaults_absent_scope_to_curriculum() -> None:
    """Config default wins over the model default (PERSONAL), which would
    create an ownerless 'personal' exercise no view can surface."""
    prepared = _prepared({"title": "Sample", "instructions": "Do."})
    assert prepared["scope"] == "curriculum"
    result = validate_entity_data(EntityType.EXERCISE, prepared, _FILE)
    assert result.is_ok


def test_ingestion_accepts_explicit_curriculum_scope() -> None:
    prepared = _prepared({"title": "Sample", "instructions": "Do.", "scope": "curriculum"})
    result = validate_entity_data(EntityType.EXERCISE, prepared, _FILE)
    assert result.is_ok


@pytest.mark.parametrize("scope", ["personal", "assigned", "assessment"])
def test_ingestion_rejects_owner_bound_scopes(scope: str) -> None:
    prepared = _prepared({"title": "Sample", "instructions": "Do.", "scope": scope})
    result = validate_entity_data(EntityType.EXERCISE, prepared, _FILE)
    assert result.is_error
    assert "curriculum" in str(result.expect_error().message)


# ============================================================================
# 4. UPDATE PATHS PUBLISH EMBEDDING REFRESH (ADR-074)
# ============================================================================


def _service_with_mocked_super() -> "ExerciseService":
    from unittest.mock import MagicMock

    service = ExerciseService.__new__(ExerciseService)
    service.event_bus = MagicMock()
    service.logger = MagicMock()
    return service


@pytest.mark.parametrize("method", ["update", "update_for_user"])
@pytest.mark.asyncio
async def test_both_update_paths_publish_embedding_refresh(method: str) -> None:
    """The CRUD route factory calls update_for_user() for exercises
    (ContentScope.USER_OWNED), and update() elsewhere — BOTH must publish the
    ADR-074 embedding event (Kody #496: only update() did)."""
    from unittest.mock import AsyncMock, patch

    from core.models.update_contracts import RawChanges
    from core.services.mixins.crud_operations_mixin import CrudOperationsMixin

    service = _service_with_mocked_super()
    exercise = _exercise(scope=ExerciseScope.PERSONAL)
    updates = RawChanges({"instructions": "New text."})

    from core.utils.result_simplified import Result

    with (
        patch.object(CrudOperationsMixin, method, AsyncMock(return_value=Result.ok(exercise))),
        patch(
            "core.events.embedding_publisher.publish_embedding_requested", new_callable=AsyncMock
        ) as publish,
    ):
        if method == "update":
            result = await service.update("ex.test.sample", updates)
        else:
            result = await service.update_for_user("ex.test.sample", updates, "user_test")

    assert result.is_ok
    publish.assert_awaited_once()
    assert publish.await_args is not None
    assert publish.await_args.args[1] is EntityType.EXERCISE
    assert set(publish.await_args.kwargs["changed_fields"]) == {"instructions"}


# ============================================================================
# 5. BATCH ITEM PREPARATION (edge-source survival)
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
