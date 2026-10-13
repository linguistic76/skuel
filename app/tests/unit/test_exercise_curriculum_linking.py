"""
Exercise-Curriculum Linking Tests
==================================

Validates:
- EXERCISE_CONFIG in relationship registry
- ExerciseService curriculum-link reads (the vault writes the links, ADR-091 S4)
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
from core.models.type_hints import UserUID
from core.ports.curriculum_protocols import ExerciseOperations
from core.services.exercises.exercise_service import ExerciseService
from core.utils.result_simplified import ErrorCategory, Result

_OWNER = UserUID("user_owner")


# =========================================================================
# Registry Tests — EXERCISE_CONFIG in relationship registry
# =========================================================================


class TestExerciseRegistryConfig:
    """Verify EXERCISE_CONFIG is correctly registered."""

    def test_exercise_config_exists(self):
        """EXERCISE_CONFIG should be defined."""
        assert EXERCISE_CONFIG is not None

    def test_exercise_in_label_configs(self):
        """Exercise should be registered under its label in LABEL_CONFIGS."""
        assert "Exercise" in LABEL_CONFIGS
        assert LABEL_CONFIGS["Exercise"] is EXERCISE_CONFIG

    def test_exercise_in_entity_type_to_label(self):
        """EntityType.EXERCISE should map to 'Exercise' label."""
        assert ENTITY_TYPE_TO_LABEL[EntityType.EXERCISE] == "Exercise"

    def test_exercise_in_label_to_default_entity_type(self):
        """'Exercise' label should map to EntityType.EXERCISE."""
        assert LABEL_TO_DEFAULT_ENTITY_TYPE["Exercise"] == EntityType.EXERCISE

    def test_exercise_config_has_requires_knowledge(self):
        """EXERCISE_CONFIG should have REQUIRES_KNOWLEDGE outgoing relationship."""
        outgoing = EXERCISE_CONFIG.get_outgoing_relationships()
        rel_names = [r.relationship for r in outgoing]
        assert RelationshipName.REQUIRES_KNOWLEDGE in rel_names

    def test_exercise_config_has_no_group_assignment(self):
        """No exercise is assigned to a group (ADR-091 S4): no SHARED_WITH_GROUP."""
        outgoing = EXERCISE_CONFIG.get_outgoing_relationships()
        rel_names = [r.relationship for r in outgoing]
        assert RelationshipName.SHARED_WITH_GROUP not in rel_names

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
        assert "shared_groups" not in keys
        assert "submissions" in keys


# =========================================================================
# Service Tests — ExerciseService curriculum linking methods
# =========================================================================


class TestExerciseServiceCurriculumLinking:
    """Test ExerciseService's curriculum-link reads."""

    def _make_service(self) -> tuple[ExerciseService, AsyncMock]:
        """Create ExerciseService with mocked backend."""
        backend = AsyncMock()
        service = ExerciseService(backend=backend)
        return service, backend

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
        """get_exercises_for_curriculum should delegate to backend.get_exercises_for_curriculum."""
        service, backend = self._make_service()
        backend.get_exercises_for_curriculum.return_value = Result.ok(
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

        result = await service.get_exercises_for_curriculum("ku_python_abc", _OWNER)

        assert result.is_ok
        assert len(result.value) == 1
        assert result.value[0]["uid"] == "ex_essay_123"
        backend.get_exercises_for_curriculum.assert_called_once_with("ku_python_abc", _OWNER)

    @pytest.mark.anyio
    async def test_get_exercises_for_curriculum_empty(self):
        """get_exercises_for_curriculum should return empty list when no exercises link."""
        service, backend = self._make_service()
        backend.get_exercises_for_curriculum.return_value = Result.ok([])

        result = await service.get_exercises_for_curriculum("ku_unused_abc", _OWNER)

        assert result.is_ok
        assert result.value == []

    @pytest.mark.anyio
    async def test_get_required_knowledge_for_user_passes_the_caller_to_the_backend(self):
        """The audience read hands the backend the exercise AND the caller."""
        service, backend = self._make_service()
        backend.get_required_knowledge_for_user.return_value = Result.ok(
            [
                {
                    "uid": "ku_python_abc",
                    "title": "Python Basics",
                    "entity_type": "ku",
                    "complexity": None,
                    "learning_level": None,
                }
            ]
        )

        result = await service.get_required_knowledge_for_user("ex_test_123", _OWNER)

        assert result.is_ok
        assert [ku["uid"] for ku in result.value] == ["ku_python_abc"]
        backend.get_required_knowledge_for_user.assert_called_once_with("ex_test_123", _OWNER)

    @pytest.mark.anyio
    async def test_get_required_knowledge_for_user_is_not_found_for_a_missing_exercise(self):
        """The backend's None (no such exercise) is a not-found of the exercise."""
        service, backend = self._make_service()
        backend.get_required_knowledge_for_user.return_value = Result.ok(None)

        result = await service.get_required_knowledge_for_user("ex_test_123", _OWNER)

        assert result.is_error
        error = result.expect_error()
        assert error.category == ErrorCategory.NOT_FOUND
        assert "ex_test_123" in str(error)


# =========================================================================
# Protocol Compliance — ExerciseOperations includes curriculum methods
# =========================================================================


class TestExerciseOperationsProtocol:
    """Verify ExerciseOperations declares the curriculum-link reads and no writers."""

    @pytest.mark.parametrize(
        "writer",
        ["admit_requirement_change", "link_to_curriculum", "unlink_from_curriculum"],
    )
    def test_protocol_has_no_requirement_writer(self, writer):
        """The requirement doors are retired (ADR-091 S4)."""
        assert not hasattr(ExerciseOperations, writer)
        assert not hasattr(ExerciseService, writer)

    def test_protocol_has_get_required_knowledge(self):
        """ExerciseOperations should declare get_required_knowledge."""
        assert hasattr(ExerciseOperations, "get_required_knowledge")

    def test_protocol_has_get_exercises_for_curriculum(self):
        """ExerciseOperations should declare get_exercises_for_curriculum."""
        assert hasattr(ExerciseOperations, "get_exercises_for_curriculum")

    def test_exercise_service_implements_protocol(self):
        """ExerciseService should be a runtime instance of ExerciseOperations."""
        assert issubclass(ExerciseService, ExerciseOperations)
