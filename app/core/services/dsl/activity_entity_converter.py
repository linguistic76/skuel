"""
Activity Entity Converter
=========================

Converts ParsedActivityLine (with type-safe EntityType/NonKuDomain contexts) into SKUEL domain entities.

This is the bridge from DSL parsing to entity creation:
- ParsedActivityLine → TaskCreateRequest → Task
- ParsedActivityLine → HabitCreateRequest → Habit
- ParsedActivityLine → GoalCreateRequest → Goal
- ParsedActivityLine → EventCreateRequest → Event
- ... and all domains

**Type Safety (v0.4.0):**

1. **EntityType/NonKuDomain contexts**: ParsedActivityLine uses `list[EntityType | NonKuDomain]` for contexts
2. **Protocol-verified conversion**: `convert()` method uses EntityType/NonKuDomain matching
3. **Typed union results**: `ConversionResult` type alias for all possible outputs

The converter's `is_task()`, `is_habit()`, etc. methods use EntityType/NonKuDomain enum comparisons,
providing compile-time verification. Use `activity.context_values` for string serialization.

**Protocol-Based Design:**

The `ActivityEntityConverter.convert()` method uses EntityType/NonKuDomain-based dispatch:

```python
result = converter.convert(activity)
match result:
    case Result(value=TaskCreateRequest() as task):
        await tasks_service.create(task)
    case Result(value=dict() as data):
        # Handle other domain types
```

**Design Principle:**
The converter produces request objects that can be passed to existing
SKUEL services. This maintains separation of concerns:
- DSL Parser: Text → Intermediate Representation (type-safe EntityType/NonKuDomain contexts)
- Entity Converter: IR → Create Requests (protocol-verified)
- Services: Create Requests → Domain Models → Neo4j
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from core.models.enums import (
    EntityStatus,
    Priority,
    RecurrencePattern,
)
from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.models.task.task_request import TaskCreateRequest
from core.services.dsl.activity_dsl_parser import ParsedActivityLine, ParsedJournal
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

# ============================================================================
# PROTOCOL DEFINITIONS
# ============================================================================


@runtime_checkable
class CreateRequestProtocol(Protocol):
    """
    Protocol for entity creation requests.

    All typed CreateRequest classes (TaskCreateRequest, HabitCreateRequest, etc.)
    implicitly satisfy this protocol. This enables type-safe handling of
    conversion results without knowing the concrete type.

    Usage:
        def process_request(request: CreateRequestProtocol) -> None:
            # request is guaranteed to be a valid create request
            pass

    Note:
        This is a structural protocol - classes don't need to explicitly
        inherit from it. Any class with compatible structure satisfies it.
    """

    pass  # Marker protocol for create requests


# Type alias for conversion results
# As we add more typed CreateRequest classes, add them to this union
ConversionResult = TaskCreateRequest | dict[str, Any]
"""
Union type for all possible conversion results.

Currently includes:
- TaskCreateRequest (fully typed)
- dict[str, Any] (for domains without typed request classes yet)

As more domains get typed request classes, they'll be added here:
- HabitCreateRequest
- GoalCreateRequest
- EventCreateRequest
- etc.
"""


@dataclass
class TypedConversionResult:
    """
    Wrapper for conversion results with entity type information.

    Provides both the converted data and the entity type it represents,
    enabling type-safe dispatch in consuming code.

    Attributes:
        entity_type: The EntityType or NonKuDomain this conversion produced
        data: The converted data (CreateRequest or dict)
        source_activity: Reference to the original ParsedActivityLine

    Usage:
        result = converter.convert_typed(activity)
        if result.is_ok:
            typed = result.value
            match typed.entity_type:
                case EntityType.TASK:
                    task_request = typed.data  # Known to be TaskCreateRequest
                case EntityType.HABIT:
                    habit_dict = typed.data    # Known to be dict
    """

    entity_type: EntityType | NonKuDomain
    data: ConversionResult
    source_activity: ParsedActivityLine


logger = get_logger("skuel.dsl.converter")


# ============================================================================
# PRIORITY MAPPING
# ============================================================================


def map_dsl_priority_to_enum(dsl_priority: int | None) -> Priority:
    """
    Map DSL priority (1-5) to SKUEL Priority enum.

    DSL: 1=highest, 5=lowest
    SKUEL: LOW, MEDIUM, HIGH, CRITICAL

    Mapping:
    - 1 → CRITICAL
    - 2 → HIGH
    - 3 → MEDIUM
    - 4, 5 → LOW
    """
    if dsl_priority is None:
        return Priority.MEDIUM

    if dsl_priority == 1:
        return Priority.CRITICAL
    elif dsl_priority == 2:
        return Priority.HIGH
    elif dsl_priority == 3:
        return Priority.MEDIUM
    else:
        return Priority.LOW


# ============================================================================
# RECURRENCE MAPPING
# ============================================================================


def map_repeat_to_recurrence(repeat_pattern: dict[str, Any] | None) -> RecurrencePattern | None:
    """
    Map DSL repeat pattern to SKUEL RecurrencePattern.

    DSL patterns:
    - {"type": "daily"}
    - {"type": "weekly", "days": ["Mon", "Wed"]}
    - {"type": "monthly", "days": [1, 15]}
    - {"type": "interval", "interval": 3, "unit": "days"}

    SKUEL patterns: DAILY, WEEKLY, BIWEEKLY, MONTHLY, QUARTERLY, YEARLY, CUSTOM
    """
    if not repeat_pattern:
        return None

    pattern_type = repeat_pattern.get("type", "")

    if pattern_type == "daily":
        return RecurrencePattern.DAILY

    if pattern_type == "weekly":
        repeat_pattern.get("days", [])
        # If specific days, it's WEEKLY
        # If all weekdays, still WEEKLY
        return RecurrencePattern.WEEKLY

    if pattern_type == "monthly":
        return RecurrencePattern.MONTHLY

    if pattern_type == "interval":
        interval = repeat_pattern.get("interval", 1)
        unit = repeat_pattern.get("unit", "days")

        if unit == "days":
            if interval == 1:
                return RecurrencePattern.DAILY
            elif interval == 7:
                return RecurrencePattern.WEEKLY
            elif interval == 14:
                return RecurrencePattern.BIWEEKLY
        elif unit == "weeks":
            if interval == 1:
                return RecurrencePattern.WEEKLY
            elif interval == 2:
                return RecurrencePattern.BIWEEKLY
        elif unit == "months":
            if interval == 1:
                return RecurrencePattern.MONTHLY
            elif interval == 3:
                return RecurrencePattern.QUARTERLY
            elif interval == 12:
                return RecurrencePattern.YEARLY

        # Default to CUSTOM for complex intervals
        return RecurrencePattern.CUSTOM

    if pattern_type == "custom":
        return RecurrencePattern.CUSTOM

    return None


# ============================================================================
# TASK CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_task_request")
def activity_to_task_request(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to TaskCreateRequest.

    The resulting request can be passed to TasksCoreService.create_task().

    Args:
        activity: Parsed activity line with context containing "task"

    Returns:
        Result containing TaskCreateRequest (as ConversionResult for type compatibility)
    """
    if not activity.is_task():
        return Result.fail(
            Errors.validation(
                message=f"Activity is not a task (missing '{EntityType.TASK.value}' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Extract due date from @when
    due_date: date | None = None
    if activity.when:
        due_date = activity.when.date()

    # Map priority
    priority = map_dsl_priority_to_enum(activity.priority)

    # Map recurrence
    recurrence = map_repeat_to_recurrence(activity.repeat_pattern)

    # Build request
    request = TaskCreateRequest(
        title=activity.description,
        due_date=due_date,
        duration_minutes=activity.duration_minutes or 30,
        priority=priority,
        status=EntityStatus.DRAFT if not activity.is_checked else EntityStatus.COMPLETED,
        recurrence_pattern=recurrence,
        # Knowledge connections
        applies_knowledge_uids=activity.get_linked_knowledge(),
        # Goal connections
        fulfills_goal_uid=activity.get_linked_goals()[0] if activity.get_linked_goals() else None,
        # Tags from energy states
        tags=activity.energy_states if activity.energy_states else [],
    )

    logger.debug(f"Converted activity to TaskCreateRequest: {request.title}")
    return Result.ok(request)


# ============================================================================
# HABIT REQUEST (Placeholder - adapt to your HabitCreateRequest)
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_habit_dict")
def activity_to_habit_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to habit creation dict.

    Since HabitCreateRequest may vary, this returns a dict that can be
    adapted to your specific habit service.

    Args:
        activity: Parsed activity line with context containing "habit"

    Returns:
        Result containing dict for habit creation
    """
    if not activity.is_habit():
        return Result.fail(
            Errors.validation(
                message=f"Activity is not a habit (missing '{EntityType.HABIT.value}' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Map recurrence to frequency string
    frequency = "daily"  # default
    if activity.repeat_pattern:
        pattern_type = activity.repeat_pattern.get("type", "daily")
        if pattern_type == "weekly":
            days = activity.repeat_pattern.get("days", [])
            frequency = f"weekly:{','.join(days)}" if days else "weekly"
        elif pattern_type == "interval":
            interval = activity.repeat_pattern.get("interval", 1)
            unit = activity.repeat_pattern.get("unit", "days")
            frequency = f"every_{interval}_{unit}"
        else:
            frequency = pattern_type

    habit_dict = {
        "title": activity.description,
        "frequency": frequency,
        "duration_minutes": activity.duration_minutes,
        "energy_required": activity.energy_states[0] if activity.energy_states else None,
        "linked_knowledge_uids": activity.get_linked_knowledge(),
        "linked_goal_uids": activity.get_linked_goals(),
        "linked_principle_uids": activity.get_linked_principles(),
        "tags": activity.energy_states,
    }

    logger.debug(f"Converted activity to habit dict: {habit_dict['title']}")
    return Result.ok(habit_dict)


# ============================================================================
# GOAL REQUEST (Placeholder)
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_goal_dict")
def activity_to_goal_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to goal creation dict.

    Args:
        activity: Parsed activity line with context containing "goal"

    Returns:
        Result containing dict for goal creation
    """
    if not activity.is_goal():
        return Result.fail(
            Errors.validation(
                message=f"Activity is not a goal (missing '{EntityType.GOAL.value}' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Extract target date if provided
    target_date: date | None = None
    if activity.when:
        target_date = activity.when.date()

    goal_dict = {
        "title": activity.description,
        "target_date": target_date,
        "priority": activity.priority,
        "linked_knowledge_uids": activity.get_linked_knowledge(),
        "linked_principle_uids": activity.get_linked_principles(),
        "tags": activity.energy_states,
    }

    logger.debug(f"Converted activity to goal dict: {goal_dict['title']}")
    return Result.ok(goal_dict)


# ============================================================================
# EVENT REQUEST (Placeholder)
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_event_dict")
def activity_to_event_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to event creation dict.

    Args:
        activity: Parsed activity line with context containing "event"

    Returns:
        Result containing dict for event creation
    """
    if not activity.is_event():
        return Result.fail(
            Errors.validation(
                message=f"Activity is not an event (missing '{EntityType.EVENT.value}' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Events require a datetime
    event_datetime = activity.when or datetime.now()

    # Calculate end time based on duration
    duration = activity.duration_minutes or 60
    end_datetime = event_datetime + timedelta(minutes=duration)

    event_dict = {
        "title": activity.description,
        "start_datetime": event_datetime,
        "end_datetime": end_datetime,
        "duration_minutes": duration,
        "priority": activity.priority,
        "linked_knowledge_uids": activity.get_linked_knowledge(),
        "linked_goal_uids": activity.get_linked_goals(),
        "recurrence_pattern": map_repeat_to_recurrence(activity.repeat_pattern),
        "tags": activity.energy_states,
    }

    logger.debug(f"Converted activity to event dict: {event_dict['title']}")
    return Result.ok(event_dict)


# ============================================================================
# PRINCIPLE CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_principle_dict")
def activity_to_principle_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to principle creation dict.

    Principles represent values, beliefs, and guiding philosophies that
    inform goals, choices, and habits.

    **DSL Example:**
    ```markdown
    - [ ] Practice non-attachment @context(principle) @energy(spiritual)
          @link(goal:mindfulness/daily-practice)
    ```

    Args:
        activity: Parsed activity line with context containing "principle"

    Returns:
        Result containing dict for principle creation
    """
    if not activity.is_principle():
        return Result.fail(
            Errors.validation(
                message=f"Activity is not a principle (missing '{EntityType.PRINCIPLE.value}' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Extract principle name (first part before any dash or colon)
    description = activity.description
    name = description.split(" - ")[0].split(":")[0].strip()
    if len(name) > 100:
        name = name[:97] + "..."

    # Full statement is the complete description
    statement = description
    if len(statement) > 500:
        statement = statement[:497] + "..."

    # Map energy states to principle category
    # spiritual → SPIRITUAL, focus/creative → INTELLECTUAL, etc.
    category = "personal"  # default
    if activity.energy_states:
        energy_to_category = {
            "spiritual": "spiritual",
            "emotion": "relational",
            "focus": "intellectual",
            "creative": "creative",
            "physical": "health",
            "social": "relational",
        }
        for energy in activity.energy_states:
            if energy.lower() in energy_to_category:
                category = energy_to_category[energy.lower()]
                break

    # Map priority to principle strength
    strength = "moderate"  # default
    if activity.priority:
        priority_to_strength = {
            1: "core",  # Priority 1 = Core principle
            2: "strong",  # Priority 2 = Strong
            3: "moderate",  # Priority 3 = Moderate
            4: "developing",
            5: "exploring",
        }
        strength = priority_to_strength.get(activity.priority, "moderate")

    principle_dict = {
        "name": name,
        "statement": statement,
        "description": description if description != statement else None,
        "category": category,
        "source": "personal",  # DSL entries are personal by default
        "strength": strength,
        "priority": activity.priority or 3,
        "linked_knowledge_uids": activity.get_linked_knowledge(),
        "linked_goal_uids": activity.get_linked_goals(),
        "tags": activity.energy_states if activity.energy_states else [],
        "key_behaviors": [],  # Can be extracted from description if needed
    }

    logger.debug(f"Converted activity to principle dict: {principle_dict['name']}")
    return Result.ok(principle_dict)


# ============================================================================
# CHOICE CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_choice_dict")
def activity_to_choice_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to choice creation dict.

    Choices represent decisions to be made, with options to evaluate
    and criteria to consider.

    **DSL Example:**
    ```markdown
    - [ ] Decide on tech stack for new project @context(choice)
          @when(2025-12-01T17:00) @priority(1)
          @link(goal:skuel/launch, principle:simplicity-first)
    ```

    Args:
        activity: Parsed activity line with context containing "choice"

    Returns:
        Result containing dict for choice creation
    """
    if not activity.is_choice():
        return Result.fail(
            Errors.validation(
                message=f"Activity is not a choice (missing '{EntityType.CHOICE.value}' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Title from description
    title = activity.description
    if len(title) > 200:
        title = title[:197] + "..."

    # Decision deadline from @when
    deadline = activity.when

    # Map priority (1-5) to Priority enum
    priority = map_dsl_priority_to_enum(activity.priority)

    # Infer domain from linked entities or energy states
    domain = "personal"  # default
    if activity.energy_states:
        energy_to_domain = {
            "focus": "tech",
            "creative": "creative",
            "social": "social",
            "physical": "health",
            "spiritual": "personal",
        }
        for energy in activity.energy_states:
            if energy.lower() in energy_to_domain:
                domain = energy_to_domain[energy.lower()]
                break

    # Determine choice type from context
    # If binary keywords detected, mark as binary
    binary_keywords = ["whether", "or not", "should i", "yes or no"]
    choice_type = "multiple"  # default
    if any(kw in activity.description.lower() for kw in binary_keywords):
        choice_type = "binary"

    choice_dict = {
        "title": title,
        "description": activity.description,
        "choice_type": choice_type,
        "priority": priority.value if priority else "medium",
        "domain": domain,
        "decision_deadline": deadline,
        "decision_criteria": [],  # Can be extracted from description
        "constraints": [],
        "stakeholders": [],
        "informed_by_knowledge_uids": activity.get_linked_knowledge(),
        "linked_goal_uids": activity.get_linked_goals(),
        "linked_principle_uids": activity.get_linked_principles(),
        "tags": activity.energy_states if activity.energy_states else [],
    }

    logger.debug(f"Converted activity to choice dict: {choice_dict['title']}")
    return Result.ok(choice_dict)


# ============================================================================
# FINANCE CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_finance_dict")
def activity_to_finance_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to finance/expense creation dict.

    Finance activities track expenses, income, and budget-related items.

    **DSL Example:**
    ```markdown
    - [ ] AWS hosting $150 @context(finance) @when(2025-11-27)
          @link(budget:skuel/infrastructure)
    ```

    **Amount Extraction:**
    The converter attempts to extract amounts from the description using patterns:
    - $50, $100.50 (dollar sign prefix)
    - 50.00 (bare number)
    - 1,500 (with comma separators)

    Args:
        activity: Parsed activity line with context containing "finance"

    Returns:
        Result containing dict for expense creation
    """
    if not activity.is_finance():
        return Result.fail(
            Errors.validation(
                message=f"Activity is not a finance activity (missing '{NonKuDomain.FINANCE.value}' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Extract amount from description
    amount = activity.get_amount()
    if amount is None:
        amount = 0.0  # Default if not parseable

    # Description (remove amount pattern for cleaner description)
    description = re.sub(r"\$[\d,]+\.?\d*", "", activity.description).strip()
    if len(description) > 200:
        description = description[:197] + "..."

    # Expense date from @when (or today)
    expense_date = activity.when.date() if activity.when else date.today()

    # Infer category from energy states or description
    category = "personal"  # default
    category_keywords = {
        "skuel": ["skuel", "development", "ai", "database", "infrastructure"],
        "2222": ["business", "equipment", "software", "contractor"],
        "personal": ["food", "housing", "entertainment", "health"],
    }
    desc_lower = activity.description.lower()
    for cat, keywords in category_keywords.items():
        if any(kw in desc_lower for kw in keywords):
            category = cat
            break

    # Infer subcategory from description keywords
    subcategory = None
    subcategory_keywords = {
        "food": ["food", "groceries", "restaurant", "meal"],
        "transportation": ["uber", "lyft", "gas", "parking", "transit"],
        "subscriptions": ["subscription", "monthly", "netflix", "spotify"],
        "ai_services": ["openai", "anthropic", "ai", "gpt", "claude"],
        "infrastructure": ["aws", "hosting", "server", "cloud"],
        "software": ["software", "license", "app"],
    }
    for subcat, keywords in subcategory_keywords.items():
        if any(kw in desc_lower for kw in keywords):
            subcategory = subcat
            break

    # Determine if recurring from @repeat
    is_recurring = activity.repeat_pattern is not None
    recurrence_pattern = None
    if is_recurring and activity.repeat_pattern:
        pattern_type = activity.repeat_pattern.get("type", "")
        pattern_map = {
            "daily": "daily",
            "weekly": "weekly",
            "monthly": "monthly",
        }
        recurrence_pattern = pattern_map.get(pattern_type)

    finance_dict = {
        "amount": amount,
        "description": description or activity.description,
        "expense_date": expense_date,
        "category": category,
        "subcategory": subcategory,
        "payment_method": "other",  # Default, can be enhanced with DSL tag
        "vendor": None,  # Could be extracted from description
        "currency": "USD",
        "tax_deductible": False,
        "reimbursable": False,
        "is_recurring": is_recurring,
        "recurrence_pattern": recurrence_pattern,
        "tags": activity.energy_states if activity.energy_states else [],
        "notes": None,
        "linked_budget_uid": None,  # Could be from @link(budget:...)
    }

    # Extract budget link if present
    for link in activity.links:
        if link.get("type") == "budget":
            finance_dict["linked_budget_uid"] = link["id"]
            break

    logger.debug(f"Converted activity to finance dict: ${amount} - {description}")
    return Result.ok(finance_dict)


# ============================================================================
# CURRICULUM DOMAIN CONVERTERS (3)
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_ku_dict")
def activity_to_ku_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to KnowledgeUnit creation dict.

    KnowledgeUnits are atomic units of knowledge content - the foundation
    of SKUEL's curriculum architecture.

    **DSL Example:**
    ```markdown
    - [ ] Python async/await patterns @context(ku) @energy(focus)
          @link(ku:python/basics, ku:python/functions)
    ```

    Args:
        activity: Parsed activity line with context containing "ku" or "knowledge"

    Returns:
        Result containing dict for KnowledgeUnit creation
    """
    if not activity.is_lesson():
        return Result.fail(
            Errors.validation(
                message="Activity is not a KU (missing 'ku' or 'knowledge' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Title from description
    title = activity.description
    if len(title) > 200:
        title = title[:197] + "..."

    # Content defaults to description (can be enhanced later)
    content = activity.description

    # Infer domain from energy states or default to TECH
    domain = "TECH"  # default for knowledge
    if activity.energy_states:
        energy_to_domain = {
            "spiritual": "SPIRITUAL",
            "physical": "HEALTH",
            "creative": "CREATIVE",
            "social": "SOCIAL",
            "focus": "TECH",
        }
        for energy in activity.energy_states:
            if energy.lower() in energy_to_domain:
                domain = energy_to_domain[energy.lower()]
                break

    # Complexity from priority (inverted: high priority = basic, low priority = advanced)
    complexity = "medium"
    if activity.priority:
        priority_to_complexity = {
            1: "basic",  # High priority = foundational
            2: "basic",
            3: "medium",
            4: "advanced",
            5: "advanced",
        }
        complexity = priority_to_complexity.get(activity.priority, "medium")

    ku_dict = {
        "title": title,
        "content": content,
        "domain": domain,
        "complexity": complexity,
        "tags": activity.energy_states if activity.energy_states else [],
        "prerequisites": activity.get_linked_knowledge(),
    }

    logger.debug(f"Converted activity to KU dict: {ku_dict['title']}")
    return Result.ok(ku_dict)


@with_error_handling(error_type="system", operation="activity_to_ls_dict")
def activity_to_ls_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to LearningStep creation dict.

    LearningSteps are individual steps in a learning journey,
    connecting knowledge to practice.

    **DSL Example:**
    ```markdown
    - [ ] Complete async programming exercises @context(ls)
          @ku(ku:python/async) @duration(120m) @link(lp:python-mastery)
    ```

    Args:
        activity: Parsed activity line with context containing "ls" or "learningstep"

    Returns:
        Result containing dict for LearningStep creation
    """
    if not activity.is_ls():
        return Result.fail(
            Errors.validation(
                message="Activity is not a LearningStep (missing 'ls' or 'learningstep' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Title from description
    title = activity.description
    if len(title) > 200:
        title = title[:197] + "..."

    # Intent (learning objective) from description
    intent = activity.description

    # Estimated hours from duration
    estimated_hours = 1.0  # default
    if activity.duration_minutes:
        estimated_hours = activity.duration_minutes / 60.0

    # Primary knowledge from @ku tag
    primary_knowledge_uids = []
    if activity.primary_ku:
        primary_knowledge_uids.append(activity.primary_ku)

    # Supporting knowledge from @link(ku:...)
    supporting_knowledge_uids = activity.get_linked_knowledge()

    # Learning path from @link(lp:...)
    learning_path_uid = None
    for link in activity.links:
        if link.get("type") == EntityType.LEARNING_PATH.value:
            learning_path_uid = link["id"]
            break

    ls_dict = {
        "title": title,
        "intent": intent,
        "estimated_hours": estimated_hours,
        "mastery_threshold": 0.7,  # default
        "primary_knowledge_uids": primary_knowledge_uids,
        "supporting_knowledge_uids": supporting_knowledge_uids,
        "learning_path_uid": learning_path_uid,
        "tags": activity.energy_states if activity.energy_states else [],
    }

    logger.debug(f"Converted activity to LS dict: {ls_dict['title']}")
    return Result.ok(ls_dict)


@with_error_handling(error_type="system", operation="activity_to_lp_dict")
def activity_to_lp_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to LearningPath creation dict.

    LearningPaths are complete learning sequences - the journey from
    novice to mastery in a subject area.

    **DSL Example:**
    ```markdown
    - [ ] Master Python async programming @context(lp) @energy(focus)
          @link(goal:become-python-expert)
    ```

    Args:
        activity: Parsed activity line with context containing "lp" or "learningpath"

    Returns:
        Result containing dict for LearningPath creation
    """
    if not activity.is_lp():
        return Result.fail(
            Errors.validation(
                message="Activity is not a LearningPath (missing 'lp' or 'learningpath' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Name from description
    name = activity.description
    if len(name) > 200:
        name = name[:197] + "..."

    # Goal (what learner will achieve) from description
    goal = activity.description

    # Infer domain from energy states
    domain = "TECH"  # default
    if activity.energy_states:
        energy_to_domain = {
            "spiritual": "SPIRITUAL",
            "physical": "HEALTH",
            "creative": "CREATIVE",
            "social": "SOCIAL",
            "focus": "TECH",
        }
        for energy in activity.energy_states:
            if energy.lower() in energy_to_domain:
                domain = energy_to_domain[energy.lower()]
                break

    # Difficulty from priority
    difficulty = "intermediate"
    if activity.priority:
        priority_to_difficulty = {
            1: "beginner",
            2: "intermediate",
            3: "intermediate",
            4: "advanced",
            5: "expert",
        }
        difficulty = priority_to_difficulty.get(activity.priority, "intermediate")

    # Estimated hours from duration (or default to 10 hours for a path)
    estimated_hours = 10.0
    if activity.duration_minutes:
        estimated_hours = activity.duration_minutes / 60.0

    lp_dict = {
        "name": name,
        "goal": goal,
        "domain": domain,
        "difficulty": difficulty,
        "path_type": "structured",  # default
        "estimated_hours": estimated_hours,
        "tags": activity.energy_states if activity.energy_states else [],
        "linked_goal_uids": activity.get_linked_goals(),
    }

    logger.debug(f"Converted activity to LP dict: {lp_dict['name']}")
    return Result.ok(lp_dict)


# ============================================================================
# META DOMAIN CONVERTERS (3)
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_report_dict")
def activity_to_report_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to Report creation dict.

    Reports are file uploads and processing requests - the entry point
    for content into SKUEL.

    **DSL Example:**
    ```markdown
    - [ ] Process my voice memo @context(report) @when(2025-11-27)
          @link(goal:daily-reflection)
    ```

    Args:
        activity: Parsed activity line with context containing "report"

    Returns:
        Result containing dict for Report creation
    """
    if not activity.is_report():
        return Result.fail(
            Errors.validation(
                message="Activity is not a Report (missing 'report' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Infer report type from description keywords
    # NOTE (January 2026): Default changed from "journal" to "transcript"
    # Journal is now a separate domain (JournalsCoreService).
    report_type = "transcript"  # default
    type_keywords = {
        "voice": "transcript",
        "audio": "transcript",
        "memo": "transcript",
        "recording": "transcript",
        "transcript": "transcript",
        "report": "report",
        "image": "image_analysis",
        "video": "video_summary",
    }
    desc_lower = activity.description.lower()
    for keyword, rtype in type_keywords.items():
        if keyword in desc_lower:
            report_type = rtype
            break

    report_dict = {
        "report_type": report_type,
        "processor_type": "automatic",  # LLM processing
        "metadata": {
            "description": activity.description,
            "linked_goals": activity.get_linked_goals(),
            "tags": activity.energy_states if activity.energy_states else [],
        },
    }

    logger.debug(f"Converted activity to Report dict: {report_type}")
    return Result.ok(report_dict)


@with_error_handling(error_type="system", operation="activity_to_analytics_dict")
def activity_to_analytics_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to Analytics request dict.

    Analytics are statistical aggregation requests - analyzing activity
    patterns and progress across domains.

    **DSL Example:**
    ```markdown
    - [ ] Generate weekly habit analytics @context(analytics) @when(2025-11-27)
    ```

    Args:
        activity: Parsed activity line with context containing analytics request

    Returns:
        Result containing dict for Analytics generation request
    """
    # Infer analytics type from description
    analytics_type = "summary"  # default
    type_keywords = {
        "habit": "habits",
        "task": "tasks",
        "goal": "goals",
        "finance": "finance",
        "weekly": "weekly_planning",
        "review": "weekly_review",
        "progress": "goal_progress",
        "life": "life_path",
    }
    desc_lower = activity.description.lower()
    for keyword, atype in type_keywords.items():
        if keyword in desc_lower:
            analytics_type = atype
            break

    # Analytics date from @when
    analytics_date = activity.when.date() if activity.when else date.today()

    analytics_dict = {
        "analytics_type": analytics_type,
        "analytics_date": analytics_date,
        "description": activity.description,
        "metadata": {
            "tags": activity.energy_states if activity.energy_states else [],
        },
    }

    logger.debug(f"Converted activity to Analytics dict: {analytics_type}")
    return Result.ok(analytics_dict)


@with_error_handling(error_type="system", operation="activity_to_calendar_dict")
def activity_to_calendar_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to Calendar item dict.

    Calendar items are scheduled activity views - aggregating tasks, events,
    habits, and goals into a unified time-based view.

    **DSL Example:**
    ```markdown
    - [ ] Block time for deep work @context(calendar) @when(2025-11-28T09:00)
          @duration(180m) @energy(focus)
    ```

    Args:
        activity: Parsed activity line with context containing "calendar"

    Returns:
        Result containing dict for Calendar item creation
    """
    if not activity.is_calendar():
        return Result.fail(
            Errors.validation(
                message="Activity is not a Calendar item (missing 'calendar' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Title from description
    title = activity.description
    if len(title) > 200:
        title = title[:197] + "..."

    # Start time from @when
    start_time = activity.when or datetime.now()

    # Duration
    duration_minutes = activity.duration_minutes or 60

    # Infer calendar item type
    item_type = "time_block"  # default
    type_keywords = {
        "meeting": "event",
        "call": "event",
        "appointment": "event",
        "block": "time_block",
        "focus": "time_block",
        "deep work": "time_block",
    }
    desc_lower = activity.description.lower()
    for keyword, itype in type_keywords.items():
        if keyword in desc_lower:
            item_type = itype
            break

    calendar_dict = {
        "title": title,
        "start_time": start_time,
        "duration_minutes": duration_minutes,
        "item_type": item_type,
        "energy_states": activity.energy_states if activity.energy_states else [],
        "linked_goals": activity.get_linked_goals(),
        "linked_tasks": [
            link["id"] for link in activity.links if link.get("type") == EntityType.TASK.value
        ],
    }

    logger.debug(f"Converted activity to Calendar dict: {calendar_dict['title']}")
    return Result.ok(calendar_dict)


# ============================================================================
# THE DESTINATION (+1)
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_lifepath_dict")
def activity_to_lifepath_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to LifePath alignment dict.

    LifePath represents the ultimate life goal - the destination toward
    which all activities flow. "Everything flows toward the life path."

    **DSL Example:**
    ```markdown
    - [ ] Embody wisdom and service to others @context(lifepath) @priority(1)
          @link(principle:service, principle:wisdom, goal:teaching-mastery)
    ```

    Args:
        activity: Parsed activity line with context containing "lifepath"

    Returns:
        Result containing dict for LifePath alignment/update
    """
    if not activity.is_lifepath():
        return Result.fail(
            Errors.validation(
                message="Activity is not a LifePath item (missing 'lifepath' in @context)",
                field="context",
                value=",".join(activity.context_values),
            )
        )

    # Life path statement
    statement = activity.description
    if len(statement) > 500:
        statement = statement[:497] + "..."

    # Extract linked principles (values guiding the path)
    linked_principles = activity.get_linked_principles()

    # Extract linked goals (milestones on the path)
    linked_goals = activity.get_linked_goals()

    # Extract linked knowledge (wisdom supporting the path)
    linked_knowledge = activity.get_linked_knowledge()

    lifepath_dict: dict[str, Any] = {
        "statement": statement,
        "description": activity.description,
        "linked_principles": linked_principles,
        "linked_goals": linked_goals,
        "linked_knowledge": linked_knowledge,
        "tags": activity.energy_states if activity.energy_states else [],
        "priority": activity.priority or 1,  # LifePath is always high priority
    }

    logger.debug(f"Converted activity to LifePath dict: {lifepath_dict['statement'][:50]}...")
    return Result.ok(lifepath_dict)


# ============================================================================
# BATCH CONVERTER
# ============================================================================


class ActivityEntityConverter:
    """
    Converts parsed activities to SKUEL entity requests.

    Handles batch conversion from ParsedJournal to create requests
    for all 13 domain types.
    """

    def __init__(self) -> None:
        """Initialize converter."""
        self.logger = get_logger("skuel.dsl.converter")

    def convert_journal(self, parsed: ParsedJournal) -> dict[str, list[Any]]:
        """
        Convert all activities in a parsed journal to entity requests.

        Returns dict with keys for ALL 13 SKUEL domains + errors:

        **Activity Domains (7) - What I DO:**
        - "tasks": list of TaskCreateRequest
        - "habits": list of habit dicts
        - "goals": list of goal dicts
        - "events": list of event dicts
        - "principles": list of principle dicts
        - "choices": list of choice dicts
        - "finances": list of finance dicts

        **Curriculum Domains (3) - What I LEARN:**
        - "knowledge_units": list of KU dicts
        - "learning_steps": list of LS dicts
        - "learning_paths": list of LP dicts

        **Meta Domains (3) - How I ORGANIZE:**
        - "reports": list of report dicts
        - "analytics": list of analytics dicts
        - "calendar_items": list of calendar dicts

        **The Destination (+1) - Where I'm GOING:**
        - "lifepath_items": list of lifepath dicts

        **Errors:**
        - "errors": list of conversion error messages
        """
        results: dict[str, list[Any]] = {
            # Activity Domains (7)
            "tasks": [],
            "habits": [],
            "goals": [],
            "events": [],
            "principles": [],
            "choices": [],
            "finances": [],
            # Curriculum Domains (3)
            "knowledge_units": [],
            "learning_steps": [],
            "learning_paths": [],
            # Meta Domains (3)
            "reports": [],
            "analytics": [],
            "calendar_items": [],
            # The Destination (+1)
            "lifepath_items": [],
            # Errors
            "errors": [],
        }

        for activity in parsed.activities:
            # An activity can have multiple contexts (e.g., task + learning)
            # We create entities for each applicable context

            # ================================================================
            # ACTIVITY DOMAINS (7) - What I DO
            # ================================================================

            if activity.is_task():
                result = activity_to_task_request(activity)
                if result.is_ok:
                    results["tasks"].append(result.value)
                else:
                    results["errors"].append(f"Task conversion: {result.error}")

            if activity.is_habit():
                result = activity_to_habit_dict(activity)
                if result.is_ok:
                    results["habits"].append(result.value)
                else:
                    results["errors"].append(f"Habit conversion: {result.error}")

            if activity.is_goal():
                result = activity_to_goal_dict(activity)
                if result.is_ok:
                    results["goals"].append(result.value)
                else:
                    results["errors"].append(f"Goal conversion: {result.error}")

            if activity.is_event():
                result = activity_to_event_dict(activity)
                if result.is_ok:
                    results["events"].append(result.value)
                else:
                    results["errors"].append(f"Event conversion: {result.error}")

            if activity.is_principle():
                result = activity_to_principle_dict(activity)
                if result.is_ok:
                    results["principles"].append(result.value)
                else:
                    results["errors"].append(f"Principle conversion: {result.error}")

            if activity.is_choice():
                result = activity_to_choice_dict(activity)
                if result.is_ok:
                    results["choices"].append(result.value)
                else:
                    results["errors"].append(f"Choice conversion: {result.error}")

            if activity.is_finance():
                result = activity_to_finance_dict(activity)
                if result.is_ok:
                    results["finances"].append(result.value)
                else:
                    results["errors"].append(f"Finance conversion: {result.error}")

            # ================================================================
            # CURRICULUM DOMAINS (3) - What I LEARN
            # ================================================================

            if activity.is_lesson():
                result = activity_to_ku_dict(activity)
                if result.is_ok:
                    results["knowledge_units"].append(result.value)
                else:
                    results["errors"].append(f"KU conversion: {result.error}")

            if activity.is_ls():
                result = activity_to_ls_dict(activity)
                if result.is_ok:
                    results["learning_steps"].append(result.value)
                else:
                    results["errors"].append(f"LS conversion: {result.error}")

            if activity.is_lp():
                result = activity_to_lp_dict(activity)
                if result.is_ok:
                    results["learning_paths"].append(result.value)
                else:
                    results["errors"].append(f"LP conversion: {result.error}")

            # ================================================================
            # META DOMAINS (3) - How I ORGANIZE
            # ================================================================

            if activity.is_report():
                result = activity_to_report_dict(activity)
                if result.is_ok:
                    results["reports"].append(result.value)
                else:
                    results["errors"].append(f"Report conversion: {result.error}")

            if activity.is_calendar():
                result = activity_to_calendar_dict(activity)
                if result.is_ok:
                    results["calendar_items"].append(result.value)
                else:
                    results["errors"].append(f"Calendar conversion: {result.error}")

            # ================================================================
            # THE DESTINATION (+1) - Where I'm GOING
            # ================================================================

            if activity.is_lifepath():
                result = activity_to_lifepath_dict(activity)
                if result.is_ok:
                    results["lifepath_items"].append(result.value)
                else:
                    results["errors"].append(f"LifePath conversion: {result.error}")

        # Log conversion summary
        self.logger.info(
            f"Converted journal: "
            # Activity domains
            f"{len(results['tasks'])} tasks, "
            f"{len(results['habits'])} habits, "
            f"{len(results['goals'])} goals, "
            f"{len(results['events'])} events, "
            f"{len(results['principles'])} principles, "
            f"{len(results['choices'])} choices, "
            f"{len(results['finances'])} finances, "
            # Curriculum domains
            f"{len(results['knowledge_units'])} KUs, "
            f"{len(results['learning_steps'])} LSs, "
            f"{len(results['learning_paths'])} LPs, "
            # Meta domains
            f"{len(results['reports'])} reports, "
            f"{len(results['analytics'])} analytics, "
            f"{len(results['calendar_items'])} calendar items, "
            # Destination
            f"{len(results['lifepath_items'])} lifepath items, "
            # Errors
            f"{len(results['errors'])} errors"
        )

        return results

    # ========================================================================
    # PROTOCOL-VERIFIED CONVERSION (Type-Safe EntityType/NonKuDomain Dispatch)
    # ========================================================================

    def convert(
        self,
        activity: ParsedActivityLine,
        entity_type: EntityType | NonKuDomain | None = None,
    ) -> Result[ConversionResult]:
        """
        Convert a ParsedActivityLine to a create request using EntityType/NonKuDomain dispatch.

        This method provides protocol-verified, type-safe conversion using
        EntityType/NonKuDomain-based pattern matching. It returns typed results that
        can be further matched by the caller.

        Args:
            activity: The parsed activity line to convert
            entity_type: Specific EntityType or NonKuDomain to convert to (defaults to primary_context)

        Returns:
            Result containing either:
            - TaskCreateRequest (for EntityType.TASK)
            - dict[str, Any] (for other entity types, pending typed request classes)

        Example:
            ```python
            converter = ActivityEntityConverter()
            result = converter.convert(activity)

            if result.is_ok:
                match result.value:
                    case TaskCreateRequest() as task:
                        # Handle typed TaskCreateRequest
                        await tasks_service.create(task)
                    case dict() as data:
                        # Handle dict for other domains
                        pass
            ```

        Type Safety:
            The EntityType/NonKuDomain enums ensure only valid entity types are handled.
            MyPy can verify exhaustiveness when all domains have typed requests.
        """
        # Determine entity type to convert to
        target_type = entity_type or activity.primary_context

        if target_type is None:
            return Result.fail(
                Errors.validation(
                    message="Activity has no context to convert",
                    field="contexts",
                    value="[]",
                )
            )

        # EntityType/NonKuDomain-based dispatch
        match target_type:
            # ================================================================
            # ACTIVITY DOMAINS (6) - EntityType
            # ================================================================
            case EntityType.TASK:
                return activity_to_task_request(activity)

            case EntityType.HABIT:
                return activity_to_habit_dict(activity)

            case EntityType.GOAL:
                return activity_to_goal_dict(activity)

            case EntityType.EVENT:
                return activity_to_event_dict(activity)

            case EntityType.PRINCIPLE:
                return activity_to_principle_dict(activity)

            case EntityType.CHOICE:
                return activity_to_choice_dict(activity)

            # ================================================================
            # NON-KU DOMAINS - NonKuDomain
            # ================================================================
            case NonKuDomain.FINANCE:
                return activity_to_finance_dict(activity)

            case NonKuDomain.CALENDAR:
                return activity_to_calendar_dict(activity)

            case NonKuDomain.LEARNING:
                # LEARNING is a general learning context - a modifier, not a primary entity type
                # When used alone, it indicates a learning-focused activity without specific KU creation
                # Return a dict with learning metadata (can be used to enhance other entities)
                return Result.ok(
                    {
                        "type": "learning_activity",
                        "description": activity.description,
                        "primary_ku": activity.primary_ku,
                        "linked_knowledge": activity.get_linked_knowledge(),
                        "duration_minutes": activity.duration_minutes,
                        "tags": activity.energy_states if activity.energy_states else [],
                    }
                )

            # ================================================================
            # CURRICULUM DOMAINS (3) - EntityType
            # ================================================================
            case EntityType.LESSON:
                return activity_to_ku_dict(activity)

            case EntityType.LEARNING_STEP:
                return activity_to_ls_dict(activity)

            case EntityType.LEARNING_PATH:
                return activity_to_lp_dict(activity)

            # ================================================================
            # CONTENT PROCESSING - EntityType
            # ================================================================
            case EntityType.EXERCISE_SUBMISSION:
                return activity_to_report_dict(activity)

            # ================================================================
            # THE DESTINATION (+1) - EntityType
            # ================================================================
            case EntityType.LIFE_PATH:
                return activity_to_lifepath_dict(activity)

            # ================================================================
            # FALLBACK (should not reach due to EntityType/NonKuDomain exhaustiveness)
            # ================================================================
            case _:
                return Result.fail(
                    Errors.validation(
                        message=f"Unsupported entity type for conversion: {target_type}",
                        field="entity_type",
                        value=target_type.value,
                    )
                )

    def convert_typed(
        self,
        activity: ParsedActivityLine,
        entity_type: EntityType | NonKuDomain | None = None,
    ) -> Result[TypedConversionResult]:
        """
        Convert with full type information preserved.

        Returns a TypedConversionResult that includes the EntityType or NonKuDomain,
        enabling type-safe pattern matching on both the type and the data.

        Args:
            activity: The parsed activity line to convert
            entity_type: Specific EntityType or NonKuDomain to convert to (defaults to primary_context)

        Returns:
            Result containing TypedConversionResult with:
            - entity_type: The EntityType or NonKuDomain that was converted
            - data: The conversion result (CreateRequest or dict)
            - source_activity: Reference to original activity

        Example:
            ```python
            result = converter.convert_typed(activity)
            if result.is_ok:
                typed = result.value

                # Pattern match on entity type
                match typed.entity_type:
                    case EntityType.TASK:
                        task = typed.data  # Known context: TaskCreateRequest
                        print(f"Task: {task.title}")
                    case EntityType.HABIT:
                        habit = typed.data  # Known context: dict
                        print(f"Habit: {habit['name']}")
                    case _:
                        # Handle other types
                        pass
            ```
        """
        target_type = entity_type or activity.primary_context

        if target_type is None:
            return Result.fail(
                Errors.validation(
                    message="Activity has no context to convert",
                    field="contexts",
                    value="[]",
                )
            )

        # Convert using standard method
        conversion_result = self.convert(activity, target_type)

        if conversion_result.is_error:
            return Result.fail(conversion_result.expect_error())

        # Wrap in TypedConversionResult
        typed_result = TypedConversionResult(
            entity_type=target_type,
            data=conversion_result.value,
            source_activity=activity,
        )

        return Result.ok(typed_result)

    def convert_all_contexts(
        self,
        activity: ParsedActivityLine,
    ) -> list[Result[TypedConversionResult]]:
        """
        Convert an activity for ALL its contexts (multi-context support).

        An activity can have multiple contexts (e.g., `@context(task,learning)`).
        This method converts to each context type and returns all results.

        Args:
            activity: The parsed activity line (may have multiple contexts)

        Returns:
            List of Results, one per context in the activity

        Example:
            ```python
            # Activity with @context(task,learning)
            results = converter.convert_all_contexts(activity)

            for result in results:
                if result.is_ok:
                    typed = result.value
                    print(f"Converted to {typed.entity_type.value}")
            ```
        """
        results: list[Result[TypedConversionResult]] = []

        for context in activity.contexts:
            result = self.convert_typed(activity, context)
            results.append(result)

        return results
