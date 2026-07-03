"""entity_type integrity — systems-review G6 (Arc C).

The base EntityDTO used to default entity_type to KU, so any service that
forgot to pass it persisted Habits/Goals as ``entity_type='ku'`` while the
frozen models silently force-corrected on read. These tests pin the fix:

- base + intermediate DTOs REQUIRE entity_type (TypeError without it),
- every leaf DTO defaults to its own honest type,
- frozen leaf models default honestly and RAISE on a mismatch instead of
  silently correcting it.
"""

from __future__ import annotations

import pytest

from core.models.choice.choice_dto import ChoiceDTO
from core.models.curriculum_dto import CurriculumDTO
from core.models.entity_dto import EntityDTO
from core.models.enums.entity_enums import EntityType
from core.models.event.event_dto import EventDTO
from core.models.exercises.exercise_dto import ExerciseDTO
from core.models.exercises.revised_exercise_dto import RevisedExerciseDTO
from core.models.forms.form_submission_dto import FormSubmissionDTO
from core.models.forms.form_template_dto import FormTemplateDTO
from core.models.goal.goal import Goal
from core.models.goal.goal_dto import GoalDTO
from core.models.habit.habit import Habit
from core.models.habit.habit_dto import HabitDTO
from core.models.interaction.interaction_dto import InteractionDTO
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.models.life_path.life_path_dto import LifePathDTO
from core.models.pathways.learning_path_dto import LearningPathDTO
from core.models.pathways.path_step_dto import PathStepDTO
from core.models.principle.principle_dto import PrincipleDTO
from core.models.report.activity_report_dto import ActivityReportDTO
from core.models.report.entry_report_dto import EntryReportDTO
from core.models.resource.resource_dto import ResourceDTO
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO
from core.models.templates.choice_template_dto import ChoiceTemplateDTO
from core.models.templates.event_template_dto import EventTemplateDTO
from core.models.templates.goal_template_dto import GoalTemplateDTO
from core.models.templates.habit_template_dto import HabitTemplateDTO
from core.models.templates.principle_template_dto import PrincipleTemplateDTO
from core.models.templates.task_template_dto import TaskTemplateDTO
from core.models.user_entry.user_entry_dto import UserEntryDTO
from core.models.user_owned_dto import UserOwnedDTO

LEAF_DTO_TYPES = [
    (KuDTO, EntityType.KU),
    (TaskDTO, EntityType.TASK),
    (GoalDTO, EntityType.GOAL),
    (HabitDTO, EntityType.HABIT),
    (EventDTO, EntityType.EVENT),
    (ChoiceDTO, EntityType.CHOICE),
    (PrincipleDTO, EntityType.PRINCIPLE),
    (UserEntryDTO, EntityType.USER_ENTRY),
    (InteractionDTO, EntityType.INTERACTION),
    (LifePathDTO, EntityType.LIFE_PATH),
    (ExerciseDTO, EntityType.EXERCISE),
    (RevisedExerciseDTO, EntityType.REVISED_EXERCISE),
    (PathStepDTO, EntityType.PATH_STEP),
    (LearningPathDTO, EntityType.LEARNING_PATH),
    (ResourceDTO, EntityType.RESOURCE),
    (ActivityReportDTO, EntityType.ACTIVITY_REPORT),
    (EntryReportDTO, EntityType.ENTRY_REPORT),
    (FormSubmissionDTO, EntityType.FORM_SUBMISSION),
    (FormTemplateDTO, EntityType.FORM_TEMPLATE),
    (TaskTemplateDTO, EntityType.TASK_TEMPLATE),
    (GoalTemplateDTO, EntityType.GOAL_TEMPLATE),
    (HabitTemplateDTO, EntityType.HABIT_TEMPLATE),
    (EventTemplateDTO, EntityType.EVENT_TEMPLATE),
    (ChoiceTemplateDTO, EntityType.CHOICE_TEMPLATE),
    (PrincipleTemplateDTO, EntityType.PRINCIPLE_TEMPLATE),
]


class TestDTOTier:
    @pytest.mark.parametrize("dto_class", [EntityDTO, UserOwnedDTO, CurriculumDTO])
    def test_base_and_intermediate_dtos_require_entity_type(self, dto_class):
        with pytest.raises(TypeError, match="entity_type"):
            dto_class(uid="x", title="t")

    def test_base_dto_accepts_explicit_entity_type(self):
        dto = EntityDTO(uid="x", title="t", entity_type=EntityType.KU)
        assert dto.entity_type is EntityType.KU

    @pytest.mark.parametrize(("dto_class", "expected"), LEAF_DTO_TYPES)
    def test_leaf_dto_defaults_to_its_own_type(self, dto_class, expected):
        assert dto_class(uid="x", title="t").entity_type is expected

    def test_habit_dto_dict_round_trip_carries_honest_type(self):
        """The G6 write path: dto.to_dict() is what gets persisted."""
        dto = HabitDTO(uid="habit_x", title="t", user_uid="user_x")
        assert dto.to_dict()["entity_type"] == "habit"

    def test_goal_dto_dict_round_trip_carries_honest_type(self):
        dto = GoalDTO(uid="goal_x", title="t", user_uid="user_x")
        assert dto.to_dict()["entity_type"] == "goal"


class TestFrozenTier:
    @pytest.mark.parametrize(
        ("model", "kwargs", "expected"),
        [
            (Habit, {"uid": "habit_x", "title": "t", "user_uid": "u"}, EntityType.HABIT),
            (Goal, {"uid": "goal_x", "title": "t", "user_uid": "u"}, EntityType.GOAL),
            (Task, {"uid": "task_x", "title": "t", "user_uid": "u"}, EntityType.TASK),
            (Ku, {"uid": "ku_x", "title": "t"}, EntityType.KU),
        ],
    )
    def test_leaf_model_defaults_to_its_own_type(self, model, kwargs, expected):
        assert model(**kwargs).entity_type is expected

    @pytest.mark.parametrize(
        ("model", "kwargs"),
        [
            (Habit, {"uid": "habit_x", "title": "t", "user_uid": "u"}),
            (Goal, {"uid": "goal_x", "title": "t", "user_uid": "u"}),
            (Task, {"uid": "task_x", "title": "t", "user_uid": "u"}),
        ],
    )
    def test_leaf_model_raises_on_wrong_entity_type(self, model, kwargs):
        """The read-side mask is gone: a wrong persisted type fails loudly."""
        with pytest.raises(ValueError, match="entity_type"):
            model(entity_type=EntityType.KU, **kwargs)

    def test_ku_model_raises_on_wrong_entity_type(self):
        with pytest.raises(ValueError, match="entity_type"):
            Ku(uid="ku_x", title="t", entity_type=EntityType.HABIT)
