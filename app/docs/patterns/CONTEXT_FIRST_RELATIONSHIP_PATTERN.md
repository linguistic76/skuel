---
title: Context-First Relationship Pattern
updated: 2026-01-30
status: current
category: patterns
tags: [context, first, pattern, patterns, relationship]
related: []
---

# Context-First Relationship Pattern

**Version:** 1.0.0
**Date:** November 25, 2025
**Status:** Design Document (Implemented 2026-11-26)

## Executive Summary

This pattern extends relationship services to leverage `UnifiedUserContext` for **personalized graph queries**. Instead of returning all related entities, context-aware methods filter, rank, and enrich results based on the user's complete state.

## The Problem

Current relationship services operate "context-blind":

```python
# Current Pattern - Returns ALL related entities
async def get_task_dependencies(self, task_uid: str) -> Result[list[Task]]:
    """Get task dependencies - no user awareness."""
    return await self.backend.get_task_dependencies(task_uid)

# What this misses:
# - Is the user ready for these dependencies? (prerequisites met?)
# - Which dependencies align with user's current goals?
# - Which should be prioritized based on user's capacity?
# - Are there knowledge gaps blocking these tasks?
```

## The Solution: Context-First Pattern

### Core Principle: "Filter by readiness, rank by relevance, enrich with insights"

```python
# NEW Pattern - Context-aware relationship queries
async def get_task_dependencies_for_user(
    self,
    task_uid: str,
    context: UnifiedUserContext
) -> Result[ContextualDependencies]:
    """
    Get task dependencies filtered and ranked by user context.

    Filters by:
    - User's mastery of required knowledge
    - User's capacity and workload
    - User's goal alignment

    Ranks by:
    - Readiness score (prerequisites met)
    - Goal contribution (alignment with active goals)
    - Urgency (deadlines, streaks at risk)

    Enriches with:
    - Blocking reasons (what's missing?)
    - Unlocking potential (what does this enable?)
    - Learning opportunities (knowledge gaps)
    """
```

## Pattern Architecture

### Layer 1: Context-Aware Return Types

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class ContextualEntity:
    """Base class for context-enriched entities."""
    uid: str
    title: str

    # Context-derived scores
    readiness_score: float  # 0.0-1.0: How ready is user for this?
    relevance_score: float  # 0.0-1.0: How relevant to user's goals?
    priority_score: float   # 0.0-1.0: Combined priority

    # Context-derived insights
    blocking_reasons: list[str] = field(default_factory=list)
    unlocks: list[str] = field(default_factory=list)  # What this enables
    learning_gaps: list[str] = field(default_factory=list)

@dataclass(frozen=True)
class ContextualTask(ContextualEntity):
    """Task enriched with user context."""
    can_start: bool = False
    estimated_time_minutes: int = 0
    contributes_to_goals: list[str] = field(default_factory=list)
    applies_knowledge: list[str] = field(default_factory=list)

@dataclass(frozen=True)
class ContextualKnowledge(ContextualEntity):
    """Knowledge unit enriched with user context."""
    user_mastery: float = 0.0  # User's current mastery
    prerequisites_met: bool = False
    application_opportunities: list[str] = field(default_factory=list)

@dataclass(frozen=True)
class ContextualDependencies:
    """Complete dependency analysis with user context."""
    task_uid: str

    # Categorized by readiness
    ready_dependencies: list[ContextualTask] = field(default_factory=list)
    blocked_dependencies: list[ContextualTask] = field(default_factory=list)

    # Categorized by type
    knowledge_requirements: list[ContextualKnowledge] = field(default_factory=list)
    task_requirements: list[ContextualTask] = field(default_factory=list)

    # Aggregated insights
    total_blocking_items: int = 0
    estimated_unblock_time_minutes: int = 0
    highest_priority_blocker: str | None = None

    # User-specific recommendations
    recommended_next_action: str = ""
    learning_path_suggestion: list[str] = field(default_factory=list)
```

### Layer 2: Context-First Method Signatures

```python
class ContextFirstRelationshipService(GenericRelationshipService[Ops, Model, DtoType]):
    """
    Base class adding context-aware methods to relationship services.

    **Philosophy:** Every relationship query can be enhanced with user context.
    - Standard methods: Return raw relationships (for system operations)
    - Context methods: Return personalized, enriched relationships (for user-facing features)

    **Naming Convention:**
    - Standard: get_task_dependencies(uid)
    - Context-First: get_task_dependencies_for_user(uid, context)
    """

    # ==========================================================================
    # CONTEXT-AWARE DEPENDENCY QUERIES
    # ==========================================================================

    async def get_dependencies_for_user(
        self,
        entity_uid: str,
        context: UnifiedUserContext,
        include_transitive: bool = False,
        max_depth: int = 2,
    ) -> Result[ContextualDependencies]:
        """
        Get dependencies filtered and ranked by user context.

        **Context Fields Used:**
        - knowledge_mastery: Filter by user's mastery levels
        - prerequisites_completed: Determine readiness
        - active_goal_uids: Calculate goal alignment
        - current_workload_score: Adjust recommendations
        - available_minutes_daily: Estimate completion feasibility

        Args:
            entity_uid: Entity to get dependencies for
            context: User's complete context
            include_transitive: Include dependencies of dependencies
            max_depth: Maximum traversal depth

        Returns:
            ContextualDependencies with enriched, ranked dependencies
        """
        # Step 1: Get raw dependencies
        raw_deps = await self.get_dependencies(entity_uid, max_depth)
        if raw_deps.is_error:
            return Result.fail(raw_deps.expect_error())

        # Step 2: Enrich each dependency with context
        ready = []
        blocked = []

        for dep in raw_deps.value:
            contextual = await self._enrich_with_context(dep, context)

            if contextual.can_start:
                ready.append(contextual)
            else:
                blocked.append(contextual)

        # Step 3: Rank by priority (goal alignment × readiness)
        ready.sort(key=lambda x: x.priority_score, reverse=True)
        blocked.sort(key=lambda x: x.relevance_score, reverse=True)

        # Step 4: Generate recommendations
        recommendation = self._generate_unblock_recommendation(blocked, context)

        return Result.ok(ContextualDependencies(
            task_uid=entity_uid,
            ready_dependencies=ready,
            blocked_dependencies=blocked,
            total_blocking_items=len(blocked),
            recommended_next_action=recommendation,
        ))

    async def _enrich_with_context(
        self,
        entity: Any,
        context: UnifiedUserContext,
    ) -> ContextualTask:
        """
        Enrich entity with user context scores and insights.

        **Scoring Logic:**
        - readiness_score: Based on prerequisites_completed, knowledge_mastery
        - relevance_score: Based on goal alignment, principle alignment
        - priority_score: readiness × relevance × urgency_factor
        """
        # Calculate readiness (prerequisites met?)
        required_knowledge = await self.get_entity_knowledge(entity.uid)
        mastered = sum(
            1 for ku_uid in required_knowledge.value
            if context.knowledge_mastery.get(ku_uid, 0) >= 0.7
        )
        readiness = mastered / len(required_knowledge.value) if required_knowledge.value else 1.0

        # Calculate relevance (goal alignment)
        entity_goals = await self.get_entity_goals(entity.uid)
        aligned = sum(
            1 for goal_uid in entity_goals.value
            if goal_uid in context.active_goal_uids
        )
        relevance = aligned / len(entity_goals.value) if entity_goals.value else 0.5

        # Calculate priority (combined score with urgency)
        urgency = self._calculate_urgency(entity, context)
        priority = (readiness * 0.4) + (relevance * 0.4) + (urgency * 0.2)

        # Identify blocking reasons
        blocking_reasons = []
        if readiness < 1.0:
            missing_knowledge = [
                ku_uid for ku_uid in required_knowledge.value
                if context.knowledge_mastery.get(ku_uid, 0) < 0.7
            ]
            blocking_reasons.extend([f"Missing knowledge: {ku}" for ku in missing_knowledge])

        return ContextualTask(
            uid=entity.uid,
            title=entity.title,
            readiness_score=readiness,
            relevance_score=relevance,
            priority_score=priority,
            can_start=readiness >= 0.7,
            blocking_reasons=blocking_reasons,
            contributes_to_goals=[g for g in entity_goals.value if g in context.active_goal_uids],
        )

    def _generate_unblock_recommendation(
        self,
        blocked: list[ContextualTask],
        context: UnifiedUserContext,
    ) -> str:
        """Generate actionable recommendation for unblocking."""
        if not blocked:
            return "All dependencies are ready!"

        # Find highest-impact blocker to resolve
        highest_impact = max(blocked, key=lambda x: x.relevance_score)

        if highest_impact.learning_gaps:
            return f"Learn '{highest_impact.learning_gaps[0]}' to unblock {highest_impact.title}"
        elif highest_impact.blocking_reasons:
            return highest_impact.blocking_reasons[0]
        else:
            return f"Complete prerequisites for {highest_impact.title}"
```

### Layer 3: Domain-Specific Extensions

```python
class TasksRelationshipService(ContextFirstRelationshipService[TasksOperations, Task, TaskDTO]):
    """
    Task relationships with context-first methods.

    **Context-First Methods:**
    - get_task_dependencies_for_user(): Dependencies filtered by readiness
    - get_actionable_tasks_for_user(): Tasks user can start NOW
    - get_learning_tasks_for_user(): Tasks that apply knowledge user is learning
    - get_goal_tasks_for_user(): Tasks contributing to active goals
    """

    async def get_actionable_tasks_for_user(
        self,
        context: UnifiedUserContext,
        limit: int = 10,
    ) -> Result[list[ContextualTask]]:
        """
        Get tasks user can start immediately, ranked by priority.

        **Filters Applied:**
        1. Prerequisites completed (knowledge mastery >= 0.7)
        2. Not blocked by other tasks
        3. Within user's capacity (workload_score < 0.8)

        **Ranking Factors:**
        1. Goal alignment (contributes_to active goals)
        2. Urgency (deadlines, dependencies waiting)
        3. Learning value (applies knowledge user is building)
        """
        # Get all user's active tasks
        all_tasks = context.active_task_uids

        actionable = []
        for task_uid in all_tasks:
            # Check if user can start this task
            deps_result = await self.get_dependencies_for_user(task_uid, context)
            if deps_result.is_error:
                continue

            deps = deps_result.value
            if deps.total_blocking_items == 0:
                # Get task details and enrich
                task_result = await self.backend.get_task(task_uid)
                if task_result.is_ok and task_result.value:
                    contextual = await self._enrich_with_context(
                        task_result.value, context
                    )
                    actionable.append(contextual)

        # Sort by priority and limit
        actionable.sort(key=lambda x: x.priority_score, reverse=True)
        return Result.ok(actionable[:limit])

    async def get_learning_tasks_for_user(
        self,
        context: UnifiedUserContext,
        knowledge_focus: list[str] | None = None,
    ) -> Result[list[ContextualTask]]:
        """
        Get tasks that apply knowledge user is currently learning.

        **Philosophy:** "Learn by doing" - find tasks that reinforce learning.

        **Context Fields Used:**
        - in_progress_knowledge_uids: Knowledge user is actively learning
        - next_recommended_knowledge: Knowledge user should learn next
        - knowledge_mastery: Filter by partially mastered (0.3-0.7)
        """
        # Focus on knowledge user is building (not mastered, not new)
        learning_knowledge = knowledge_focus or list(context.in_progress_knowledge_uids)

        learning_tasks = []
        for ku_uid in learning_knowledge:
            # Get tasks that apply this knowledge
            tasks_result = await self.get_tasks_requiring_knowledge(ku_uid)
            if tasks_result.is_ok:
                for task in tasks_result.value:
                    if task.uid in context.active_task_uids:
                        contextual = await self._enrich_with_context(task, context)
                        contextual = ContextualTask(
                            **{**contextual.__dict__,
                               'applies_knowledge': [ku_uid]}
                        )
                        learning_tasks.append(contextual)

        # Deduplicate and sort by learning impact
        seen = set()
        unique_tasks = []
        for task in learning_tasks:
            if task.uid not in seen:
                seen.add(task.uid)
                unique_tasks.append(task)

        unique_tasks.sort(key=lambda x: len(x.applies_knowledge), reverse=True)
        return Result.ok(unique_tasks)
```

## Integration with UserContextIntelligence

**Location:** `core/services/user/intelligence/` (modular package, January 2026)

### Modular Package Structure

The intelligence service is decomposed into **5 mixins** for separation of concerns:

```
core/services/user/intelligence/
├── __init__.py                   (95 lines)   - Package exports
├── types.py                      (205 lines)  - Data classes (return types)
├── learning_intelligence.py      (445 lines)  - LearningIntelligenceMixin (Methods 1-4)
├── life_path_intelligence.py     (429 lines)  - LifePathIntelligenceMixin (Method 7)
├── synergy_intelligence.py       (382 lines)  - SynergyIntelligenceMixin (Method 6)
├── schedule_intelligence.py      (469 lines)  - ScheduleIntelligenceMixin (Method 8)
├── daily_planning.py             (254 lines)  - DailyPlanningMixin (Method 5 - THE FLAGSHIP)
├── graph_native.py               (366 lines)  - GraphNativeMixin (context-based methods)
├── core.py                       (245 lines)  - UserContextIntelligence (composes mixins)
└── factory.py                    (234 lines)  - UserContextIntelligenceFactory
```

### Factory Pattern with 13 Required Domain Services

**UserContextIntelligenceFactory** holds all 13 domain services and creates intelligence instances:

```python
# File: core/services/user/intelligence/factory.py (lines 94-167)

class UserContextIntelligenceFactory:
    """
    Factory for creating UserContextIntelligence instances.

    **The 13 Required Domain Services:**
    - Activity Domains (6): tasks, goals, habits, events, choices, principles
    - Curriculum Domains (3): ku, ls, lp
    - Processing Domains (3): assignments, journals, reports
    - Temporal Domain (1): calendar

    **Fail-Fast Validation:**
    Raises ValueError if ANY of the 13 services is None.
    """

    def __init__(
        self,
        # Activity Domains (6) - All UnifiedRelationshipService with domain configs
        tasks: UnifiedRelationshipService,
        goals: UnifiedRelationshipService,
        habits: UnifiedRelationshipService,
        events: UnifiedRelationshipService,
        choices: UnifiedRelationshipService,
        principles: UnifiedRelationshipService,
        # Curriculum Domains (3)
        ku: KuGraphService,
        ls: UnifiedRelationshipService,  # January 2026: Unified
        lp: UnifiedRelationshipService,  # January 2026: Unified
        # Processing Domains (3)
        assignments: AssignmentRelationshipService,
        journals: JournalRelationshipService,
        reports: ReportRelationshipService,
        # Temporal Domain (1)
        calendar: CalendarService,
    ) -> None:
        # Fail-fast validation: ALL 13 services REQUIRED
        required = {
            "tasks": tasks, "goals": goals, "habits": habits,
            "events": events, "choices": choices, "principles": principles,
            "ku": ku, "ls": ls, "lp": lp,
            "assignments": assignments, "journals": journals, "reports": reports,
            "calendar": calendar,
        }
        missing = [name for name, service in required.items() if service is None]
        if missing:
            raise ValueError(
                f"UserContextIntelligenceFactory requires all 13 domain services. "
                f"Missing: {', '.join(missing)}"
            )

    def create(self, context: UserContext) -> UserContextIntelligence:
        """Create intelligence instance bound to specific user context."""
        return UserContextIntelligence(context=context, services=self)
```

### The 8 Flagship Methods (via Mixin Composition)

```python
# Import from modular package
from core.services.user.intelligence import UserContextIntelligence

class UserContextIntelligence(
    LearningIntelligenceMixin,
    DailyPlanningMixin,
    SynergyIntelligenceMixin,
    LifePathIntelligenceMixin,
    ScheduleIntelligenceMixin,
    GraphNativeMixin,
):
    """
    Intelligence methods powered by context-first relationship services.

    **Core Methods (8) across 5 mixins:**
    1. get_optimal_next_learning_steps() - LearningIntelligenceMixin
    2. get_learning_path_critical_path() - LearningIntelligenceMixin
    3. get_knowledge_application_opportunities() - LearningIntelligenceMixin
    4. get_unblocking_priority_order() - LearningIntelligenceMixin
    5. get_ready_to_work_on_today() - DailyPlanningMixin (THE FLAGSHIP)
    6. get_cross_domain_synergies() - SynergyIntelligenceMixin
    7. calculate_life_path_alignment() - LifePathIntelligenceMixin
    8. get_schedule_aware_recommendations() - ScheduleIntelligenceMixin
    """

    def __init__(self, context: UserContext, services: UserContextIntelligenceFactory):
        self.context = context
        self.services = services  # Access all 13 domain services

    async def get_ready_to_work_on_today(
        self,
        context: UnifiedUserContext,
    ) -> Result[DailyWorkPlan]:
        """
        THE FLAGSHIP METHOD: What should user work on today?

        **Combines Context-First Results From:**
        - tasks.get_actionable_tasks_for_user() - Ready tasks
        - ku.get_ready_to_learn_for_user() - Ready knowledge
        - habits.get_at_risk_habits_for_user() - Habits to maintain
        - goals.get_advancing_goals_for_user() - Goals to progress

        **Respects:**
        - context.available_minutes_daily (capacity)
        - context.current_energy_level (cognitive load)
        - context.current_workload_score (not overload)
        - context.preferred_time (scheduling preferences)
        """
        # Get actionable items from each domain
        tasks = await self.tasks.get_actionable_tasks_for_user(context, limit=5)
        learning = await self.ku.get_ready_to_learn_for_user(context, limit=3)
        habits = await self.habits.get_at_risk_habits_for_user(context)
        goals = await self.goals.get_advancing_goals_for_user(context, limit=2)

        # Build capacity-aware plan
        available_minutes = context.available_minutes_daily
        plan_items = []
        total_time = 0

        # Prioritize at-risk habits (maintain streaks)
        for habit in habits.value:
            if total_time + habit.estimated_time_minutes <= available_minutes:
                plan_items.append(('habit', habit))
                total_time += habit.estimated_time_minutes

        # Then high-priority tasks
        for task in tasks.value:
            if total_time + task.estimated_time_minutes <= available_minutes:
                plan_items.append(('task', task))
                total_time += task.estimated_time_minutes

        # Then learning if time permits
        for ku in learning.value:
            if total_time + 30 <= available_minutes:  # ~30 min per KU
                plan_items.append(('learn', ku))
                total_time += 30

        return Result.ok(DailyWorkPlan(
            learning=[item[1].uid for item in plan_items if item[0] == 'learn'],
            tasks=[item[1].uid for item in plan_items if item[0] == 'task'],
            habits=[item[1].uid for item in plan_items if item[0] == 'habit'],
            goals=[g.uid for g in goals.value],
            estimated_time_minutes=total_time,
            fits_capacity=total_time <= available_minutes,
            workload_utilization=total_time / available_minutes,
            rationale=self._generate_plan_rationale(plan_items, context),
        ))
```

## Implementation Status

**Status:** Implemented (November 26, 2025)
**Protocol Compliance:** Updated January 28, 2026

### Protocol Compliance Update (January 2026)

The UserContextIntelligence factory and relationship services were updated to use protocol-based interfaces:

- **Before:** Concrete backend types (e.g., `UniversalNeo4jBackend[T]`)
- **After:** Protocol interfaces (e.g., `TasksOperations`, `GoalsOperations`)
- **Impact:** Zero port dependencies - all services use Protocol interfaces exclusively

This change maintains the context-first pattern while achieving 100% protocol compliance across the codebase.

**See:** `/docs/migrations/PROTOCOL_MIXIN_ALIGNMENT_COMPLETE_2026-01-29.md` for details on the protocol migration.

## Summary

The Context-First Pattern transforms relationship services from "data retrievers" into "intelligent advisors" by leveraging the ~240 fields of `UnifiedUserContext`. Every relationship query becomes an opportunity to provide personalized, actionable insights.

**Key Insight:** UserContext isn't just data - it's the lens through which all relationships should be viewed.

**Architecture Evolution:** Originally implemented November 2025, updated January 2026 for protocol compliance as part of SKUEL's zero-dependency architecture.
