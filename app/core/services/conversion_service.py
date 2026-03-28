"""
Unified Conversion Service V2
==============================

Refactored conversion service using generic methods to eliminate repetition.
Follows DRY principle with type-safe generic conversions.

Clean implementation with no backwards compatibility.
"""

__version__ = "2.0"

import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any, ClassVar, Protocol, TypeVar, runtime_checkable

from core.models.choice.choice import Choice
from core.models.choice.choice_option import ChoiceOption
from core.models.choice.choice_request import ChoiceCreateRequest
from core.models.event.event import Event
from core.models.event.event_request import EventCreateRequest
from core.models.exercises.revised_exercise import RevisedExercise
from core.models.exercises.revised_exercise_request import RevisedExerciseCreateRequest
from core.models.finance.finance_pure import BudgetPure, ExpensePure
from core.models.finance.finance_request import (
    BudgetCreateRequest,
    ExpenseCreateRequest,
)
from core.models.forms.form_template import FormTemplate
from core.models.forms.form_template_request import FormTemplateCreateRequest
from core.models.goal.goal import Goal
from core.models.goal.goal_request import GoalCreateRequest
from core.models.group.group import Group
from core.models.group.group_request import GroupCreateRequest
from core.models.habit.habit import Habit
from core.models.habit.habit_request import HabitCreateRequest
from core.models.ku.ku import Ku
from core.models.lesson.lesson_request import LessonCreateRequest
from core.models.principle.principle import Principle
from core.models.principle.principle_request import PrincipleCreateRequest
from core.models.task.task import Task
from core.models.task.task_request import TaskCreateRequest
from core.ports import PydanticModel

# Type variables for generic methods
T = TypeVar("T")
U = TypeVar("U")


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
        cls, schema: T, pure_class: type[U], uid: str | None = None, **extra_fields: Any
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

        # Filter to only fields that exist in the target class
        if is_dataclass(pure_class):
            field_names = {f.name for f in fields(pure_class)}
            schema_data = {k: v for k, v in schema_data.items() if k in field_names}

        # Create the pure model instance
        return pure_class(**schema_data)

    @classmethod
    def pure_to_dict(
        cls, pure_model: T, exclude_none: bool = True, exclude_fields: set[str] | None = None
    ) -> dict[str, Any]:
        """
        Generic method to convert pure model to dictionary.

        Args:
            pure_model: The pure model to convert,
            exclude_none: Whether to exclude None values,
            exclude_fields: Set of field names to exclude

        Returns:
            Dictionary representation
        """
        if exclude_fields is None:
            exclude_fields = set()

        result = {}

        if isinstance(pure_model, PydanticModel):
            # Pydantic model
            result = pure_model.model_dump(exclude_none=exclude_none)
        elif is_dataclass(pure_model):
            # Dataclass
            from dataclasses import asdict

            result = asdict(pure_model)
        elif isinstance(pure_model, dict):
            # Already a dict
            result = pure_model
        else:
            # Regular object with __dict__
            result = {k: v for k, v in pure_model.__dict__.items() if not k.startswith("_")}

        # Apply exclusions
        if exclude_none:
            result = {k: v for k, v in result.items() if v is not None}

        # Exclude specified fields
        for field in exclude_fields:
            result.pop(field, None)

        return result

    @classmethod
    def dict_to_pure(cls, data: dict[str, Any], pure_class: type[T]) -> T:
        """
        Generic method to create pure model from dictionary.

        Args:
            data: Dictionary with model data,
            pure_class: The pure model class to instantiate

        Returns:
            Instance of the pure model
        """
        # Filter to only fields that exist in the target class
        if is_dataclass(pure_class):
            field_names = {f.name for f in fields(pure_class)}
            data = {k: v for k, v in data.items() if k in field_names}

        return pure_class(**data)

    # ========================================================================
    # SPECIFIC CONVERSIONS (Using Generic Methods)
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

    # --- Knowledge Unit (Ku) Conversions --
    @classmethod
    def ku_create_to_pure(
        cls, schema: LessonCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> Ku:
        """Convert CurriculumCreateRequest to Curriculum entity using generic method."""
        return cls.create_to_pure(schema, Ku, uid, **kwargs)

    # --- Finance Conversions (three-tier migrated) --
    @classmethod
    def expense_create_to_pure(
        cls, schema: ExpenseCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> ExpensePure:
        """Convert ExpenseCreateRequest to ExpensePure using generic method."""
        return cls.create_to_pure(schema, ExpensePure, uid, **kwargs)

    @classmethod
    def budget_create_to_pure(
        cls, schema: BudgetCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> BudgetPure:
        """Convert BudgetCreateRequest to BudgetPure using generic method."""
        return cls.create_to_pure(schema, BudgetPure, uid, **kwargs)

    # NOTE: Journal conversions REMOVED (February 2026) - Journal merged into Reports
    # NOTE: Transcription conversions REMOVED (February 2026) - Three-tier models deleted

    # --- Principle Conversions --
    @classmethod
    def principle_create_to_pure(
        cls, schema: PrincipleCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> Principle:
        """Convert PrincipleCreateRequest to Principle entity using generic method."""
        # Principle uses tuples for immutability, need to convert lists
        extra_fields = {}
        if schema.key_behaviors:
            extra_fields["key_behaviors"] = tuple(schema.key_behaviors)
        if schema.decision_criteria:
            extra_fields["decision_criteria"] = tuple(schema.decision_criteria)
        if schema.tags:
            extra_fields["tags"] = tuple(schema.tags)

        # Merge kwargs (includes user_uid) with extra_fields
        extra_fields.update(kwargs)
        return cls.create_to_pure(schema, Principle, uid, **extra_fields)

    # --- Choice Conversions --
    @classmethod
    def choice_create_to_pure(
        cls, schema: ChoiceCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> Choice:
        """Convert ChoiceCreateRequest to Choice entity using generic method."""
        # Choice uses tuples for immutability, need to convert lists
        extra_fields = {}
        if schema.decision_criteria:
            extra_fields["decision_criteria"] = tuple(schema.decision_criteria)
        if schema.constraints:
            extra_fields["constraints"] = tuple(schema.constraints)
        if schema.stakeholders:
            extra_fields["stakeholders"] = tuple(schema.stakeholders)
        if schema.options:
            # Convert ChoiceOptionCreateRequest list to ChoiceOption tuple
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
    # PRINCIPLE EXTENDED FEATURES (Conversion layer complete - service stubs remain)
    # ========================================================================

    @classmethod
    def principle_expression_to_dto(
        cls, expression_uid: str, principle_uid: str, data: Any
    ) -> dict[str, Any]:
        """
        Convert PrincipleExpressionRequest to DTO dict.

        Args:
            expression_uid: Generated UID for the expression
            principle_uid: Parent principle UID
            data: PrincipleExpressionRequest with context, behavior, example

        Returns:
            Dict representation for service layer consumption
        """
        # Extract fields from Pydantic model
        if isinstance(data, PydanticModel):
            data_dict = data.model_dump(exclude_none=False)
        elif isinstance(data, Mapping) or (
            isinstance(data, Iterable) and not isinstance(data, str | bytes)
        ):
            data_dict = dict(data)
        else:
            data_dict = {}

        return {
            "uid": expression_uid,
            "principle_uid": principle_uid,
            "context": data_dict.get("context", ""),
            "behavior": data_dict.get("behavior", ""),
            "example": data_dict.get("example"),
            "created_at": datetime.now(),
        }

    @classmethod
    def alignment_assessment_to_dto(
        cls, assessment_uid: str, principle_uid: str, data: Any
    ) -> dict[str, Any]:
        """
        Convert AlignmentAssessmentRequest to DTO dict.

        Args:
            assessment_uid: Generated UID for the assessment
            principle_uid: Parent principle UID
            data: AlignmentAssessmentRequest with alignment_level, evidence, reflection

        Returns:
            Dict representation for service layer consumption
        """
        from core.models.enums.principle_enums import AlignmentLevel
        from core.ports.base_protocols import EnumLike

        # Extract fields from Pydantic model
        if isinstance(data, PydanticModel):
            data_dict = data.model_dump(exclude_none=False)
        elif isinstance(data, Mapping) or (
            isinstance(data, Iterable) and not isinstance(data, str | bytes)
        ):
            data_dict = dict(data)
        else:
            data_dict = {}

        # Handle enum value extraction
        alignment_level = data_dict.get("alignment_level", AlignmentLevel.PARTIAL)
        if isinstance(alignment_level, EnumLike):
            alignment_level = alignment_level.value

        return {
            "uid": assessment_uid,
            "principle_uid": principle_uid,
            "alignment_level": alignment_level,
            "evidence": data_dict.get("evidence", ""),
            "reflection": data_dict.get("reflection"),
            "assessed_date": data_dict.get("assessed_date"),
            "created_at": datetime.now(),
        }

    @classmethod
    def principle_link_to_dto(cls, link_uid: str, principle_uid: str, data: Any) -> dict[str, Any]:
        """
        Convert PrincipleLinkRequest to DTO dict.

        Args:
            link_uid: Generated UID for the link
            principle_uid: Source principle UID
            data: PrincipleLinkRequest with link_type, uid, bidirectional

        Returns:
            Dict representation for service layer consumption
        """
        # Extract fields from Pydantic model
        if isinstance(data, PydanticModel):
            data_dict = data.model_dump(exclude_none=False)
        elif isinstance(data, Mapping) or (
            isinstance(data, Iterable) and not isinstance(data, str | bytes)
        ):
            data_dict = dict(data)
        else:
            data_dict = {}

        return {
            "uid": link_uid,
            "principle_uid": principle_uid,
            "link_type": data_dict.get("link_type", ""),
            "target_uid": data_dict.get("uid", ""),  # 'uid' in request is the target
            "bidirectional": data_dict.get("bidirectional", False),
            "created_at": datetime.now(),
        }

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
    ExpenseCreateRequest: ConversionServiceV2.expense_create_to_pure,
    BudgetCreateRequest: ConversionServiceV2.budget_create_to_pure,
    PrincipleCreateRequest: ConversionServiceV2.principle_create_to_pure,
    ChoiceCreateRequest: ConversionServiceV2.choice_create_to_pure,
    FormTemplateCreateRequest: ConversionServiceV2.formtemplate_create_to_pure,
    RevisedExerciseCreateRequest: ConversionServiceV2.revisedexercise_create_to_pure,
    GroupCreateRequest: ConversionServiceV2.group_create_to_pure,
}
