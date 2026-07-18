"""
Unit tests for ConversionServiceV2 — the request→domain conversion choke point.

Testing-gap roadmap item 4: ConversionServiceV2 is THE single request→domain
converter for all create paths (CRUDRouteFactory registry lookup + templates_ui),
yet until now it had only indirect coverage through route-factory tests. These
tests exercise the converters directly, mock-free — every converter is a sync
classmethod, pure except the uuid4 fallback and datetime.now() timestamp
stamping.

Covers:
- The generic engine (uid/user_uid stamping, timestamp auto-stamp + override,
  uuid4 fallback, silent field filtering)
- Domain-specific converters (Habit, Principle, Choice, Exercise, Group)
- Activity Template converters (RelativeOffsetDTO → RelativeOffset,
  list → tuple coercion, deliberate Phase-7 complex-field deferral)
- CONVERTER_REGISTRY completeness and the exact CRUDRouteFactory calling
  convention (adapters/inbound/route_factories/crud_route_factory.py ~L394-400)
"""

import dataclasses
import uuid
from datetime import datetime

import pytest

from core.models.choice.choice import Choice
from core.models.choice.choice_option import ChoiceOption
from core.models.choice.choice_request import ChoiceCreateRequest, ChoiceOptionRequest
from core.models.enums import Domain
from core.models.enums.entity_enums import EntityType
from core.models.event.event_request import EventCreateRequest
from core.models.exercises.exercise import Exercise
from core.models.exercises.exercise_request import ExerciseCreateRequest
from core.models.exercises.revised_exercise_request import RevisedExerciseCreateRequest
from core.models.forms.form_template_request import FormTemplateCreateRequest
from core.models.goal.goal_request import GoalCreateRequest
from core.models.group.group import Group
from core.models.group.group_request import GroupCreateRequest
from core.models.habit.habit import Habit
from core.models.habit.habit_request import HabitCreateRequest
from core.models.principle.principle import Principle
from core.models.principle.principle_request import PrincipleCreateRequest
from core.models.task.task import Task
from core.models.task.task_request import TaskCreateRequest
from core.models.templates.choice_template import ChoiceTemplate
from core.models.templates.choice_template_request import ChoiceTemplateCreateRequest
from core.models.templates.event_template_request import EventTemplateCreateRequest
from core.models.templates.goal_template import GoalTemplate
from core.models.templates.goal_template_request import GoalTemplateCreateRequest
from core.models.templates.habit_template_request import HabitTemplateCreateRequest
from core.models.templates.principle_template_request import PrincipleTemplateCreateRequest
from core.models.templates.relative_offset import RelativeOffset
from core.models.templates.relative_offset_dto import RelativeOffsetDTO
from core.models.templates.task_template import TaskTemplate
from core.models.templates.task_template_request import TaskTemplateCreateRequest
from core.services.conversion_service import ConversionServiceV2

FIXED_CREATED_AT = datetime(2026, 1, 2, 3, 4, 5)


def field_names(instance_or_class: object) -> set[str]:
    """Dataclass field names — the no-hasattr way to assert field presence/absence."""
    return {f.name for f in dataclasses.fields(instance_or_class)}


# =============================================================================
# GENERIC ENGINE (via task_create_to_pure — the thinnest wrapper)
# =============================================================================


class TestGenericEngineViaTask:
    """create_to_pure semantics observed through the Task converter."""

    def test_uid_user_uid_and_title_stamped_onto_frozen_task(self) -> None:
        task = ConversionServiceV2.task_create_to_pure(
            TaskCreateRequest(title="X"), uid="task:t1", user_uid="user_1"
        )

        assert type(task) is Task  # the frozen domain dataclass, not a dict/DTO
        assert task.uid == "task:t1"
        assert task.user_uid == "user_1"  # Task HAS user_uid (UserOwnedEntity)
        assert task.title == "X"
        assert task.entity_type == EntityType.TASK

        with pytest.raises(dataclasses.FrozenInstanceError):
            task.title = "mutated"  # type: ignore[misc]

    def test_timestamps_auto_stamped_as_datetimes(self) -> None:
        # Entity's timestamp fields are created_at/updated_at (there is no
        # created/updated pair on Entity) — the engine stamps whichever the
        # target dataclass declares.
        task = ConversionServiceV2.task_create_to_pure(
            TaskCreateRequest(title="X"), uid="task:t1", user_uid="user_1"
        )

        assert isinstance(task.created_at, datetime)
        assert isinstance(task.updated_at, datetime)

    def test_explicit_created_at_kwarg_not_overwritten_by_now(self) -> None:
        # extra_fields are applied AFTER timestamp stamping, so an explicit
        # created_at wins over the datetime.now() default.
        task = ConversionServiceV2.task_create_to_pure(
            TaskCreateRequest(title="X"),
            uid="task:t1",
            user_uid="user_1",
            created_at=FIXED_CREATED_AT,
        )

        assert task.created_at == FIXED_CREATED_AT

    def test_uid_none_falls_back_to_uuid4(self) -> None:
        task = ConversionServiceV2.task_create_to_pure(
            TaskCreateRequest(title="X"), user_uid="user_1"
        )

        # Parseable UUID string — exact value is nondeterministic by design.
        parsed = uuid.UUID(task.uid)
        assert str(parsed) == task.uid

    def test_extra_kwarg_not_on_dataclass_is_silently_dropped(self) -> None:
        task = ConversionServiceV2.task_create_to_pure(
            TaskCreateRequest(title="X"),
            uid="task:t1",
            user_uid="user_1",
            bogus_field="x",  # no TypeError — filtered before construction
        )

        assert "bogus_field" not in field_names(task)

    def test_request_only_fields_are_filtered_not_leaked(self) -> None:
        # TaskCreateRequest carries relationship-typed fields (edge material)
        # that have no Task column; the engine drops them silently.
        task = ConversionServiceV2.task_create_to_pure(
            TaskCreateRequest(title="X", applies_knowledge_uids=["ku.a"]),
            uid="task:t1",
            user_uid="user_1",
        )

        assert "applies_knowledge_uids" not in field_names(task)

    def test_tags_coerced_to_tuple_generically(self) -> None:
        # Entity.tags is declared tuple[str, ...]; model_dump() produces a
        # list, and the generic engine coerces every tuple-typed field so
        # frozen-dataclass immutability isn't undermined by mutable members.
        task = ConversionServiceV2.task_create_to_pure(
            TaskCreateRequest(title="X", tags=["deep-work"]),
            uid="task:t1",
            user_uid="user_1",
        )

        assert task.tags == ("deep-work",)
        assert isinstance(task.tags, tuple)


# =============================================================================
# HABIT
# =============================================================================


class TestHabitConversion:
    def test_target_days_per_week_int_passthrough(self) -> None:
        habit = ConversionServiceV2.habit_create_to_pure(
            HabitCreateRequest(title="Meditate", target_days_per_week=5),
            uid="habit:h1",
            user_uid="user_1",
        )

        assert type(habit) is Habit
        assert habit.target_days_per_week == 5
        assert isinstance(habit.target_days_per_week, int)
        assert habit.user_uid == "user_1"


# =============================================================================
# PRINCIPLE
# =============================================================================


class TestPrincipleConversion:
    def test_key_behaviors_and_tags_become_tuples(self) -> None:
        principle = ConversionServiceV2.principle_create_to_pure(
            PrincipleCreateRequest(
                title="Honesty",
                statement="Tell the truth",
                key_behaviors=["admit mistakes", "give real feedback"],
                decision_criteria=["is it true?"],
                tags=["character"],
            ),
            uid="principle:p1",
            user_uid="user_1",
        )

        assert type(principle) is Principle
        assert principle.key_behaviors == ("admit mistakes", "give real feedback")
        assert principle.tags == ("character",)

    def test_decision_criteria_request_only_field_filtered_out(self) -> None:
        # Principle has no decision_criteria field (it is absent from
        # Principle/PrincipleDTO — see the note in principle_request.py
        # to_intent docstring); the generic engine filters it out silently.
        principle = ConversionServiceV2.principle_create_to_pure(
            PrincipleCreateRequest(
                title="Honesty",
                statement="Tell the truth",
                decision_criteria=["is it true?"],
            ),
            uid="principle:p1",
            user_uid="user_1",
        )

        assert "decision_criteria" not in field_names(principle)


# =============================================================================
# CHOICE
# =============================================================================


class TestChoiceConversion:
    def test_str_list_fields_become_tuples(self) -> None:
        choice = ConversionServiceV2.choice_create_to_pure(
            ChoiceCreateRequest(
                title="Pick a database",
                description="Choose the graph store",
                decision_criteria=["cost", "maturity"],
                constraints=["one month"],
                stakeholders=["me"],
            ),
            uid="choice:c1",
            user_uid="user_1",
        )

        assert type(choice) is Choice
        assert choice.decision_criteria == ("cost", "maturity")
        assert choice.constraints == ("one month",)
        assert choice.stakeholders == ("me",)

    def test_nested_options_become_choice_option_tuple_with_deterministic_uids(self) -> None:
        choice = ConversionServiceV2.choice_create_to_pure(
            ChoiceCreateRequest(
                title="Pick a database",
                description="Choose the graph store",
                options=[
                    ChoiceOptionRequest(
                        title="Neo4j",
                        description="Graph native",
                        dependencies=["dep:docker"],
                        tags=["graph"],
                    ),
                    ChoiceOptionRequest(title="Postgres"),
                ],
            ),
            uid="choice:c1",
            user_uid="user_1",
        )

        assert isinstance(choice.options, tuple)
        assert len(choice.options) == 2
        first, second = choice.options
        assert type(first) is ChoiceOption
        assert first.uid == "choice:c1_option_0"
        assert second.uid == "choice:c1_option_1"
        assert first.title == "Neo4j"
        # Nested list fields on the option are tuple-ized too
        assert first.dependencies == ("dep:docker",)
        assert first.tags == ("graph",)
        assert second.dependencies == ()


# =============================================================================
# EXERCISE
# =============================================================================


class TestExerciseConversion:
    def make_request(self, **overrides: object) -> ExerciseCreateRequest:
        payload: dict[str, object] = {
            "name": "Daily Reflection",
            "instructions": "Reflect on the day.",
        }
        payload.update(overrides)
        return ExerciseCreateRequest.model_validate(payload)

    def test_title_from_name_and_entity_type_forced(self) -> None:
        exercise = ConversionServiceV2.exercise_create_to_pure(
            self.make_request(), uid="exercise:e1", user_uid="user_owner"
        )

        assert type(exercise) is Exercise
        assert exercise.title == "Daily Reflection"  # schema.name → title
        assert exercise.entity_type == EntityType.EXERCISE

    def test_domain_string_becomes_enum_and_defaults_to_knowledge(self) -> None:
        with_domain = ConversionServiceV2.exercise_create_to_pure(
            self.make_request(domain="personal"), uid="exercise:e1", user_uid="user_owner"
        )
        without_domain = ConversionServiceV2.exercise_create_to_pure(
            self.make_request(), uid="exercise:e2", user_uid="user_owner"
        )

        assert with_domain.domain == Domain.PERSONAL
        assert without_domain.domain == Domain.KNOWLEDGE

    def test_context_notes_default_empty_tuple(self) -> None:
        exercise = ConversionServiceV2.exercise_create_to_pure(
            self.make_request(), uid="exercise:e1", user_uid="user_owner"
        )

        assert exercise.context_notes == ()

    def test_user_uid_kwarg_maps_to_owner_uid(self) -> None:
        # Exercise has owner_uid, not user_uid (it is Curriculum, not
        # UserOwnedEntity). Ownership's single source is the user_uid KWARG
        # (auth context) — ExerciseCreateRequest carries no user_uid field.
        exercise = ConversionServiceV2.exercise_create_to_pure(
            self.make_request(), uid="exercise:e1", user_uid="user_owner"
        )

        assert exercise.owner_uid == "user_owner"
        assert "user_uid" not in field_names(exercise)

    def test_without_user_uid_kwarg_owner_uid_is_none(self) -> None:
        # Without the user_uid kwarg there is no ownership source, so
        # owner_uid stays at its None default — same convention as every
        # other converter (CRUDRouteFactory always supplies the kwarg).
        exercise = ConversionServiceV2.exercise_create_to_pure(
            self.make_request(), uid="exercise:e1"
        )

        assert exercise.owner_uid is None


# =============================================================================
# GROUP
# =============================================================================


class TestGroupConversion:
    def test_user_uid_maps_to_owner_uid(self) -> None:
        group = ConversionServiceV2.group_create_to_pure(
            GroupCreateRequest(name="Physics 101"), uid="group:g1", user_uid="user_teacher"
        )

        assert type(group) is Group
        assert group.owner_uid == "user_teacher"
        assert group.name == "Physics 101"
        assert group.uid == "group:g1"


# =============================================================================
# ACTIVITY TEMPLATES
# =============================================================================


class TestTaskTemplateConversion:
    def test_offsets_converted_and_none_offsets_stay_none(self) -> None:
        template = ConversionServiceV2.tasktemplate_create_to_pure(
            TaskTemplateCreateRequest(
                title="Weekly review",
                due_offset=RelativeOffsetDTO(days=7),
                tags=["review"],
            ),
            uid="tasktemplate:tt1",
        )

        assert type(template) is TaskTemplate
        assert template.due_offset == RelativeOffset(days=7)  # DTO → value via to_value()
        assert template.scheduled_offset is None
        assert template.recurrence_end_offset is None
        assert template.tags == ("review",)  # str-list → tuple

    def test_injected_user_uid_kwarg_silently_filtered(self) -> None:
        # Templates are PS-owned curriculum — no user_uid field. The
        # CRUDRouteFactory always injects user_uid=...; the generic filter
        # drops it rather than raising.
        template = ConversionServiceV2.tasktemplate_create_to_pure(
            TaskTemplateCreateRequest(title="Weekly review"),
            uid="tasktemplate:tt1",
            user_uid="user_1",
        )

        assert "user_uid" not in field_names(template)


class TestGoalTemplateConversion:
    def test_offsets_str_tuples_and_milestones_deferred(self) -> None:
        template = ConversionServiceV2.goaltemplate_create_to_pure(
            GoalTemplateCreateRequest(
                title="Learn Cypher",
                start_offset=RelativeOffsetDTO(days=1),
                # Authored milestones supplied but deliberately dropped below.
                milestones=[{"title": "First query"}],
                potential_obstacles=["time"],
                strategies=["daily practice"],
                tags=["learning"],
            ),
            uid="goaltemplate:gt1",
        )

        assert type(template) is GoalTemplate
        assert template.start_offset == RelativeOffset(days=1)
        assert template.target_offset is None
        assert template.potential_obstacles == ("time",)
        assert template.strategies == ("daily practice",)
        assert template.tags == ("learning",)
        # Phase-7 deferral (deliberate): complex_tuple_fields are ALWAYS forced
        # to () even when the request supplies values — nested authoring lands
        # with FormGenerator nested-dataclass support (Phase 7), so V1 refuses
        # to half-convert list[dict] milestones into Milestone instances.
        assert template.milestones == ()


class TestChoiceTemplateConversion:
    def test_offsets_str_tuples_and_options_deferred(self) -> None:
        template = ConversionServiceV2.choicetemplate_create_to_pure(
            ChoiceTemplateCreateRequest(
                title="Pick a stack",
                decision_deadline_offset=RelativeOffsetDTO(days=3, hours=2),
                # Authored options supplied but deliberately dropped below.
                options=[{"title": "Option A"}],
                decision_criteria=["fit"],
                constraints=["budget"],
                stakeholders=["team"],
                tags=["decision"],
            ),
            uid="choicetemplate:ct1",
        )

        assert type(template) is ChoiceTemplate
        assert template.decision_deadline_offset == RelativeOffset(days=3, hours=2)
        assert template.decision_criteria == ("fit",)
        assert template.constraints == ("budget",)
        assert template.stakeholders == ("team",)
        assert template.tags == ("decision",)
        # Phase-7 deferral (deliberate): options forced to empty tuple — see
        # _template_create_to_pure complex_tuple_fields docstring.
        assert template.options == ()


# =============================================================================
# CONVERTER REGISTRY
# =============================================================================


ALL_REGISTERED_REQUEST_TYPES = (
    TaskCreateRequest,
    EventCreateRequest,
    HabitCreateRequest,
    GoalCreateRequest,
    PrincipleCreateRequest,
    ChoiceCreateRequest,
    FormTemplateCreateRequest,
    ExerciseCreateRequest,
    RevisedExerciseCreateRequest,
    GroupCreateRequest,
    TaskTemplateCreateRequest,
    GoalTemplateCreateRequest,
    HabitTemplateCreateRequest,
    EventTemplateCreateRequest,
    ChoiceTemplateCreateRequest,
    PrincipleTemplateCreateRequest,
)


class TestConverterRegistry:
    def test_registry_has_exactly_16_entries(self) -> None:
        assert len(ConversionServiceV2.CONVERTER_REGISTRY) == 16
        assert set(ConversionServiceV2.CONVERTER_REGISTRY) == set(ALL_REGISTERED_REQUEST_TYPES)

    @pytest.mark.parametrize("request_type", ALL_REGISTERED_REQUEST_TYPES)
    def test_get_converter_returns_the_right_classmethod(self, request_type: type) -> None:
        converter = ConversionServiceV2.get_converter(request_type)

        assert converter is ConversionServiceV2.CONVERTER_REGISTRY[request_type]
        assert callable(converter)
        # Naming convention holds for all 16: FooCreateRequest → foo_create_to_pure
        expected_name = request_type.__name__.removesuffix("CreateRequest").lower()
        assert converter.__name__ == f"{expected_name}_create_to_pure"

    def test_get_converter_returns_none_for_unregistered_types(self) -> None:
        assert ConversionServiceV2.get_converter(dict) is None
        assert ConversionServiceV2.get_converter(RelativeOffsetDTO) is None


# =============================================================================
# REALISM: exact CRUDRouteFactory calling convention
# =============================================================================


class TestCrudRouteFactoryCallingConvention:
    def test_registry_lookup_then_positional_uid_keyword_user_uid(self) -> None:
        # Mirrors adapters/inbound/route_factories/crud_route_factory.py
        # (~L383-400): uid = f"{uid_prefix}:{uuid.uuid4().hex[:12]}", then
        # converter_method = ConversionServiceV2.get_converter(type(schema)),
        # then converter_method(schema, uid, user_uid=user_uid).
        schema = TaskCreateRequest(title="Route-created task")
        uid = f"task:{uuid.uuid4().hex[:12]}"

        converter_method = ConversionServiceV2.get_converter(type(schema))
        assert converter_method is not None

        entity = converter_method(schema, uid, user_uid="user_route")

        assert type(entity) is Task
        assert entity.uid == uid
        assert entity.user_uid == "user_route"
        assert entity.title == "Route-created task"
