---
title: Domain Lateral Service - Quick Start Guide
updated: '2026-02-02'
category: patterns
related_skills:
- base-analytics-service
related_docs: []
---
# Domain Lateral Service - Quick Start Guide

**Goal:** Create a lateral relationship service for your domain in 30 minutes

---

## Step 1: Copy the Goals Example

```bash
# Copy the template
cp core/services/goals/goals_lateral_service.py \
   core/services/tasks/tasks_lateral_service.py
```

---

## Step 2: Find & Replace Domain Name

In `tasks_lateral_service.py`, replace:
- `Goals` → `Tasks`
- `goals` → `tasks`
- `goal` → `task`
- `GoalsOperations` → `TasksOperations`

**Result:**
```python
class TasksLateralService:
    """Domain-specific service for Task lateral relationships."""

    def __init__(
        self,
        driver: Any,
        tasks_service: Any,  # TasksOperations protocol
    ) -> None:
        self.driver = driver
        self.tasks_service = tasks_service
        self.lateral_service = LateralRelationshipService(driver)
```

---

## Step 3: Customize Domain-Specific Methods

Keep these core methods (they're generic):
- `create_blocking_relationship()` ✅ Works for all domains
- `create_alternative_relationship()` ✅ Works for all domains
- `create_complementary_relationship()` ✅ Works for all domains
- `get_blocking_*()` ✅ Works for all domains
- `get_alternative_*()` ✅ Works for all domains
- `get_sibling_*()` ✅ Works for all domains
- `delete_blocking_relationship()` ✅ Works for all domains

Add domain-specific methods if needed:
```python
# Example for Tasks
async def create_prerequisite_relationship(
    self,
    prerequisite_task_uid: str,
    dependent_task_uid: str,
    strength: float = 0.8,
    user_uid: str | None = None,
) -> Result[bool]:
    """
    Create PREREQUISITE_FOR relationship (softer than BLOCKS).

    For tasks where order is recommended but not required.
    """
    # Verify ownership
    if user_uid:
        for task_uid in [prerequisite_task_uid, dependent_task_uid]:
            ownership = await self.tasks_service.verify_ownership(
                task_uid, user_uid
            )
            if ownership.is_error:
                return ownership

    # Create relationship
    return await self.lateral_service.create_lateral_relationship(
        source_uid=prerequisite_task_uid,
        target_uid=dependent_task_uid,
        relationship_type=LateralRelationType.PREREQUISITE_FOR,
        metadata={
            "strength": strength,
            "domain": "tasks",
            "created_by": user_uid,
        },
        validate=True,
        auto_inverse=True,
    )
```

---

## Step 4: Add to Services Bootstrap ✅ COMPLETE

**Status:** All 8 domain lateral services successfully bootstrapped in `/core/utils/services_bootstrap.py`

Services created (line ~1249):
```python
# Core lateral relationship service (domain-agnostic)
lateral_service = LateralRelationshipService(driver)

# Domain-specific lateral services (8 total)
tasks_lateral = TasksLateralService(driver=driver, tasks_service=activity_services["tasks"])
goals_lateral = GoalsLateralService(driver=driver, goals_service=activity_services["goals"])
habits_lateral = HabitsLateralService(driver=driver, habits_service=activity_services["habits"])
events_lateral = EventsLateralService(driver=driver, events_service=activity_services["events"])
choices_lateral = ChoicesLateralService(driver=driver, choices_service=activity_services["choices"])
principles_lateral = PrinciplesLateralService(driver=driver, principles_service=activity_services["principles"])
ku_lateral = KuLateralService(driver=driver, ku_service=learning_services["ku_service"])
ls_lateral = LsLateralService(driver=driver, ls_service=learning_services["learning_steps"])
lp_lateral = LpLateralService(driver=driver, lp_service=learning_services["learning_paths"])
```

Services container (line ~2148):
```python
services = Services(
    # ... other services ...
    lateral=lateral_service,
    tasks_lateral=tasks_lateral,
    goals_lateral=goals_lateral,
    habits_lateral=habits_lateral,
    events_lateral=events_lateral,
    choices_lateral=choices_lateral,
    principles_lateral=principles_lateral,
    ku_lateral=ku_lateral,
    ls_lateral=ls_lateral,
    lp_lateral=lp_lateral,
)
```

---

## Step 5: Test Basic Flow

```python
# In a test or route
async def test_task_blocking():
    # Create two sibling tasks
    setup_task = await tasks_service.create_task(
        user_uid=user_uid,
        title="Setup Development Environment",
        priority=Priority.HIGH
    )

    deploy_task = await tasks_service.create_task(
        user_uid=user_uid,
        title="Deploy to Production",
        priority=Priority.MEDIUM
    )

    # Create blocking relationship
    result = await services.tasks_lateral.create_blocking_relationship(
        blocker_uid=setup_task.uid,
        blocked_uid=deploy_task.uid,
        reason="Must setup environment before deployment",
        severity="required",
        user_uid=user_uid
    )

    assert result.is_ok

    # Query blocking tasks
    blocking = await services.tasks_lateral.get_blocking_goals(
        task_uid=deploy_task.uid,
        user_uid=user_uid
    )

    assert len(blocking.value) == 1
    assert blocking.value[0]["target_uid"] == setup_task.uid
```

---

## Complete Example: Habits Domain

```python
# core/services/habits/habits_lateral_service.py

from typing import Any
from core.models.enums.lateral_relationship_types import LateralRelationType
from core.services.lateral_relationships import LateralRelationshipService
from core.utils.result_simplified import Errors, Result

class HabitsLateralService:
    """Domain-specific service for Habit lateral relationships."""

    def __init__(self, driver: Any, habits_service: Any) -> None:
        self.driver = driver
        self.habits_service = habits_service
        self.lateral_service = LateralRelationshipService(driver)

    async def create_stacking_relationship(
        self,
        first_habit_uid: str,
        second_habit_uid: str,
        trigger: str = "after",  # "after", "before", "during"
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create STACKS_WITH relationship for habit chaining.

        Example: Meditate STACKS_WITH Exercise (do exercise after meditation)
        """
        if user_uid:
            for habit_uid in [first_habit_uid, second_habit_uid]:
                ownership = await self.habits_service.verify_ownership(
                    habit_uid, user_uid
                )
                if ownership.is_error:
                    return ownership

        return await self.lateral_service.create_lateral_relationship(
            source_uid=first_habit_uid,
            target_uid=second_habit_uid,
            relationship_type=LateralRelationType.STACKS_WITH,
            metadata={
                "trigger": trigger,
                "domain": "habits",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Directional based on trigger
        )

    async def create_complementary_relationship(
        self,
        habit_a_uid: str,
        habit_b_uid: str,
        synergy_description: str,
        synergy_score: float = 0.7,
        user_uid: str | None = None,
    ) -> Result[bool]:
        """
        Create COMPLEMENTARY_TO relationship for synergistic habits.

        Example: Meditation complements Exercise (both support wellness)
        """
        if not 0.0 <= synergy_score <= 1.0:
            return Errors.validation("synergy_score must be 0.0-1.0")

        if user_uid:
            for habit_uid in [habit_a_uid, habit_b_uid]:
                ownership = await self.habits_service.verify_ownership(
                    habit_uid, user_uid
                )
                if ownership.is_error:
                    return ownership

        return await self.lateral_service.create_lateral_relationship(
            source_uid=habit_a_uid,
            target_uid=habit_b_uid,
            relationship_type=LateralRelationType.COMPLEMENTARY_TO,
            metadata={
                "synergy_description": synergy_description,
                "synergy_score": synergy_score,
                "domain": "habits",
                "created_by": user_uid,
            },
            validate=True,
            auto_inverse=False,  # Symmetric
        )

    async def get_habit_stack(
        self,
        habit_uid: str,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """Get all habits in the stacking chain."""
        if user_uid:
            ownership = await self.habits_service.verify_ownership(
                habit_uid, user_uid
            )
            if ownership.is_error:
                return ownership

        return await self.lateral_service.get_lateral_relationships(
            entity_uid=habit_uid,
            relationship_types=[LateralRelationType.STACKS_WITH],
            direction="both",
            include_metadata=True,
        )

    async def get_complementary_habits(
        self,
        habit_uid: str,
        min_synergy: float = 0.5,
        user_uid: str | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """Get habits that complement this habit."""
        if user_uid:
            ownership = await self.habits_service.verify_ownership(
                habit_uid, user_uid
            )
            if ownership.is_error:
                return ownership

        all_complementary = await self.lateral_service.get_lateral_relationships(
            entity_uid=habit_uid,
            relationship_types=[LateralRelationType.COMPLEMENTARY_TO],
            direction="both",
            include_metadata=True,
        )

        if all_complementary.is_error:
            return all_complementary

        # Filter by minimum synergy score
        filtered = [
            habit for habit in all_complementary.value
            if habit.get("metadata", {}).get("synergy_score", 0) >= min_synergy
        ]

        return Result.ok(filtered)
```

---

## Domain-Specific Considerations

### Tasks
- **BLOCKS** - Deployment tasks blocked by setup tasks
- **PREREQUISITE_FOR** - Softer ordering (recommended not required)
- **ALTERNATIVE_TO** - Different implementation approaches

### Habits
- **STACKS_WITH** - Habit chaining (trigger-based sequencing)
- **COMPLEMENTARY_TO** - Synergistic habits (meditation + exercise)
- **CONFLICTS_WITH** - Incompatible habits (late nights + early mornings)

### Knowledge Units (KU)
- **PREREQUISITE_FOR** - Must learn A before B
- **ENABLES** - Learning A unlocks ability to learn B
- **RELATED_TO** - Topics in similar domain
- **SIMILAR_TO** - Overlapping content

### Learning Steps (LS)
- **PREREQUISITE_FOR** - Step order in curriculum
- **ALTERNATIVE_TO** - Different learning approaches

### Learning Paths (LP)
- **ALTERNATIVE_TO** - Different curriculum paths to same goal
- **COMPLEMENTARY_TO** - Paths that enhance each other

### Events
- **CONFLICTS_WITH** - Scheduling conflicts
- **COMPLEMENTARY_TO** - Events that work well together

### Choices
- **ALTERNATIVE_TO** - Mutually exclusive options
- **BLOCKS** - Decision A prevents decision B

### Principles
- **RELATED_TO** - Principles that reinforce each other
- **COMPLEMENTARY_TO** - Principles that work together
- **CONFLICTS_WITH** - Contradictory principles

---

## Checklist

- [ ] Copy goals_lateral_service.py to your domain
- [ ] Find & replace domain names
- [ ] Add domain-specific methods (if needed)
- [ ] Import in services_bootstrap.py
- [ ] Create lateral service instance
- [ ] Add to Services container
- [ ] Write basic test
- [ ] Verify imports work
- [ ] Test create relationship
- [ ] Test query relationships
- [ ] Test delete relationship

**Time estimate:** 30-60 minutes per domain

---

## Next Steps After All Domains Created

1. **Create API Routes** (`/api/{domain}/{uid}/lateral/*`)
2. **Create UI Components** (blocking chain, alternatives grid, etc.)
3. **Integrate with Intelligence Services** (recommendations)
4. **Add to Entity Detail Pages** (show lateral relationships)
5. **Create Graph Visualizations** (interactive relationship maps)

**Total domains to implement:** 8
- Tasks, Goals, Habits, Events, Choices, Principles, KU, LS, LP

**Total estimated time:** 4-8 hours for all domains
