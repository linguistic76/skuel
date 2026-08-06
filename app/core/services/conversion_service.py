"""
Unified Conversion Service V2
==============================

Refactored conversion service using generic methods to eliminate repetition.
Follows DRY principle with type-safe generic conversions.

Clean implementation with no backwards compatibility.
"""

__version__ = "2.0"

import uuid
from collections.abc import Callable
from dataclasses import fields, is_dataclass
from datetime import datetime
from functools import cache
from types import UnionType
from typing import (
    Any,
    ClassVar,
    Protocol,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
    runtime_checkable,
)

from core.models.choice.choice import Choice
from core.models.choice.choice_option import ChoiceOption
from core.models.choice.choice_request import ChoiceCreateRequest
from core.models.event.event import Event
from core.models.event.event_request import EventCreateRequest
from core.models.exercises.exercise import Exercise
from core.models.exercises.exercise_request import ExerciseCreateRequest
from core.models.exercises.revised_exercise import RevisedExercise
from core.models.exercises.revised_exercise_request import RevisedExerciseCreateRequest
from core.models.forms.form_template import FormTemplate
from core.models.forms.form_template_request import FormTemplateCreateRequest
from core.models.goal.goal import Goal
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
from core.models.templates.event_template import EventTemplate
from core.models.templates.event_template_request import EventTemplateCreateRequest
from core.models.templates.goal_template import GoalTemplate
from core.models.templates.goal_template_request import GoalTemplateCreateRequest
from core.models.templates.habit_template import HabitTemplate
from core.models.templates.habit_template_request import HabitTemplateCreateRequest
from core.models.templates.principle_template import PrincipleTemplate
from core.models.templates.principle_template_request import PrincipleTemplateCreateRequest
from core.models.templates.relative_offset_dto import RelativeOffsetDTO
from core.models.templates.task_template import TaskTemplate
from core.models.templates.task_template_request import TaskTemplateCreateRequest
from core.ports import PydanticModel

# Type variables for generic methods
T = TypeVar("T")
U = TypeVar("U")


@cache
def _tuple_typed_field_names(pure_class: type) -> frozenset[str]:
    """Dataclass fields declared ``tuple[...]``, possibly inside an optional/union.

    Drives the generic list → tuple coercion in ``create_to_pure``: frozen-dataclass
    immutability is shallow, and Pydantic ``model_dump()`` emits lists, so every
    tuple-typed field must be coerced or the "frozen" model carries mutable state.
    """
    hints = get_type_hints(pure_class)
    names: set[str] = set()
    for f in fields(pure_class):
        hint = hints.get(f.name)
        members = get_args(hint) if get_origin(hint) in (Union, UnionType) else (hint,)
        if any(member is tuple or get_origin(member) is tuple for member in members):
            names.add(f.name)
    return frozenset(names)


@runtime_checkable
class CreateRequest(Protocol):
    """Protocol for create request models"""

    @property
    def name(self) -> str | None: ...
    @property
    def title(self) -> str | None: ...


class ConversionServiceV2:
    """
    Unified service for converting between Pure models and Schemas using generic methods.

    Features:
    - Generic conversion methods eliminate repetition
    - Type-safe conversions with generics
    - Single place for all conversions
    - Follows DRY principle
    """

    # ========================================================================
    # GENERIC CONVERSION METHODS
    # ========================================================================

    @classmethod
    def create_to_pure(
        cls, schema: object, pure_class: type[U], uid: str | None = None, **extra_fields: Any
    ) -> U:
        """
        Generic method to convert any CreateRequest to a Pure model.

        Args:
            schema: The create request/schema object,
            pure_class: The target pure model class,
            uid: Optional UID, will generate if not provided
            **extra_fields: Additional fields to add to the pure model

        Returns:
            Instance of the pure model class
        """
        # Generate UID if not provided
        if uid is None:
            uid = str(uuid.uuid4())

        # Get all fields from schema
        schema_data = {}
        if isinstance(schema, PydanticModel):
            # Pydantic model
            schema_data = schema.model_dump(exclude_none=False)
        elif isinstance(schema, dict):
            # Dict
            schema_data = schema
        else:
            # Regular object with __dict__
            schema_data = {k: v for k, v in schema.__dict__.items() if not k.startswith("_")}

        # Add standard fields
        schema_data["uid"] = uid

        # Add timestamps if the pure class expects them
        if is_dataclass(pure_class):
            field_names = {f.name for f in fields(pure_class)}
            if "created" in field_names and "created" not in schema_data:
                schema_data["created"] = datetime.now()
            if "updated" in field_names and "updated" not in schema_data:
                schema_data["updated"] = datetime.now()
            if "created_at" in field_names and "created_at" not in schema_data:
                schema_data["created_at"] = datetime.now()
            if "updated_at" in field_names and "updated_at" not in schema_data:
                schema_data["updated_at"] = datetime.now()

        # Add any extra fields
        schema_data.update(extra_fields)

        # Filter to only fields that exist in the target class, then coerce
        # list values to tuples wherever the target field is tuple-typed
        if is_dataclass(pure_class):
            field_names = {f.name for f in fields(pure_class)}
            schema_data = {k: v for k, v in schema_data.items() if k in field_names}
            for fname in _tuple_typed_field_names(pure_class):
                value = schema_data.get(fname)
                if isinstance(value, list):
                    schema_data[fname] = tuple(value)

        # Create the pure model instance
        return pure_class(**schema_data)

    # ========================================================================
    # SPECIFIC CONVERSIONS
    # ========================================================================

    # --- Task Conversions --
    @classmethod
    def task_create_to_pure(
        cls, schema: TaskCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> Task:
        """Convert TaskCreateRequest to Task using generic method."""
        return cls.create_to_pure(schema, Task, uid, **kwargs)

    # --- Event Conversions --
    @classmethod
    def event_create_to_pure(
        cls, schema: EventCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> Event:
        """Convert EventCreateRequest to Event using generic method."""
        return cls.create_to_pure(schema, Event, uid, **kwargs)

    # --- Habit Conversions --
    @classmethod
    def habit_create_to_pure(
        cls, schema: HabitCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> Habit:
        """Convert HabitCreateRequest to Habit using generic method."""
        # Handle special case for target_days_per_week
        extra_fields = {}
        if schema.target_days_per_week:
            # Note: Habit uses target_days_per_week directly (int, not list of WeekDay)
            extra_fields["target_days_per_week"] = schema.target_days_per_week

        # Merge kwargs (includes user_uid) with extra_fields
        extra_fields.update(kwargs)
        return cls.create_to_pure(schema, Habit, uid, **extra_fields)

    # --- Goal Conversions --
    @classmethod
    def goal_create_to_pure(
        cls, schema: GoalCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> Goal:
        """Convert GoalCreateRequest to Goal using generic method."""
        return cls.create_to_pure(schema, Goal, uid, **kwargs)

    # NOTE: Finance (expense/budget) conversions REMOVED (ADR-052 Phase 5) — native
    # expense/budget module demolished; only the invoice module survives.
    # NOTE: Journal conversions REMOVED (February 2026) - Journal merged into Reports
    # NOTE: Transcription conversions REMOVED (February 2026) - Three-tier models deleted

    # --- Principle Conversions --
    @classmethod
    def principle_create_to_pure(
        cls, schema: PrincipleCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> Principle:
        """Convert PrincipleCreateRequest to Principle entity using generic method.

        List → tuple coercion (key_behaviors, tags) is generic in create_to_pure;
        request-only fields (decision_criteria) are filtered there too.
        """
        return cls.create_to_pure(schema, Principle, uid, **kwargs)

    # --- Choice Conversions --
    @classmethod
    def choice_create_to_pure(
        cls, schema: ChoiceCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> Choice:
        """Convert ChoiceCreateRequest to Choice entity using generic method.

        Straight list[str] fields tuple-ize generically in create_to_pure; only
        the nested option requests need hand-conversion to ChoiceOption values.
        """
        extra_fields: dict[str, Any] = {}
        if schema.options:
            # Convert ChoiceOptionRequest list to ChoiceOption tuple
            # (ChoiceOptionCreateRequest is a different, unused model — not this one)
            options = []
            for i, opt_req in enumerate(schema.options):
                option_uid = f"{uid}_option_{i}" if uid else f"option_{i}"
                option = ChoiceOption(
                    uid=option_uid,
                    title=opt_req.title,
                    description=opt_req.description,
                    feasibility_score=opt_req.feasibility_score,
                    risk_level=opt_req.risk_level,
                    potential_impact=opt_req.potential_impact,
                    resource_requirement=opt_req.resource_requirement,
                    estimated_duration=opt_req.estimated_duration,
                    dependencies=tuple(opt_req.dependencies),
                    tags=tuple(opt_req.tags),
                )
                options.append(option)
            extra_fields["options"] = tuple(options)

        # Merge kwargs (includes user_uid) with extra_fields
        extra_fields.update(kwargs)
        return cls.create_to_pure(schema, Choice, uid, **extra_fields)

    # --- FormTemplate Conversions --
    @classmethod
    def formtemplate_create_to_pure(
        cls, schema: FormTemplateCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> FormTemplate:
        """Convert FormTemplateCreateRequest to FormTemplate using generic method."""
        return cls.create_to_pure(schema, FormTemplate, uid, **kwargs)

    # --- Exercise Conversions --
    @classmethod
    def exercise_create_to_pure(
        cls, schema: ExerciseCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> Exercise:
        """Convert ExerciseCreateRequest to Exercise.

        Handles: name→title, user_uid kwarg→owner_uid, domain str→enum.
        """
        from core.models.enums import Domain
        from core.models.enums.entity_enums import EntityType

        extra_fields: dict[str, Any] = {
            "entity_type": EntityType.EXERCISE,
            "title": schema.name,
            "domain": Domain(schema.domain) if schema.domain else Domain.KNOWLEDGE,
            # Exercise.context_notes is a non-optional tuple — schema None maps to ()
            "context_notes": schema.context_notes or (),
        }
        # Ownership's single source: the authenticated user_uid kwarg (injected
        # by CRUDRouteFactory). The schema deliberately carries no user_uid.
        if "user_uid" in kwargs:
            extra_fields["owner_uid"] = kwargs.pop("user_uid")
        extra_fields.update(kwargs)
        return cls.create_to_pure(schema, Exercise, uid, **extra_fields)

    # --- RevisedExercise Conversions --
    @classmethod
    def revisedexercise_create_to_pure(
        cls, schema: RevisedExerciseCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> RevisedExercise:
        """Convert RevisedExerciseCreateRequest to RevisedExercise using generic method."""
        return cls.create_to_pure(schema, RevisedExercise, uid, **kwargs)

    # --- Group Conversions --
    @classmethod
    def group_create_to_pure(
        cls, schema: GroupCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> Group:
        """Convert GroupCreateRequest to Group using generic method.

        Maps user_uid (from CRUDRouteFactory) to owner_uid (Group field name).
        """
        if "user_uid" in kwargs:
            kwargs["owner_uid"] = kwargs.pop("user_uid")
        return cls.create_to_pure(schema, Group, uid, **kwargs)

    # ========================================================================
    # ACTIVITY TEMPLATE CONVERSIONS (Phase 5)
    # ========================================================================
    # Activity Templates carry RelativeOffsetDTO fields at the API edge that
    # convert to RelativeOffset (frozen value) on the core model. The helper
    # below centralizes that transformation (plus the Phase-7 complex-field
    # deferral); list → tuple coercion is generic in create_to_pure.
    #
    # Templates are PS-owned curriculum (no user_uid). The CRUDRouteFactory
    # passes user_uid via kwargs as a side effect of authentication; the
    # generic create_to_pure filters it out (TaskTemplate has no user_uid
    # field), so no special handling is needed here.

    @classmethod
    def _template_create_to_pure(
        cls,
        schema: object,
        model_class: type[U],
        uid: str | None,
        *,
        offset_fields: tuple[str, ...] = (),
        complex_tuple_fields: tuple[str, ...] = (),
        **kwargs: Any,
    ) -> U:
        """Generic template-schema → frozen-dataclass converter.

        - ``offset_fields``: schema field names typed RelativeOffsetDTO | None;
          convert to RelativeOffset via .to_value() before constructing.
        - ``complex_tuple_fields``: schema list[dict] fields whose model
          counterpart is a tuple of frozen dataclasses (Milestone, ChoiceOption,
          PrincipleExpression). For Phase 5 V1 these default to an empty tuple
          — full nested authoring lands with the UI plan (Phase 7) once
          FormGenerator supports nested dataclasses.
        """
        extra_fields: dict[str, Any] = {}
        for fname in offset_fields:
            value = getattr(schema, fname, None)
            if isinstance(value, RelativeOffsetDTO):
                extra_fields[fname] = value.to_value()
            else:
                extra_fields[fname] = None
        for fname in complex_tuple_fields:
            extra_fields[fname] = ()
        extra_fields.update(kwargs)
        return cls.create_to_pure(schema, model_class, uid, **extra_fields)

    @classmethod
    def tasktemplate_create_to_pure(
        cls, schema: TaskTemplateCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> TaskTemplate:
        """Convert TaskTemplateCreateRequest to TaskTemplate."""
        return cls._template_create_to_pure(
            schema,
            TaskTemplate,
            uid,
            offset_fields=("due_offset", "scheduled_offset", "recurrence_end_offset"),
            **kwargs,
        )

    @classmethod
    def goaltemplate_create_to_pure(
        cls, schema: GoalTemplateCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> GoalTemplate:
        """Convert GoalTemplateCreateRequest to GoalTemplate."""
        return cls._template_create_to_pure(
            schema,
            GoalTemplate,
            uid,
            offset_fields=("start_offset", "target_offset"),
            complex_tuple_fields=("milestones",),
            **kwargs,
        )

    @classmethod
    def habittemplate_create_to_pure(
        cls, schema: HabitTemplateCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> HabitTemplate:
        """Convert HabitTemplateCreateRequest to HabitTemplate."""
        return cls._template_create_to_pure(
            schema,
            HabitTemplate,
            uid,
            offset_fields=("recurrence_end_offset",),
            **kwargs,
        )

    @classmethod
    def eventtemplate_create_to_pure(
        cls, schema: EventTemplateCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> EventTemplate:
        """Convert EventTemplateCreateRequest to EventTemplate."""
        return cls._template_create_to_pure(
            schema,
            EventTemplate,
            uid,
            offset_fields=("event_offset", "recurrence_end_offset"),
            **kwargs,
        )

    @classmethod
    def choicetemplate_create_to_pure(
        cls, schema: ChoiceTemplateCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> ChoiceTemplate:
        """Convert ChoiceTemplateCreateRequest to ChoiceTemplate."""
        return cls._template_create_to_pure(
            schema,
            ChoiceTemplate,
            uid,
            offset_fields=("decision_deadline_offset",),
            complex_tuple_fields=("options",),
            **kwargs,
        )

    @classmethod
    def principletemplate_create_to_pure(
        cls,
        schema: PrincipleTemplateCreateRequest,
        uid: str | None = None,
        **kwargs: Any,
    ) -> PrincipleTemplate:
        """Convert PrincipleTemplateCreateRequest to PrincipleTemplate."""
        return cls._template_create_to_pure(
            schema,
            PrincipleTemplate,
            uid,
            complex_tuple_fields=("expressions",),
            **kwargs,
        )

    # ========================================================================
    # CONVERTER REGISTRY — static mapping from schema type to converter method
    # ========================================================================
    # Replaces getattr-based method discovery (SKUEL011: no hasattr/getattr).
    # MyPy can verify each value is a valid classmethod reference.

    CONVERTER_REGISTRY: ClassVar[dict[type, Callable[..., Any]]] = {}  # populated after class body

    @classmethod
    def get_converter(cls, schema_type: type) -> Callable[..., Any] | None:
        """Look up the converter for a Pydantic CreateRequest type.

        Returns the converter callable, or None if no converter is registered.
        """
        return cls.CONVERTER_REGISTRY.get(schema_type)


# Populated outside the class body so that forward references to classmethods resolve.
# Each key is a Pydantic CreateRequest type; each value is the classmethod that converts it.
ConversionServiceV2.CONVERTER_REGISTRY = {
    TaskCreateRequest: ConversionServiceV2.task_create_to_pure,
    EventCreateRequest: ConversionServiceV2.event_create_to_pure,
    HabitCreateRequest: ConversionServiceV2.habit_create_to_pure,
    GoalCreateRequest: ConversionServiceV2.goal_create_to_pure,
    PrincipleCreateRequest: ConversionServiceV2.principle_create_to_pure,
    ChoiceCreateRequest: ConversionServiceV2.choice_create_to_pure,
    FormTemplateCreateRequest: ConversionServiceV2.formtemplate_create_to_pure,
    ExerciseCreateRequest: ConversionServiceV2.exercise_create_to_pure,
    RevisedExerciseCreateRequest: ConversionServiceV2.revisedexercise_create_to_pure,
    GroupCreateRequest: ConversionServiceV2.group_create_to_pure,
    # Activity Templates (Phase 5 — May 2026)
    TaskTemplateCreateRequest: ConversionServiceV2.tasktemplate_create_to_pure,
    GoalTemplateCreateRequest: ConversionServiceV2.goaltemplate_create_to_pure,
    HabitTemplateCreateRequest: ConversionServiceV2.habittemplate_create_to_pure,
    EventTemplateCreateRequest: ConversionServiceV2.eventtemplate_create_to_pure,
    ChoiceTemplateCreateRequest: ConversionServiceV2.choicetemplate_create_to_pure,
    PrincipleTemplateCreateRequest: ConversionServiceV2.principletemplate_create_to_pure,
}
