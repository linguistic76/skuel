"""
Specialized Domain Converters
=============================

Converter functions for non-Activity domains:
- Finance (NonKuDomain)
- Curriculum: KU, PathStep, LearningPath
- Meta: Report, Analytics, Calendar
- LifePath (the destination)

Each function converts a ParsedActivityLine to a domain-specific dict.
"""

import re
from datetime import date, datetime
from typing import Any

from core.models.enums.entity_enums import EntityType, NonKuDomain
from core.services.dsl.activity_dsl_parser import ParsedActivityLine
from core.services.dsl.dsl_mappings import ConversionResult
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.dsl.converter")


# ============================================================================
# FINANCE CONVERTER
# ============================================================================


@with_error_handling(error_type="system", operation="activity_to_finance_dict")
def activity_to_finance_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to finance/expense creation dict.

    Finance activities track expenses, income, and budget-related items.

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

    Args:
        activity: Parsed activity line with context containing "ku" or "knowledge"

    Returns:
        Result containing dict for KnowledgeUnit creation
    """
    if not activity.is_ku():
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


@with_error_handling(error_type="system", operation="activity_to_ps_dict")
def activity_to_ps_dict(activity: ParsedActivityLine) -> Result[ConversionResult]:
    """
    Convert ParsedActivityLine to PathStep creation dict.

    PathSteps are individual steps in a learning journey,
    connecting knowledge to practice.

    Args:
        activity: Parsed activity line with context containing "ps" or "pathstep"

    Returns:
        Result containing dict for PathStep creation
    """
    if not activity.is_path_step():
        return Result.fail(
            Errors.validation(
                message="Activity is not a PathStep (missing 'ps' or 'pathstep' in @context)",
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

    # Knowledge from @ku tag and @link(ku:...)
    knowledge_uids = []
    if activity.primary_ku:
        knowledge_uids.append(activity.primary_ku)
    knowledge_uids.extend(activity.get_linked_knowledge())

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
        "knowledge_uids": knowledge_uids,
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
