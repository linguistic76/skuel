"""
Tests for embedding text builder utility.

Covers all 7 entity types with both dict and model inputs.
"""

from dataclasses import dataclass

import pytest

from core.models.enums.entity_enums import EntityType
from core.utils.embedding_text_builder import build_embedding_text


# Test models (mimicking domain models)
@dataclass
class MockTask:
    title: str
    description: str | None = None


@dataclass
class MockGoal:
    title: str
    description: str | None = None
    vision_statement: str | None = None


@dataclass
class MockHabit:
    name: str
    title: str | None = None
    description: str | None = None
    cue: str | None = None
    reward: str | None = None


@dataclass
class MockEvent:
    title: str
    description: str | None = None
    location: str | None = None


@dataclass
class MockChoice:
    title: str
    description: str | None = None
    decision_context: str | None = None
    outcome: str | None = None


@dataclass
class MockPrinciple:
    title: str
    statement: str | None = None
    description: str | None = None


@dataclass
class MockKU:
    title: str
    content: str | None = None
    summary: str | None = None


class TestBuildEmbeddingTextFromDict:
    """Test embedding text extraction from dict (ingestion path)."""

    def test_task_with_all_fields(self):
        data = {"title": "Fix bug", "description": "Fix login error"}
        result = build_embedding_text(EntityType.TASK, data)
        assert result == "Fix bug\nFix login error"

    def test_task_with_title_only(self):
        data = {"title": "Fix bug"}
        result = build_embedding_text(EntityType.TASK, data)
        assert result == "Fix bug"

    def test_goal_with_all_fields(self):
        data = {
            "title": "Learn Python",
            "description": "Master basics",
            "vision_statement": "Become expert",
        }
        result = build_embedding_text(EntityType.GOAL, data)
        assert result == "Learn Python\nMaster basics\nBecome expert"

    def test_habit_with_all_fields(self):
        data = {
            "name": "Morning run",
            "title": "Exercise",
            "description": "Stay fit",
            "cue": "Wake up",
            "reward": "Energy",
        }
        result = build_embedding_text(EntityType.HABIT, data)
        assert result == "Morning run\nExercise\nStay fit\nWake up\nEnergy"

    def test_event_with_all_fields(self):
        data = {
            "title": "Team meeting",
            "description": "Sprint planning",
            "location": "Office",
        }
        result = build_embedding_text(EntityType.EVENT, data)
        assert result == "Team meeting\nSprint planning\nOffice"

    def test_choice_with_all_fields(self):
        data = {
            "title": "Career move",
            "description": "Job offer",
            "decision_context": "Current vs new",
            "outcome": "Accepted",
        }
        result = build_embedding_text(EntityType.CHOICE, data)
        assert result == "Career move\nJob offer\nCurrent vs new\nAccepted"

    def test_principle_with_all_fields(self):
        data = {
            "title": "Integrity",
            "statement": "Be honest",
            "description": "Always tell truth",
        }
        result = build_embedding_text(EntityType.PRINCIPLE, data)
        assert result == "Integrity\nBe honest\nAlways tell truth"

    def test_ku_with_all_fields_uses_double_newlines(self):
        data = {
            "title": "Python",
            "content": "Programming language",
            "summary": "High-level",
        }
        result = build_embedding_text(EntityType.LESSON, data)
        assert result == "Python\n\nProgramming language\n\nHigh-level"

    def test_empty_dict_returns_empty_string(self):
        result = build_embedding_text(EntityType.TASK, {})
        assert result == ""

    def test_dict_with_empty_string_fields(self):
        data = {"title": "Fix bug", "description": ""}
        result = build_embedding_text(EntityType.TASK, data)
        assert result == "Fix bug"

    def test_dict_with_whitespace_only_fields(self):
        data = {"title": "Fix bug", "description": "   "}
        result = build_embedding_text(EntityType.TASK, data)
        assert result == "Fix bug"

    def test_dict_with_none_fields(self):
        data = {"title": "Fix bug", "description": None}
        result = build_embedding_text(EntityType.TASK, data)
        assert result == "Fix bug"

    def test_dict_with_missing_fields(self):
        data = {"title": "Fix bug"}  # description missing
        result = build_embedding_text(EntityType.TASK, data)
        assert result == "Fix bug"


class TestBuildEmbeddingTextFromModel:
    """Test embedding text extraction from domain models (worker path)."""

    def test_task_model_with_all_fields(self):
        task = MockTask(title="Fix bug", description="Fix login error")
        result = build_embedding_text(EntityType.TASK, task)
        assert result == "Fix bug\nFix login error"

    def test_task_model_with_title_only(self):
        task = MockTask(title="Fix bug")
        result = build_embedding_text(EntityType.TASK, task)
        assert result == "Fix bug"

    def test_goal_model_with_all_fields(self):
        goal = MockGoal(
            title="Learn Python",
            description="Master basics",
            vision_statement="Become expert",
        )
        result = build_embedding_text(EntityType.GOAL, goal)
        assert result == "Learn Python\nMaster basics\nBecome expert"

    def test_habit_model_with_all_fields(self):
        habit = MockHabit(
            name="Morning run",
            title="Exercise",
            description="Stay fit",
            cue="Wake up",
            reward="Energy",
        )
        result = build_embedding_text(EntityType.HABIT, habit)
        assert result == "Morning run\nExercise\nStay fit\nWake up\nEnergy"

    def test_event_model_with_all_fields(self):
        event = MockEvent(title="Team meeting", description="Sprint planning", location="Office")
        result = build_embedding_text(EntityType.EVENT, event)
        assert result == "Team meeting\nSprint planning\nOffice"

    def test_choice_model_with_all_fields(self):
        choice = MockChoice(
            title="Career move",
            description="Job offer",
            decision_context="Current vs new",
            outcome="Accepted",
        )
        result = build_embedding_text(EntityType.CHOICE, choice)
        assert result == "Career move\nJob offer\nCurrent vs new\nAccepted"

    def test_principle_model_with_all_fields(self):
        principle = MockPrinciple(
            title="Integrity", statement="Be honest", description="Always tell truth"
        )
        result = build_embedding_text(EntityType.PRINCIPLE, principle)
        assert result == "Integrity\nBe honest\nAlways tell truth"

    def test_ku_model_with_all_fields_uses_double_newlines(self):
        ku = MockKU(title="Python", content="Programming language", summary="High-level")
        result = build_embedding_text(EntityType.LESSON, ku)
        assert result == "Python\n\nProgramming language\n\nHigh-level"

    def test_model_with_none_fields(self):
        task = MockTask(title="Fix bug", description=None)
        result = build_embedding_text(EntityType.TASK, task)
        assert result == "Fix bug"

    def test_model_with_empty_string_fields(self):
        task = MockTask(title="Fix bug", description="")
        result = build_embedding_text(EntityType.TASK, task)
        assert result == "Fix bug"

    def test_model_with_whitespace_only_fields(self):
        task = MockTask(title="Fix bug", description="   ")
        result = build_embedding_text(EntityType.TASK, task)
        assert result == "Fix bug"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_unknown_entity_type_returns_empty_string(self):
        # Create a mock entity type that's not in EMBEDDING_FIELD_MAPS
        data = {"title": "Test"}
        # Use a string cast to bypass enum validation
        result = build_embedding_text("unknown_type", data)  # type: ignore[arg-type]
        assert result == ""

    def test_all_fields_empty_returns_empty_string(self):
        data = {"title": "", "description": ""}
        result = build_embedding_text(EntityType.TASK, data)
        assert result == ""

    def test_all_fields_whitespace_returns_empty_string(self):
        data = {"title": "   ", "description": "   "}
        result = build_embedding_text(EntityType.TASK, data)
        assert result == ""

    def test_mixed_empty_and_present_fields(self):
        data = {"title": "", "description": "Has content", "extra": ""}
        result = build_embedding_text(EntityType.TASK, data)
        assert result == "Has content"

    def test_fields_with_leading_trailing_whitespace_are_stripped(self):
        data = {"title": "  Fix bug  ", "description": "  Login error  "}
        result = build_embedding_text(EntityType.TASK, data)
        assert result == "Fix bug\nLogin error"

    def test_numeric_values_are_converted_to_string(self):
        data = {"title": 123, "description": "Test"}  # type: ignore[dict-item]
        result = build_embedding_text(EntityType.TASK, data)
        assert result == "123\nTest"


class TestSeparatorLogic:
    """Test separator logic for different entity types."""

    def test_ku_uses_double_newline(self):
        data = {"title": "A", "content": "B", "summary": "C"}
        result = build_embedding_text(EntityType.LESSON, data)
        assert "\n\n" in result
        assert result == "A\n\nB\n\nC"

    def test_task_uses_single_newline(self):
        data = {"title": "A", "description": "B"}
        result = build_embedding_text(EntityType.TASK, data)
        assert "\n\n" not in result
        assert result == "A\nB"

    def test_goal_uses_single_newline(self):
        data = {"title": "A", "description": "B", "vision_statement": "C"}
        result = build_embedding_text(EntityType.GOAL, data)
        assert "\n\n" not in result
        assert result == "A\nB\nC"

    def test_habit_uses_single_newline(self):
        data = {"name": "A", "title": "B", "description": "C"}
        result = build_embedding_text(EntityType.HABIT, data)
        assert "\n\n" not in result
        assert result == "A\nB\nC"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
