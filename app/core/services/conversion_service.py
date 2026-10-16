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
from core.utils.type_converters import PydanticModel

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
        """Convert GoalCreateRequest to Goal using generic method.

        ``parent_goal_uid`` needs a hand-mapping: the request and the model spell the
        same hierarchy link differently (``Goal.fulfills_goal_uid``), and
        ``create_to_pure`` filters by exact field name, so the generic pass dropped the
        parent on every goal created through this converter.
        """
        # boundary: dataclass-kwargs — splatted into Goal(**...), so the values are
        # genuinely heterogeneous (str uid here, plus whatever the caller passes in
        # kwargs: UserUID, EntityStatus, ...). Narrowing would have to enumerate
        # every Goal field type.
        extra_fields: dict[str, Any] = {}
        if schema.parent_goal_uid:
            extra_fields["fulfills_goal_uid"] = schema.parent_goal_uid

        # Merge kwargs (includes user_uid) with extra_fields
        extra_fields.update(kwargs)
        return cls.create_to_pure(schema, Goal, uid, **extra_fields)

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

        Nothing needs hand-mapping: every request field the generic pass keeps is a real
        ``Principle`` column (``why_important`` included, since it stopped being spliced
        into ``description``), list → tuple coercion (key_behaviors, tags) is generic in
        create_to_pure, and request-only fields (decision_criteria) are filtered there
        too. Registered in ``CONVERTER_REGISTRY``, so the generated CRUD route reaches
        Principle through this method like every other domain.
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
    GroupCreateRequest: ConversionServiceV2.group_create_to_pure,
}
