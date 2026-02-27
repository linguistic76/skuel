"""
Unified Conversion Service V2
==============================

Refactored conversion service using generic methods to eliminate repetition.
Follows DRY principle with type-safe generic conversions.

Clean implementation with no backwards compatibility.
"""

__version__ = "2.0"

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any, Protocol, TypeVar, runtime_checkable

from core.models.activity_requests import (
    ChoiceCreateRequest,
    PrincipleCreateRequest,
)
from core.models.choice.choice import Choice
from core.models.choice.choice_option import ChoiceOption
from core.models.curriculum.curriculum_requests import CurriculumCreateRequest as KuCreateRequest
from core.models.entity import Entity
from core.models.entity_requests import EntityUpdateRequest

# Import domain models (Tier 3 - Core)
from core.models.event.event_request import EventCreateRequest, EventUpdateRequest
from core.models.finance.finance_pure import BudgetPure, ExpensePure
from core.models.finance.finance_request import (
    BudgetCreateRequest,
    BudgetUpdateRequest,
    ExpenseCreateRequest,
    ExpenseUpdateRequest,
)
from core.models.goal.goal_request import GoalCreateRequest, GoalUpdateRequest
from core.models.habit.habit import Habit as Habit
from core.models.habit.habit_request import HabitCreateRequest, HabitUpdateRequest
from core.models.principle.principle import Principle
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest
from core.ports import HasUpdated, HasUpdatedAt, PydanticModel

# Create aliases for Pure models (backward compatibility)
Task = Entity  # Alias for Entity base type (domain-first model)
TaskPure = Task
EventPure = Entity
HabitPure = Habit
GoalPure = Entity  # Alias for Entity base type (domain-first model)
KuPure = Entity  # Knowledge Unit (Entity base type)

# Type variables for generic methods
T = TypeVar("T")
S = TypeVar("S")
U = TypeVar("U")
V = TypeVar("V")


@runtime_checkable
class HasModelCopy(Protocol):
    """Protocol for models with model_copy method (Pydantic models)"""

    def model_copy(self, update: dict[str, Any]) -> Any: ...


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


    Source Tag: "conversion_service_explicit"
    - Format: "conversion_service_explicit" for user-created relationships
    - Format: "conversion_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from conversion metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (uses pure Cypher)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

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
    def update_to_pure(cls, existing: T, schema: U, **extra_updates: Any) -> T:
        """
        Generic method to apply update schema to existing pure model.

        Args:
            existing: The existing pure model,
            schema: The update schema with new values
            **extra_updates: Additional updates to apply

        Returns:
            Updated copy of the pure model
        """
        updates = {}

        # Extract updates from schema
        if isinstance(schema, PydanticModel):
            # Pydantic model - get non-None values
            schema_dict = schema.model_dump(exclude_none=True)
            updates.update(schema_dict)
        elif isinstance(schema, dict):
            # Dict
            updates.update({k: v for k, v in schema.items() if v is not None})
        else:
            # Regular object - use dict comprehension
            updates.update(
                {
                    key: value
                    for key, value in schema.__dict__.items()
                    if not key.startswith("_") and value is not None
                }
            )

        # Add standard update fields
        if isinstance(existing, HasUpdated):
            updates["updated"] = datetime.now()
        elif isinstance(existing, HasUpdatedAt):
            updates["updated_at"] = datetime.now()

        # Add extra updates
        updates.update(extra_updates)

        # Apply updates based on model type
        if isinstance(existing, HasModelCopy):
            # Pydantic model with model_copy
            return existing.model_copy(update=updates)
        elif is_dataclass(existing):
            # Dataclass - create new instance with updates
            from dataclasses import replace

            return replace(existing, **updates)
        else:
            # Fallback - try to create new instance
            existing_data = existing.__dict__.copy()
            existing_data.update(updates)
            return type(existing)(**existing_data)

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
    ) -> TaskPure:
        """Convert TaskCreateRequest to TaskPure using generic method."""
        return cls.create_to_pure(schema, TaskPure, uid, **kwargs)

    @classmethod
    def task_update_to_pure(cls, existing: TaskPure, schema: TaskUpdateRequest) -> TaskPure:
        """Apply TaskUpdateRequest to existing TaskPure using generic method."""
        return cls.update_to_pure(existing, schema)

    # --- Event Conversions --
    @classmethod
    def event_create_to_pure(
        cls, schema: EventCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> EventPure:
        """Convert EventCreateRequest to EventPure using generic method."""
        return cls.create_to_pure(schema, EventPure, uid, **kwargs)

    @classmethod
    def event_update_to_pure(cls, existing: EventPure, schema: EventUpdateRequest) -> EventPure:
        """Apply EventUpdateRequest to existing EventPure using generic method."""
        return cls.update_to_pure(existing, schema)

    # --- Habit Conversions --
    @classmethod
    def habit_create_to_pure(
        cls, schema: HabitCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> HabitPure:
        """Convert HabitCreateRequest to HabitPure using generic method."""
        # Handle special case for target_days_per_week
        extra_fields = {}
        if schema.target_days_per_week:
            # Note: HabitPure uses target_days_per_week directly (int, not list of WeekDay)
            extra_fields["target_days_per_week"] = schema.target_days_per_week

        # Merge kwargs (includes user_uid) with extra_fields
        extra_fields.update(kwargs)
        return cls.create_to_pure(schema, HabitPure, uid, **extra_fields)

    @classmethod
    def habit_update_to_pure(cls, existing: HabitPure, schema: HabitUpdateRequest) -> HabitPure:
        """Apply HabitUpdateRequest to existing HabitPure using generic method."""
        # Handle special case for target_days_per_week
        extra_updates = {}
        if schema.target_days_per_week is not None:
            extra_updates["target_days_per_week"] = schema.target_days_per_week

        return cls.update_to_pure(existing, schema, **extra_updates)

    # --- Goal Conversions --
    @classmethod
    def goal_create_to_pure(
        cls, schema: GoalCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> GoalPure:
        """Convert GoalCreateRequest to GoalPure using generic method."""
        return cls.create_to_pure(schema, GoalPure, uid, **kwargs)

    @classmethod
    def goal_update_to_pure(cls, existing: GoalPure, schema: GoalUpdateRequest) -> GoalPure:
        """Apply GoalUpdateRequest to existing GoalPure using generic method."""
        return cls.update_to_pure(existing, schema)

    @classmethod
    def goal_update_to_dto(cls, schema: GoalUpdateRequest) -> dict:
        """Convert GoalUpdateRequest to dict for updating DTO."""
        return schema.model_dump(exclude_none=True)

    # --- Knowledge Unit (Ku) Conversions --
    @classmethod
    def ku_create_to_pure(
        cls, schema: KuCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> KuPure:
        """Convert CurriculumCreateRequest to Curriculum entity using generic method."""
        return cls.create_to_pure(schema, KuPure, uid, **kwargs)

    @classmethod
    def ku_update_to_pure(cls, existing: KuPure, schema: EntityUpdateRequest) -> KuPure:
        """Apply EntityUpdateRequest to existing Curriculum entity using generic method."""
        return cls.update_to_pure(existing, schema)

    # --- Finance Conversions (three-tier migrated) --
    @classmethod
    def expense_create_to_pure(
        cls, schema: ExpenseCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> ExpensePure:
        """Convert ExpenseCreateRequest to ExpensePure using generic method."""
        return cls.create_to_pure(schema, ExpensePure, uid, **kwargs)

    @classmethod
    def expense_update_to_pure(
        cls, existing: ExpensePure, schema: ExpenseUpdateRequest
    ) -> ExpensePure:
        """Apply ExpenseUpdateRequest to existing ExpensePure using generic method."""
        return cls.update_to_pure(existing, schema)

    @classmethod
    def budget_create_to_pure(
        cls, schema: BudgetCreateRequest, uid: str | None = None, **kwargs: Any
    ) -> BudgetPure:
        """Convert BudgetCreateRequest to BudgetPure using generic method."""
        return cls.create_to_pure(schema, BudgetPure, uid, **kwargs)

    @classmethod
    def budget_update_to_pure(cls, existing: BudgetPure, schema: BudgetUpdateRequest) -> BudgetPure:
        """Apply BudgetUpdateRequest to existing BudgetPure using generic method."""
        return cls.update_to_pure(existing, schema)

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

    @classmethod
    def principle_update_to_pure(cls, existing: Principle, schema: EntityUpdateRequest) -> Principle:
        """Apply EntityUpdateRequest to existing Principle entity using generic method."""
        # Convert list fields to tuples for immutable model
        extra_updates = {}
        if schema.key_behaviors is not None:
            extra_updates["key_behaviors"] = tuple(schema.key_behaviors)
        if schema.decision_criteria is not None:
            extra_updates["decision_criteria"] = tuple(schema.decision_criteria)
        if schema.tags is not None:
            extra_updates["tags"] = tuple(schema.tags)

        return cls.update_to_pure(existing, schema, **extra_updates)

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

    @classmethod
    def choice_update_to_pure(cls, existing: Choice, schema: EntityUpdateRequest) -> Choice:
        """Apply ChoiceUpdateRequest to existing Choice using generic method."""
        # Convert list fields to tuples for immutable model
        extra_updates = {}
        if schema.decision_criteria is not None:
            extra_updates["decision_criteria"] = tuple(schema.decision_criteria)
        if schema.constraints is not None:
            extra_updates["constraints"] = tuple(schema.constraints)
        if schema.stakeholders is not None:
            extra_updates["stakeholders"] = tuple(schema.stakeholders)

        return cls.update_to_pure(existing, schema, **extra_updates)

    # ========================================================================
    # VIEW CONVERSIONS (Keep specific for now due to view complexity)
    # ========================================================================

    # NOTE: View conversions removed - three-tier architecture complete.
    # If views are needed, they should be handled by the domain-specific converters.
    # This forces usage of the proper three-tier pattern instead of legacy approaches.

    # ========================================================================
    # BACKWARD COMPATIBILITY ALIASES
    # ========================================================================

    # Create aliases for backward compatibility
    def task_update_to_dict(self, schema):
        return self.pure_to_dict(schema, exclude_none=True)

    def event_update_to_dict(self, schema):
        return self.pure_to_dict(schema, exclude_none=True)

    def habit_update_to_dict(self, schema):
        return self.pure_to_dict(schema, exclude_none=True)

    def goal_update_to_dict(self, schema):
        return self.pure_to_dict(schema, exclude_none=True)

    def expense_update_to_dict(self, schema):
        return self.pure_to_dict(schema, exclude_none=True)

    def budget_update_to_dict(self, schema):
        return self.pure_to_dict(schema, exclude_none=True)

    def principle_update_to_dict(self, schema):
        return self.pure_to_dict(schema, exclude_none=True)

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


# For backward compatibility, keep the old class name as an alias
ConversionService = ConversionServiceV2
