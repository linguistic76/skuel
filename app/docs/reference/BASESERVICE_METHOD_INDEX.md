---
updated: 2026-08-31
---

# BaseService Method Index

**Purpose:** Complete reference of all methods available in BaseService and Activity Domain facades.

**WARNING:** This file is AUTO-GENERATED. Do not edit manually.
**Regenerate:** `cd app && uv run python scripts/generate_method_index.py`
**Drift-guarded:** `tests/unit/scripts/test_generate_method_index.py`

---

## Table of Contents

- [BaseService Mixin Methods](#baseservice-mixin-methods) - Methods from 6 mixins
- [Shared Facade Mixins](#shared-facade-mixins) - Inherited by all 6 Activity Domain facades
- [Activity Domain Facades](#activity-domain-facades) - Facade-specific public methods
- [Common Patterns](#common-patterns) - Usage examples

---

## BaseService Mixin Methods

These methods are available on **all services that extend BaseService**.

### ConversionHelpersMixin

**Purpose:** DTO ↔ Domain model conversion and result handling

| Method | Async |
|--------|-------|

---

### CrudOperationsMixin

**Purpose:** CRUD operations with ownership verification

| Method | Async |
|--------|-------|
| `create()` | ✅ |
| `delete()` | ✅ |
| `delete_for_user()` | ✅ |
| `get()` | ✅ |
| `get_for_user()` | ✅ |
| `list()` | ✅ |
| `update()` | ✅ |
| `update_for_user()` | ✅ |
| `verify_ownership()` | ✅ |

---

### SearchOperationsMixin

**Purpose:** Text search, filtering, and graph-aware queries

| Method | Async |
|--------|-------|
| `count()` | ✅ |
| `get_by_category()` | ✅ |
| `get_by_relationship()` | ✅ |
| `get_by_status()` | ✅ |
| `get_for_user_filtered()` | ✅ |
| `graph_aware_faceted_search()` | ✅ |
| `list_all_categories()` | ✅ |
| `list_recent_for_user()` | ✅ |
| `list_user_categories()` | ✅ |
| `search()` | ✅ |
| `search_array_field()` | ✅ |
| `search_by_tags()` | ✅ |
| `search_connected_to()` | ✅ |
| `search_for_user()` | ✅ |
| `tag_frequencies()` | ✅ |

---

### RelationshipOperationsMixin

**Purpose:** Graph relationship operations and traversal

| Method | Async |
|--------|-------|
| `add_prerequisite()` | ✅ |
| `add_relationship()` | ✅ |
| `get_enables()` | ✅ |
| `get_hierarchy()` | ✅ |
| `get_prerequisites()` | ✅ |
| `get_relationships()` | ✅ |
| `traverse()` | ✅ |

---

### TimeQueryMixin

**Purpose:** Calendar and scheduling queries

| Method | Async |
|--------|-------|
| `get_active()` | ✅ |
| `get_overdue()` | ✅ |
| `get_upcoming()` | ✅ |
| `get_user_items_in_range()` | ✅ |
| `get_user_items_in_range_base()` | ✅ |

---

### ContextOperationsMixin

**Purpose:** Retrieve entities with enriched graph context

| Method | Async |
|--------|-------|
| `get()` | ✅ |
| `get_with_content()` | ✅ |
| `get_with_context()` | ✅ |

---

## Shared Facade Mixins

Inherited by all 6 Activity Domain facades on top of BaseService.

### KnowledgeIntelligenceDelegationMixin

**Purpose:** Knowledge intelligence delegation shared by all Activity Domain facades

| Method | Async |
|--------|-------|
| `generate_knowledge_from_entities()` | ✅ |
| `get_knowledge_prerequisites()` | ✅ |
| `get_knowledge_suggestions()` | ✅ |
| `get_learning_opportunities()` | ✅ |

---

## Activity Domain Facades

Facade-specific public methods — what each facade adds on top of the shared BaseService + KnowledgeIntelligenceDelegationMixin surface (explicit delegation methods, facade-local mixins, and overrides).

### TasksService

**Facade-specific public methods:** 57

| Method | Async |
|--------|-------|
| `analyze_learning_patterns()` | ✅ |
| `analyze_task_knowledge_impact()` | ✅ |
| `analyze_task_learning_metrics()` | ✅ |
| `assign_task_to_user()` | ✅ |
| `calculate_knowledge_aware_priorities()` | ✅ |
| `check_prerequisites()` | ✅ |
| `complete_task()` | ✅ |
| `complete_task_with_cascade()` | ✅ |
| `create()` | ✅ |
| `create_semantic_knowledge_relationship()` | ✅ |
| `create_subtask_relationship()` | ✅ |
| `create_task()` | ✅ |
| `create_task_dependency()` | ✅ |
| `create_task_from_path_step()` | ✅ |
| `create_task_with_context()` | ✅ |
| `create_tasks_from_learning_path()` | ✅ |
| `delete_task()` | ✅ |
| `delete_task_dependency()` | ✅ |
| `generate_task_insights()` | ✅ |
| `generate_task_knowledge_insights()` | ✅ |
| `get_actionable_tasks_for_user()` | ✅ |
| `get_active()` | ✅ |
| `get_blocked_by_prerequisites()` | ✅ |
| `get_curriculum_tasks()` | ✅ |
| `get_filtered_context()` | ✅ |
| `get_learning_relevant_tasks()` | ✅ |
| `get_learning_tasks_for_user()` | ✅ |
| `get_next_learning_task()` | ✅ |
| `get_overdue()` | ✅ |
| `get_parent_task()` | ✅ |
| `get_prioritized()` | ✅ |
| `get_reinforced_habit()` | ✅ |
| `get_subtasks()` | ✅ |
| `get_task()` | ✅ |
| `get_task_dependencies_for_user()` | ✅ |
| `get_task_dependency_neighbors()` | ✅ |
| `get_task_hierarchy()` | ✅ |
| `get_tasks_applying_knowledge()` | ✅ |
| `get_tasks_for_goal()` | ✅ |
| `get_tasks_for_habit()` | ✅ |
| `get_tasks_for_path_step()` | ✅ |
| `get_upcoming()` | ✅ |
| `get_user_items_in_range()` | ✅ |
| `get_user_tasks()` | ✅ |
| `link_task_to_goal()` | ✅ |
| `link_task_to_knowledge()` | ✅ |
| `list_tasks()` | ✅ |
| `record_task_completion()` | ✅ |
| `remove_subtask_relationship()` | ✅ |
| `suggest_learning_aligned_tasks()` | ✅ |
| `track_knowledge_mastery_progression()` | ✅ |
| `trigger_manual_knowledge_generation()` | ✅ |
| `unblock_task_if_ready()` | ✅ |
| `update()` | ✅ |
| `update_for_user()` | ✅ |
| `update_task()` | ✅ |
| `would_create_dependency_cycle()` | ✅ |

---

### GoalsService

**Facade-specific public methods:** 60

| Method | Async |
|--------|-------|
| `activate_goal()` | ✅ |
| `analyze_learning_patterns()` | ✅ |
| `archive_goal()` | ✅ |
| `assess_goal_achievability()` | ✅ |
| `assess_goal_feasibility()` | ✅ |
| `assess_goal_learning_alignment()` | ✅ |
| `calculate_goal_progress_with_context()` | ✅ |
| `cancel_goal()` | ✅ |
| `check_goal_capacity()` | ✅ |
| `complete_goal()` | ✅ |
| `complete_milestone()` | ✅ |
| `count_goals_achieved()` | ✅ |
| `create()` | ✅ |
| `create_goal()` | ✅ |
| `create_goal_milestone()` | ✅ |
| `create_goal_with_context()` | ✅ |
| `create_goal_with_scheduling_context()` | ✅ |
| `create_semantic_goal_relationship()` | ✅ |
| `create_subgoal_relationship()` | ✅ |
| `find_goals_requiring_knowledge()` | ✅ |
| `generate_tasks_for_goal()` | ✅ |
| `get_achievable_goals_for_user()` | ✅ |
| `get_active()` | ✅ |
| `get_advancing_goals_for_user()` | ✅ |
| `get_filtered_context()` | ✅ |
| `get_goal()` | ✅ |
| `get_goal_completion_forecast()` | ✅ |
| `get_goal_hierarchy()` | ✅ |
| `get_goal_learning_requirements()` | ✅ |
| `get_goal_load_by_timeframe()` | ✅ |
| `get_goal_milestones()` | ✅ |
| `get_goal_progress()` | ✅ |
| `get_goal_progress_dashboard()` | ✅ |
| `get_goals_blocked_by_knowledge()` | ✅ |
| `get_goals_needing_habits()` | ✅ |
| `get_learning_supporting_goals()` | ✅ |
| `get_overdue()` | ✅ |
| `get_parent_goal()` | ✅ |
| `get_schedule_aware_next_goal()` | ✅ |
| `get_stalled_goals_for_user()` | ✅ |
| `get_subgoals()` | ✅ |
| `get_upcoming()` | ✅ |
| `get_user_goals()` | ✅ |
| `get_user_items_in_range()` | ✅ |
| `link_goal_to_habit()` | ✅ |
| `link_goal_to_knowledge()` | ✅ |
| `link_goal_to_principle()` | ✅ |
| `optimize_goal_sequencing()` | ✅ |
| `pause_goal()` | ✅ |
| `remove_subgoal_relationship()` | ✅ |
| `set_status()` | ✅ |
| `suggest_goal_timeline()` | ✅ |
| `suggest_learning_aligned_goals()` | ✅ |
| `track_goal_learning_progress()` | ✅ |
| `unlink_goal_from_habit()` | ✅ |
| `update()` | ✅ |
| `update_for_user()` | ✅ |
| `update_goal()` | ✅ |
| `update_goal_from_habit_progress()` | ✅ |
| `update_goal_progress()` | ✅ |

---

### HabitsService

**Facade-specific public methods:** 73

| Method | Async |
|--------|-------|
| `analyze_habit_consistency()` | ✅ |
| `analyze_habit_performance()` | ✅ |
| `analyze_learning_patterns()` | ✅ |
| `assess_habit_learning_impact()` | ✅ |
| `check_habit_capacity()` | ✅ |
| `complete_habit_with_quality()` | ✅ |
| `complete_with_goal_impacts()` | ✅ |
| `create()` | ✅ |
| `create_habit()` | ✅ |
| `create_habit_from_learning_goal()` | ✅ |
| `create_habit_from_path_step()` | ✅ |
| `create_habit_with_context()` | ✅ |
| `create_habit_with_scheduling_context()` | ✅ |
| `create_semantic_skill_relationship()` | ✅ |
| `create_subhabit_relationship()` | ✅ |
| `create_with_goal_links()` | ✅ |
| `delete_habit_reminder()` | ✅ |
| `find_habits_developing_knowledge()` | ✅ |
| `get_actionable_habits_for_user()` | ✅ |
| `get_active()` | ✅ |
| `get_all_habits_due_today()` | ✅ |
| `get_at_risk_habits()` | ✅ |
| `get_at_risk_habits_for_user()` | ✅ |
| `get_completion_calendar()` | ✅ |
| `get_enriched_curriculum_metadata()` | — |
| `get_enriched_learning_summary()` | ✅ |
| `get_enriched_prerequisite_metadata()` | ✅ |
| `get_event_uids_for_habit()` | ✅ |
| `get_filtered_context()` | ✅ |
| `get_goal_supporting_habits_for_user()` | ✅ |
| `get_habit()` | ✅ |
| `get_habit_analytics()` | ✅ |
| `get_habit_goal_support()` | ✅ |
| `get_habit_hierarchy()` | ✅ |
| `get_habit_history()` | ✅ |
| `get_habit_knowledge_reinforcement()` | ✅ |
| `get_habit_load_by_day()` | ✅ |
| `get_habit_priorities_for_user()` | ✅ |
| `get_habit_progress()` | ✅ |
| `get_habit_readiness_for_user()` | ✅ |
| `get_habit_reminders()` | ✅ |
| `get_habit_streak()` | ✅ |
| `get_habit_trends()` | ✅ |
| `get_habits_by_frequency()` | ✅ |
| `get_habits_due_today()` | ✅ |
| `get_habits_summary_analytics()` | ✅ |
| `get_keystone_habits()` | ✅ |
| `get_learning_habits()` | ✅ |
| `get_learning_habits_for_user()` | ✅ |
| `get_learning_reinforcing_habits()` | ✅ |
| `get_overdue()` | ✅ |
| `get_parent_habit()` | ✅ |
| `get_skills_developed_by_habits()` | ✅ |
| `get_subhabits()` | ✅ |
| `get_upcoming()` | ✅ |
| `get_user_habits()` | ✅ |
| `get_user_items_in_range()` | ✅ |
| `identify_potential_keystone_habits()` | ✅ |
| `link_habit_to_knowledge()` | ✅ |
| `link_habit_to_principle()` | ✅ |
| `list_habits()` | ✅ |
| `optimize_habit_schedule()` | ✅ |
| `remove_subhabit_relationship()` | ✅ |
| `schedule_events_for_habit()` | ✅ |
| `set_habit_reminder()` | ✅ |
| `suggest_habit_frequency()` | ✅ |
| `suggest_habit_stacking()` | ✅ |
| `suggest_learning_supporting_habits()` | ✅ |
| `track_habit()` | ✅ |
| `untrack_habit()` | ✅ |
| `update()` | ✅ |
| `update_for_user()` | ✅ |
| `update_habit()` | ✅ |

---

### EventsService

**Facade-specific public methods:** 52

| Method | Async |
|--------|-------|
| `add_attendee()` | ✅ |
| `analyze_event_performance()` | ✅ |
| `analyze_learning_patterns()` | ✅ |
| `analyze_upcoming_events()` | ✅ |
| `check_conflicts()` | ✅ |
| `count_events()` | ✅ |
| `create()` | ✅ |
| `create_event()` | ✅ |
| `create_event_with_context()` | ✅ |
| `create_recurring_events()` | ✅ |
| `create_recurring_events_for_habit()` | ✅ |
| `create_recurring_instances()` | ✅ |
| `create_subevent_relationship()` | ✅ |
| `find_events()` | ✅ |
| `get_active()` | ✅ |
| `get_at_risk_habit_events()` | ✅ |
| `get_attendance_rate()` | ✅ |
| `get_calendar_events()` | ✅ |
| `get_celebrated_goal()` | ✅ |
| `get_event()` | ✅ |
| `get_event_attendees()` | ✅ |
| `get_event_hierarchy()` | ✅ |
| `get_events_for_habit()` | ✅ |
| `get_events_in_range()` | ✅ |
| `get_filtered_context()` | ✅ |
| `get_goal_contribution_metrics()` | ✅ |
| `get_habit_event_stats()` | ✅ |
| `get_habit_reinforcement_events()` | ✅ |
| `get_learning_events()` | ✅ |
| `get_next_habit_events()` | ✅ |
| `get_overdue()` | ✅ |
| `get_parent_event()` | ✅ |
| `get_quality_trends()` | ✅ |
| `get_recurring_events()` | ✅ |
| `get_reinforced_habit()` | ✅ |
| `get_subevents()` | ✅ |
| `get_upcoming()` | ✅ |
| `get_upcoming_events_for_user()` | ✅ |
| `get_user_events()` | ✅ |
| `get_user_items_in_range()` | ✅ |
| `get_weekly_summary()` | ✅ |
| `link_event_to_goal()` | ✅ |
| `link_event_to_habit()` | ✅ |
| `link_event_to_knowledge()` | ✅ |
| `miss_habit_event()` | ✅ |
| `optimize_recurring_schedule()` | ✅ |
| `remove_attendee()` | ✅ |
| `remove_subevent_relationship()` | ✅ |
| `suggest_spaced_repetition_events()` | ✅ |
| `update()` | ✅ |
| `update_event()` | ✅ |
| `update_for_user()` | ✅ |

---

### ChoicesService

**Facade-specific public methods:** 42

| Method | Async |
|--------|-------|
| `add_option()` | ✅ |
| `analyze_choice_impact()` | ✅ |
| `analyze_learning_patterns()` | ✅ |
| `count_choices()` | ✅ |
| `create()` | ✅ |
| `create_choice()` | ✅ |
| `create_choice_with_learning_guidance()` | ✅ |
| `create_semantic_choice_relationship()` | ✅ |
| `create_subchoice_relationship()` | ✅ |
| `delete_choice()` | ✅ |
| `find_choices()` | ✅ |
| `find_choices_aligned_with_principle()` | ✅ |
| `get_active()` | ✅ |
| `get_choice()` | ✅ |
| `get_choice_hierarchy()` | ✅ |
| `get_choice_quality_correlations()` | ✅ |
| `get_choices_needing_decision()` | ✅ |
| `get_decision_intelligence()` | ✅ |
| `get_decision_patterns()` | ✅ |
| `get_domain_decision_patterns()` | ✅ |
| `get_filtered_context()` | ✅ |
| `get_learning_informed_guidance()` | ✅ |
| `get_overdue()` | ✅ |
| `get_parent_choice()` | ✅ |
| `get_pending_choices()` | ✅ |
| `get_pending_decisions_for_user()` | ✅ |
| `get_subchoices()` | ✅ |
| `get_upcoming()` | ✅ |
| `get_user_choices()` | ✅ |
| `get_user_items_in_range()` | ✅ |
| `link_choice_to_goal()` | ✅ |
| `link_choice_to_habit()` | ✅ |
| `link_choice_to_principle()` | ✅ |
| `make_decision()` | ✅ |
| `remove_option()` | ✅ |
| `remove_subchoice_relationship()` | ✅ |
| `suggest_learning_aligned_choices()` | ✅ |
| `track_choice_learning_outcomes()` | ✅ |
| `update()` | ✅ |
| `update_choice()` | ✅ |
| `update_for_user()` | ✅ |
| `update_option()` | ✅ |

---

### PrinciplesService

**Facade-specific public methods:** 50

| Method | Async |
|--------|-------|
| `analyze_learning_patterns()` | ✅ |
| `assess_goal_alignment()` | ✅ |
| `assess_habit_alignment()` | ✅ |
| `assess_principle_alignment()` | ✅ |
| `assess_principle_learning_alignment()` | ✅ |
| `batch_analyze_principle_adoption()` | ✅ |
| `calculate_principle_integrity()` | ✅ |
| `create()` | ✅ |
| `create_principle()` | ✅ |
| `create_principle_expression()` | ✅ |
| `create_principle_link()` | ✅ |
| `create_subprinciple_relationship()` | ✅ |
| `frame_principle_practice_with_learning()` | ✅ |
| `get_active()` | ✅ |
| `get_aligned_principles_for_user()` | ✅ |
| `get_analytics_summary()` | ✅ |
| `get_choice_guidance_effectiveness()` | ✅ |
| `get_contextual_principles_for_user()` | ✅ |
| `get_embodiment_rates_7d()` | ✅ |
| `get_filtered_context()` | ✅ |
| `get_motivational_profile()` | ✅ |
| `get_overdue()` | ✅ |
| `get_parent_principle()` | ✅ |
| `get_principle()` | ✅ |
| `get_principle_adherence_trends()` | ✅ |
| `get_principle_conflict_analysis()` | ✅ |
| `get_principle_hierarchy()` | ✅ |
| `get_principle_links()` | ✅ |
| `get_principle_practice_opportunities_for_user()` | ✅ |
| `get_principles_by_category()` | ✅ |
| `get_principles_for_goal()` | ✅ |
| `get_principles_for_habit()` | ✅ |
| `get_principles_needing_attention_for_user()` | ✅ |
| `get_principles_needing_review()` | ✅ |
| `get_quick_principle_impact()` | ✅ |
| `get_related_principles()` | ✅ |
| `get_subprinciples()` | ✅ |
| `get_upcoming()` | ✅ |
| `get_user_items_in_range()` | ✅ |
| `get_user_principle_portfolio()` | ✅ |
| `get_user_principles()` | ✅ |
| `link_principle_to_knowledge()` | ✅ |
| `make_principle_based_decision()` | ✅ |
| `record_principle_reflection()` | ✅ |
| `remove_subprinciple_relationship()` | ✅ |
| `suggest_learning_supported_principles()` | ✅ |
| `track_principle_learning_development()` | ✅ |
| `update()` | ✅ |
| `update_for_user()` | ✅ |
| `update_principle()` | ✅ |

---

## Common Patterns

### Facade Usage (Production)

```python
from core.services.tasks_service import TasksService

# Auto-delegation to sub-services
result = await tasks_service.create_task(request, user_uid)
```

### Direct Sub-Service Usage (Testing)

```python
from core.services.tasks import TasksCoreService

core = TasksCoreService(backend=mock_backend)
result = await core.create_task(request, user_uid)
```

---

## See Also

- [Sub-Service Catalog](/docs/reference/SUB_SERVICE_CATALOG.md) - Which service does what
- [Quick Start Guide](/docs/guides/BASESERVICE_QUICK_START.md) - Usage patterns
- [Service Topology](/docs/architecture/SERVICE_TOPOLOGY.md) - Architecture diagrams
- [BaseService Source](/core/services/base_service.py) - Implementation
