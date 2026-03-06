"""
Exercise-Curriculum Linking Tests
==================================

Validates of Ku hierarchy refactoring:
- EXERCISE_CONFIG in relationship registry
- ExerciseService curriculum linking methods
- ExerciseOperations protocol compliance
"""

from unittest.mock import AsyncMock

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import (
    ENTITY_TYPE_TO_LABEL,
    EXERCISE_CONFIG,
    LABEL_CONFIGS,
    LABEL_TO_DEFAULT_ENTITY_TYPE,
)
from core.ports.curriculum_protocols import ExerciseOperations
from core.services.exercises.exercise_service import ExerciseService
from core.utils.result_simplified import Result

# =========================================================================
# Registry Tests — EXERCISE_CONFIG in relationship registry
# =========================================================================


class TestExerciseRegistryConfig:
    """Verify EXERCISE_CONFIG is correctly registered."""

    def test_exercise_config_exists(self):
        """EXERCISE_CONFIG should be defined."""
        assert EXERCISE_CONFIG is not None

    def test_exercise_in_label_configs(self):
        """Exercise should be registered as virtual key in LABEL_CONFIGS."""
        assert "Exercise" in LABEL_CONFIGS
        assert LABEL_CONFIGS["Exercise"] is EXERCISE_CONFIG

    def test_exercise_in_ku_type_to_label(self):
        """EntityType.EXERCISE should map to 'Exercise' label."""
        assert ENTITY_TYPE_TO_LABEL[EntityType.EXERCISE] == "Exercise"

    def test_exercise_in_label_to_default_ku_type(self):
        """'Exercise' label should map to EntityType.EXERCISE."""
        assert LABEL_TO_DEFAULT_ENTITY_TYPE["Exercise"] == EntityType.EXERCISE

    def test_exercise_config_has_requires_knowledge(self):
        """EXERCISE_CONFIG should have REQUIRES_KNOWLEDGE outgoing relationship."""
        outgoing = EXERCISE_CONFIG.get_outgoing_relationships()
        rel_names = [r.relationship for r in outgoing]
        assert RelationshipName.REQUIRES_KNOWLEDGE in rel_names

    def test_exercise_config_has_for_group(self):
        """EXERCISE_CONFIG should have FOR_GROUP outgoing relationship."""
        outgoing = EXERCISE_CONFIG.get_outgoing_relationships()
        rel_names = [r.relationship for r in outgoing]
        assert RelationshipName.FOR_GROUP in rel_names

    def test_exercise_config_has_fulfills_exercise_incoming(self):
        """EXERCISE_CONFIG should have FULFILLS_EXERCISE incoming (submissions)."""
        incoming = EXERCISE_CONFIG.get_incoming_relationships()
        rel_names = [r.relationship for r in incoming]
        assert RelationshipName.FULFILLS_EXERCISE in rel_names

    def test_exercise_config_prerequisite_relationships(self):
        """Prerequisite relationships should include REQUIRES_KNOWLEDGE."""
        assert (
            RelationshipName.REQUIRES_KNOWLEDGE in EXERCISE_CONFIG.prerequisite_relationship_names
        )

    def test_exercise_config_entity_label(self):
        """Exercise entity uses :Entity label (all entity types share the :Entity base label)."""
        assert EXERCISE_CONFIG.entity_label == "Entity"

    def test_exercise_config_method_keys(self):
        """EXERCISE_CONFIG should expose expected method keys."""
        keys = EXERCISE_CONFIG.get_all_relationship_methods()
        assert "required_knowledge" in keys
        assert "target_group" in keys
        assert "submissions" in keys


# =========================================================================
# Service Tests — ExerciseService curriculum linking methods
# =========================================================================


class TestExerciseServiceCurriculumLinking:
    """Test ExerciseService.link_to_curriculum and related methods."""

    def _make_service(self) -> tuple[ExerciseService, AsyncMock]:
        """Create ExerciseService with mocked backend."""
        backend = AsyncMock()
        service = ExerciseService(backend=backend)
        return service, backend

    @pytest.mark.anyio
    async def test_link_to_curriculum_success(self):
        """link_to_curriculum should delegate to backend.link_to_curriculum."""
        service, backend = self._make_service()
        backend.link_to_curriculum.return_value = Result.ok(True)

        result = await service.link_to_curriculum("ex_test_123", "ku_python_abc")

        assert result.is_ok
        assert result.value is True
        backend.link_to_curriculum.assert_called_once_with("ex_test_123", "ku_python_abc")

    @pytest.mark.anyio
    async def test_link_to_curriculum_not_found(self):
        """link_to_curriculum should propagate NotFound from backend."""
        service, backend = self._make_service()
        from core.utils.result_simplified import Errors

        backend.link_to_curriculum.return_value = Result.fail(
            Errors.not_found(
                resource="Exercise or Curriculum KU", identifier="ex_missing -> ku_missing"
            )
        )

        result = await service.link_to_curriculum("ex_missing", "ku_missing")

        assert result.is_error

    @pytest.mark.anyio
    async def test_unlink_from_curriculum_success(self):
        """unlink_from_curriculum should delegate to backend.unlink_from_curriculum."""
        service, backend = self._make_service()
        backend.unlink_from_curriculum.return_value = Result.ok(True)

        result = await service.unlink_from_curriculum("ex_test_123", "ku_python_abc")

        assert result.is_ok
        assert result.value is True
        backend.unlink_from_curriculum.assert_called_once_with("ex_test_123", "ku_python_abc")

    @pytest.mark.anyio
    async def test_unlink_from_curriculum_not_found(self):
        """unlink_from_curriculum should propagate NotFound from backend."""
        service, backend = self._make_service()
        from core.utils.result_simplified import Errors

        backend.unlink_from_curriculum.return_value = Result.fail(
            Errors.not_found(
                resource="REQUIRES_KNOWLEDGE relationship", identifier="ex_test_123 -> ku_missing"
            )
        )

        result = await service.unlink_from_curriculum("ex_test_123", "ku_missing")

        assert result.is_error

    @pytest.mark.anyio
    async def test_get_required_knowledge_success(self):
        """get_required_knowledge should delegate to backend.get_required_knowledge."""
        service, backend = self._make_service()
        backend.get_required_knowledge.return_value = Result.ok(
            [
                {
                    "uid": "ku_python_abc",
                    "title": "Python Basics",
                    "entity_type": "curriculum",
                    "complexity": "beginner",
                    "learning_level": "beginner",
                },
                {
                    "uid": "ku_testing_def",
                    "title": "Testing Fundamentals",
                    "entity_type": "curriculum",
                    "complexity": "intermediate",
                    "learning_level": "intermediate",
                },
            ]
        )

        result = await service.get_required_knowledge("ex_test_123")

        assert result.is_ok
        assert len(result.value) == 2
        assert result.value[0]["uid"] == "ku_python_abc"
        assert result.value[1]["title"] == "Testing Fundamentals"
        backend.get_required_knowledge.assert_called_once_with("ex_test_123")

    @pytest.mark.anyio
    async def test_get_required_knowledge_empty(self):
        """get_required_knowledge should return empty list when no links exist."""
        service, backend = self._make_service()
        backend.get_required_knowledge.return_value = Result.ok([])

        result = await service.get_required_knowledge("ex_no_links")

        assert result.is_ok
        assert result.value == []

    @pytest.mark.anyio
    async def test_get_exercises_for_curriculum_success(self):
        """get_exercises_for_curriculum should return exercises requiring this KU."""
        service, backend = self._make_service()
        backend.execute_query.return_value = Result.ok(
            [
                {
                    "uid": "ex_essay_123",
                    "title": "Write a Python Essay",
                    "scope": "personal",
                    "due_date": None,
                    "status": "draft",
                },
            ]
        )

        result = await service.get_exercises_for_curriculum("ku_python_abc")

        assert result.is_ok
        assert len(result.value) == 1
        assert result.value[0]["uid"] == "ex_essay_123"

    @pytest.mark.anyio
    async def test_get_exercises_for_curriculum_empty(self):
        """get_exercises_for_curriculum should return empty list when no exercises link."""
        service, backend = self._make_service()
        backend.execute_query.return_value = Result.ok([])

        result = await service.get_exercises_for_curriculum("ku_unused_abc")

        assert result.is_ok
        assert result.value == []


# =========================================================================
# Protocol Compliance — ExerciseOperations includes curriculum methods
# =========================================================================


class TestExerciseOperationsProtocol:
    """Verify ExerciseOperations protocol includes curriculum linking methods."""

    def test_protocol_has_link_to_curriculum(self):
        """ExerciseOperations should declare link_to_curriculum."""
        assert hasattr(ExerciseOperations, "link_to_curriculum")

    def test_protocol_has_unlink_from_curriculum(self):
        """ExerciseOperations should declare unlink_from_curriculum."""
        assert hasattr(ExerciseOperations, "unlink_from_curriculum")

    def test_protocol_has_get_required_knowledge(self):
        """ExerciseOperations should declare get_required_knowledge."""
        assert hasattr(ExerciseOperations, "get_required_knowledge")

    def test_protocol_has_get_exercises_for_curriculum(self):
        """ExerciseOperations should declare get_exercises_for_curriculum."""
        assert hasattr(ExerciseOperations, "get_exercises_for_curriculum")

    def test_exercise_service_implements_protocol(self):
        """ExerciseService should be a runtime instance of ExerciseOperations."""
        assert issubclass(ExerciseService, ExerciseOperations)
