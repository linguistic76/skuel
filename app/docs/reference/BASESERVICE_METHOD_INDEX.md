# BaseService Method Index

**Purpose:** Complete reference of all methods available in BaseService and Activity Domain facades.

**Last Updated:** 2026-01-29 (Auto-generated)

**WARNING:** This file is AUTO-GENERATED. Do not edit manually.
**To update:** Run `python scripts/generate_method_index.py`

---

## Table of Contents

- [BaseService Mixin Methods](#baseservice-mixin-methods) - Methods from 7 mixins
- [Activity Domain Facades](#activity-domain-facades) - Facade delegations
- [Common Patterns](#common-patterns) - Usage examples

---

## BaseService Mixin Methods

These methods are available on **all services that extend BaseService**.

### ConversionHelpersMixin

**Purpose:** DTO ↔ Domain model conversion and result handling

| Method | Public |
|--------|--------|
| `__init__()` | 🔒 (internal) |

---

### CrudOperationsMixin

**Purpose:** CRUD operations with ownership verification

| Method | Public |
|--------|--------|
| `__init__()` | 🔒 (internal) |
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

| Method | Public |
|--------|--------|
| `__init__()` | 🔒 (internal) |
| `count()` | ✅ |
| `get_by_category()` | ✅ |
| `get_by_domain()` | ✅ |
| `get_by_relationship()` | ✅ |
| `get_by_status()` | ✅ |
| `graph_aware_faceted_search()` | ✅ |
| `list_all_categories()` | ✅ |
| `list_user_categories()` | ✅ |
| `search()` | ✅ |
| `search_array_field()` | ✅ |
| `search_by_tags()` | ✅ |
| `search_connected_to()` | ✅ |

---

### RelationshipOperationsMixin

**Purpose:** Graph relationship operations and traversal

| Method | Public |
|--------|--------|
| `__init__()` | 🔒 (internal) |
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

| Method | Public |
|--------|--------|
| `__init__()` | 🔒 (internal) |
| `get_due_soon()` | ✅ |
| `get_overdue()` | ✅ |
| `get_user_items_in_range()` | ✅ |
| `get_user_items_in_range_base()` | ✅ |

---

### UserProgressMixin

**Purpose:** Progress and mastery tracking

| Method | Public |
|--------|--------|
| `__init__()` | 🔒 (internal) |
| `get_user_curriculum()` | ✅ |
| `get_user_progress()` | ✅ |
| `update_user_mastery()` | ✅ |

---

### ContextOperationsMixin

**Purpose:** Retrieve entities with enriched graph context

| Method | Public |
|--------|--------|
| `__init__()` | 🔒 (internal) |
| `get()` | ✅ |
| `get_with_content()` | ✅ |
| `get_with_context()` | ✅ |

---

## Activity Domain Facades

Auto-generated delegation methods for each Activity Domain facade.

### TasksService

**Total Delegated Methods:** 33

#### Core Delegations (6 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `delete_task()` | `core.delete_task()` |
| `get_task()` | `core.get_task()` |
| `get_user_items_in_range()` | `core.get_user_items_in_range()` |
| `get_user_tasks()` | `core.get_user_tasks()` |
| `list_tasks()` | `core.list_tasks()` |
| `update_task()` | `core.update_task()` |

#### Intelligence Delegations (3 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `analyze_task_learning_metrics()` | `intelligence.analyze_task_learning_metrics()` |
| `generate_task_knowledge_insights()` | `intelligence.generate_task_knowledge_insights()` |
| `get_learning_opportunities()` | `intelligence.get_learning_opportunities()` |

#### Planning Delegations (3 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `get_actionable_tasks_for_user()` | `planning.get_actionable_tasks_for_user()` |
| `get_learning_tasks_for_user()` | `planning.get_learning_tasks_for_user()` |
| `get_task_dependencies_for_user()` | `planning.get_task_dependencies_for_user()` |

#### Progress Delegations (4 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `assign_task_to_user()` | `progress.assign_task_to_user()` |
| `check_prerequisites()` | `progress.check_prerequisites()` |
| `record_task_completion()` | `progress.record_task_completion()` |
| `unblock_task_if_ready()` | `progress.unblock_task_if_ready()` |

#### Relationships Delegations (3 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `analyze_task_learning_context()` | `relationships.get_cross_domain_context()` |
| `get_task_completion_impact()` | `relationships.get_completion_impact()` |
| `get_task_with_semantic_context()` | `relationships.get_with_semantic_context()` |

#### Scheduling Delegations (6 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `create_task_from_learning_step()` | `scheduling.create_task_from_learning_step()` |
| `create_task_with_context()` | `scheduling.create_task_with_context()` |
| `create_task_with_learning_context()` | `scheduling.create_task_with_learning_context()` |
| `create_tasks_from_learning_path()` | `scheduling.create_tasks_from_learning_path()` |
| `get_next_learning_task()` | `scheduling.get_next_learning_task()` |
| `suggest_learning_aligned_tasks()` | `scheduling.suggest_learning_aligned_tasks()` |

#### Search Delegations (8 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `get_blocked_by_prerequisites()` | `search.get_blocked_by_prerequisites()` |
| `get_curriculum_tasks()` | `search.get_curriculum_tasks()` |
| `get_learning_relevant_tasks()` | `search.get_learning_relevant_tasks()` |
| `get_prioritized_tasks()` | `search.get_prioritized_tasks()` |
| `get_tasks_applying_knowledge()` | `search.get_tasks_applying_knowledge()` |
| `get_tasks_for_goal()` | `search.get_tasks_for_goal()` |
| `get_tasks_for_habit()` | `search.get_tasks_for_habit()` |
| `get_tasks_for_learning_step()` | `search.get_tasks_for_learning_step()` |

---

### GoalsService

**Total Delegated Methods:** 43

#### Core Delegations (8 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `activate_goal()` | `core.activate_goal()` |
| `archive_goal()` | `core.archive_goal()` |
| `complete_goal()` | `core.complete_goal()` |
| `create_goal()` | `core.create_goal()` |
| `get_goal()` | `core.get_goal()` |
| `get_user_goals()` | `core.get_user_goals()` |
| `get_user_items_in_range()` | `core.get_user_items_in_range()` |
| `pause_goal()` | `core.pause_goal()` |

#### Intelligence Delegations (4 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `get_goal_completion_forecast()` | `intelligence.get_goal_completion_forecast()` |
| `get_goal_learning_requirements()` | `intelligence.get_goal_learning_requirements()` |
| `get_goal_progress_dashboard()` | `intelligence.get_goal_progress_dashboard()` |
| `get_goal_with_context()` | `intelligence.get_goal_with_context()` |

#### Learning Delegations (7 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `assess_goal_learning_alignment()` | `learning.assess_goal_learning_alignment()` |
| `create_goal_with_learning_integration()` | `learning.create_goal_with_learning_integration()` |
| `get_goals_blocked_by_knowledge()` | `learning.get_goals_blocked_by_knowledge()` |
| `get_goals_needing_habits()` | `learning.get_goals_needing_habits()` |
| `get_learning_supporting_goals()` | `learning.get_learning_supporting_goals()` |
| `suggest_learning_aligned_goals()` | `learning.suggest_learning_aligned_goals()` |
| `track_goal_learning_progress()` | `learning.track_goal_learning_progress()` |

#### Progress Delegations (7 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `calculate_goal_progress_with_context()` | `progress.calculate_goal_progress_with_context()` |
| `complete_milestone()` | `progress.complete_milestone()` |
| `create_goal_milestone()` | `progress.create_goal_milestone()` |
| `get_goal_milestones()` | `progress.get_goal_milestones()` |
| `get_goal_progress()` | `progress.get_goal_progress()` |
| `update_goal_from_habit_progress()` | `progress.update_goal_from_habit_progress()` |
| `update_goal_progress()` | `progress.update_goal_progress()` |

#### Scheduling Delegations (8 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `assess_goal_achievability()` | `scheduling.assess_goal_achievability()` |
| `check_goal_capacity()` | `scheduling.check_goal_capacity()` |
| `create_goal_with_learning_scheduling()` | `scheduling.create_goal_with_learning_context()` |
| `create_goal_with_scheduling_context()` | `scheduling.create_goal_with_context()` |
| `get_goal_load_by_timeframe()` | `scheduling.get_goal_load_by_timeframe()` |
| `get_schedule_aware_next_goal()` | `scheduling.get_schedule_aware_next_goal()` |
| `optimize_goal_sequencing()` | `scheduling.optimize_goal_sequencing()` |
| `suggest_goal_timeline()` | `scheduling.suggest_goal_timeline()` |

#### Search Delegations (9 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `get_goals_by_category()` | `search.get_by_category()` |
| `get_goals_by_domain()` | `search.get_by_domain()` |
| `get_goals_by_status()` | `search.get_by_status()` |
| `get_goals_due_soon()` | `search.get_due_soon()` |
| `get_overdue_goals()` | `search.get_overdue()` |
| `get_prioritized_goals()` | `search.get_prioritized()` |
| `list_all_goal_categories()` | `search.list_all_categories()` |
| `list_goal_categories()` | `search.list_user_categories()` |
| `search_goals()` | `search.search()` |

---

### HabitsService

**Total Delegated Methods:** 47

#### Core Delegations (5 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `create_habit()` | `core.create_habit()` |
| `get_habit()` | `core.get_habit()` |
| `get_user_habits()` | `core.get_user_habits()` |
| `get_user_items_in_range()` | `core.get_user_items_in_range()` |
| `list_habits()` | `core.list_habits()` |

#### Events Delegations (2 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `get_events_for_habit()` | `events.get_events_for_habit()` |
| `schedule_events_for_habit()` | `events.schedule_events_for_habit()` |

#### Intelligence Delegations (4 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `analyze_habit_performance()` | `intelligence.analyze_habit_performance()` |
| `get_habit_goal_support()` | `intelligence.get_habit_goal_support()` |
| `get_habit_knowledge_reinforcement()` | `intelligence.get_habit_knowledge_reinforcement()` |
| `get_habit_with_context()` | `intelligence.get_habit_with_context()` |

#### Learning Delegations (6 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `assess_habit_learning_impact()` | `learning.assess_habit_learning_impact()` |
| `create_habit_from_learning_goal()` | `learning.create_habit_from_learning_goal()` |
| `create_habit_with_learning_alignment()` | `learning.create_habit_with_learning_alignment()` |
| `get_learning_habits()` | `learning.get_learning_habits()` |
| `get_learning_reinforcing_habits()` | `learning.get_learning_reinforcing_habits()` |
| `suggest_learning_supporting_habits()` | `learning.suggest_learning_supporting_habits()` |

#### Planning Delegations (5 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `get_actionable_habits_for_user()` | `planning.get_actionable_habits_for_user()` |
| `get_goal_supporting_habits_for_user()` | `planning.get_goal_supporting_habits_for_user()` |
| `get_habit_priorities_for_user()` | `planning.get_habit_priorities_for_user()` |
| `get_habit_readiness_for_user()` | `planning.get_habit_readiness_for_user()` |
| `get_learning_habits_for_user()` | `planning.get_learning_habits_for_user()` |

#### Progress Delegations (5 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `analyze_habit_consistency()` | `progress.analyze_habit_consistency()` |
| `complete_habit_with_quality()` | `progress.complete_habit_with_quality()` |
| `get_at_risk_habits()` | `progress.get_at_risk_habits()` |
| `get_keystone_habits()` | `progress.get_keystone_habits()` |
| `identify_potential_keystone_habits()` | `progress.identify_potential_keystone_habits()` |

#### Scheduling Delegations (8 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `check_habit_capacity()` | `scheduling.check_habit_capacity()` |
| `create_habit_from_learning_step()` | `scheduling.create_habit_from_learning_step()` |
| `create_habit_with_learning_scheduling_context()` | `scheduling.create_habit_with_learning_context()` |
| `create_habit_with_scheduling_context()` | `scheduling.create_habit_with_context()` |
| `get_habit_load_by_day()` | `scheduling.get_habit_load_by_day()` |
| `optimize_habit_schedule()` | `scheduling.optimize_habit_schedule()` |
| `suggest_habit_frequency()` | `scheduling.suggest_habit_frequency()` |
| `suggest_habit_stacking()` | `scheduling.suggest_habit_stacking()` |

#### Search Delegations (12 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `get_active_habits()` | `search.get_active_habits()` |
| `get_all_habits_due_today()` | `search.get_all_due_today()` |
| `get_habits_by_category()` | `search.get_by_category()` |
| `get_habits_by_domain()` | `search.get_by_domain()` |
| `get_habits_by_frequency()` | `search.get_by_frequency()` |
| `get_habits_by_status()` | `search.get_by_status()` |
| `get_habits_due_today()` | `search.get_user_due_today()` |
| `get_overdue_habits()` | `search.get_overdue()` |
| `get_prioritized_habits()` | `search.get_prioritized()` |
| `list_all_habit_categories()` | `search.list_all_categories()` |
| `list_habit_categories()` | `search.list_user_categories()` |
| `search_habits()` | `search.search()` |

---

### EventsService

**Total Delegated Methods:** 50

#### Core Delegations (6 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `count_events()` | `core.count_events()` |
| `find_events()` | `core.find_events()` |
| `get_event()` | `core.get_event()` |
| `get_user_events()` | `core.get_user_events()` |
| `get_user_items_in_range()` | `core.get_user_items_in_range()` |
| `update()` | `core.update()` |

#### Habits Delegations (7 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `complete_event_with_quality()` | `habits.complete_event_with_quality()` |
| `create_recurring_events_for_habit()` | `habits.create_recurring_events_for_habit()` |
| `get_at_risk_habit_events()` | `habits.get_at_risk_habit_events()` |
| `get_events_for_habit()` | `habits.get_events_for_habit()` |
| `get_habit_reinforcement_events()` | `habits.get_habit_reinforcement_events()` |
| `get_next_habit_events()` | `habits.get_next_habit_events()` |
| `miss_habit_event()` | `habits.miss_habit_event()` |

#### Intelligence Delegations (5 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `analyze_event_performance()` | `intelligence.analyze_event_performance()` |
| `analyze_upcoming_events()` | `intelligence.analyze_upcoming_events()` |
| `get_event_goal_support()` | `intelligence.get_event_goal_support()` |
| `get_event_knowledge_reinforcement()` | `intelligence.get_event_knowledge_reinforcement()` |
| `get_event_with_context()` | `intelligence.get_event_with_context()` |

#### Learning Delegations (7 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `create_learning_path_schedule()` | `learning.create_learning_path_schedule()` |
| `create_study_session()` | `learning.create_study_session()` |
| `get_events_for_knowledge()` | `learning.get_events_for_knowledge()` |
| `get_events_for_learning_path()` | `learning.get_events_for_learning_path()` |
| `get_knowledge_reinforcement_stats()` | `learning.get_knowledge_reinforcement_stats()` |
| `get_learning_events()` | `learning.get_learning_events()` |
| `suggest_spaced_repetition_events()` | `learning.suggest_spaced_repetition_events()` |

#### Progress Delegations (6 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `complete_event_with_cascade()` | `progress.complete_event_with_cascade()` |
| `get_attendance_rate()` | `progress.get_attendance_rate()` |
| `get_goal_contribution_metrics()` | `progress.get_goal_contribution_metrics()` |
| `get_habit_event_stats()` | `progress.get_habit_event_stats()` |
| `get_quality_trends()` | `progress.get_quality_trends()` |
| `get_weekly_summary()` | `progress.get_weekly_summary()` |

#### Relationships Delegations (3 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `analyze_event_impact()` | `relationships.get_completion_impact()` |
| `get_event_cross_domain_context()` | `relationships.get_cross_domain_context()` |
| `get_event_with_semantic_context()` | `relationships.get_with_semantic_context()` |

#### Scheduling Delegations (8 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `check_conflicts()` | `scheduling.check_conflicts()` |
| `create_recurring_events()` | `scheduling.create_recurring_events()` |
| `find_next_available_slot()` | `scheduling.find_next_available_slot()` |
| `get_busy_times()` | `scheduling.get_busy_times()` |
| `get_calendar_density()` | `scheduling.get_calendar_density()` |
| `optimize_recurring_schedule()` | `scheduling.optimize_recurring_schedule()` |
| `schedule_event_smart()` | `scheduling.schedule_event_smart()` |
| `suggest_time_slots()` | `scheduling.suggest_time_slots()` |

#### Search Delegations (8 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `get_calendar_events()` | `search.get_calendar_events()` |
| `get_event_history()` | `search.get_history()` |
| `get_events_by_status()` | `search.get_by_status()` |
| `get_events_due_soon()` | `search.get_due_soon()` |
| `get_events_in_range()` | `search.get_in_range()` |
| `get_overdue_events()` | `search.get_overdue()` |
| `get_prioritized_events()` | `search.get_prioritized()` |
| `search_events()` | `search.search()` |

---

### ChoicesService

**Total Delegated Methods:** 24

#### Core Delegations (3 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `get_choice()` | `core.get_choice()` |
| `get_user_choices()` | `core.get_user_choices()` |
| `get_user_items_in_range()` | `core.get_user_items_in_range()` |

#### Intelligence Delegations (6 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `analyze_choice_impact()` | `intelligence.analyze_choice_impact()` |
| `get_choice_quality_correlations()` | `intelligence.get_choice_quality_correlations()` |
| `get_choice_with_context()` | `intelligence.get_choice_with_context()` |
| `get_decision_intelligence()` | `intelligence.get_decision_intelligence()` |
| `get_decision_patterns()` | `intelligence.get_decision_patterns()` |
| `get_domain_decision_patterns()` | `intelligence.get_domain_decision_patterns()` |

#### Learning Delegations (4 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `create_choice_with_learning_guidance()` | `learning.create_choice_with_learning_guidance()` |
| `get_learning_informed_guidance()` | `learning.get_learning_informed_guidance()` |
| `suggest_learning_aligned_choices()` | `learning.suggest_learning_aligned_choices()` |
| `track_choice_learning_outcomes()` | `learning.track_choice_learning_outcomes()` |

#### Search Delegations (11 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `get_choices_by_domain()` | `search.get_by_domain()` |
| `get_choices_by_status()` | `search.get_by_status()` |
| `get_choices_by_urgency()` | `search.get_by_urgency()` |
| `get_choices_due_soon()` | `search.get_due_soon()` |
| `get_choices_needing_decision()` | `search.get_needing_decision()` |
| `get_overdue_choices()` | `search.get_overdue()` |
| `get_pending_choices()` | `search.get_pending()` |
| `get_prioritized_choices()` | `search.get_prioritized()` |
| `list_all_choice_categories()` | `search.list_all_categories()` |
| `list_choice_categories()` | `search.list_user_categories()` |
| `search_choices()` | `search.search()` |

---

### PrinciplesService

**Total Delegated Methods:** 34

#### Alignment Delegations (4 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `assess_goal_alignment()` | `alignment.assess_goal_alignment()` |
| `assess_habit_alignment()` | `alignment.assess_habit_alignment()` |
| `get_motivational_profile()` | `alignment.get_motivational_profile()` |
| `make_principle_based_decision()` | `alignment.make_principle_based_decision()` |

#### Core Delegations (3 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `get_principle()` | `core.get_principle()` |
| `get_user_items_in_range()` | `core.get_user_items_in_range()` |
| `get_user_principles()` | `core.get_user_principles()` |

#### Intelligence Delegations (4 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `assess_principle_alignment()` | `intelligence.assess_principle_alignment()` |
| `get_principle_adherence_trends()` | `intelligence.get_principle_adherence_trends()` |
| `get_principle_conflict_analysis()` | `intelligence.get_principle_conflict_analysis()` |
| `get_principle_with_context()` | `intelligence.get_principle_with_context()` |

#### Learning Delegations (4 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `assess_principle_learning_alignment()` | `learning.assess_principle_learning_alignment()` |
| `frame_principle_practice_with_learning()` | `learning.frame_principle_practice_with_learning()` |
| `suggest_learning_supported_principles()` | `learning.suggest_learning_supported_principles()` |
| `track_principle_learning_development()` | `learning.track_principle_learning_development()` |

#### Planning Delegations (3 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `get_contextual_principles_for_user()` | `planning.get_contextual_principles_for_user()` |
| `get_principle_practice_opportunities_for_user()` | `planning.get_principle_practice_opportunities_for_user()` |
| `get_principles_needing_attention_for_user()` | `planning.get_principles_needing_attention_for_user()` |

#### Reflection Delegations (7 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `get_alignment_trend()` | `reflection.calculate_alignment_trend()` |
| `get_conflict_analysis()` | `reflection.get_conflict_analysis()` |
| `get_cross_domain_insights()` | `reflection.get_cross_domain_insights()` |
| `get_recent_reflections()` | `reflection.get_recent_reflections()` |
| `get_reflection_frequency()` | `reflection.get_reflection_frequency()` |
| `get_reflections_for_principle()` | `reflection.get_reflections_for_principle()` |
| `save_reflection()` | `reflection.save_reflection()` |

#### Search Delegations (9 methods)

| Facade Method | Target Method |
|---------------|---------------|
| `get_principle_categories()` | `search.list_user_categories()` |
| `get_principles_by_category()` | `search.get_by_category()` |
| `get_principles_by_status()` | `search.get_by_status()` |
| `get_principles_by_strength()` | `search.get_by_strength()` |
| `get_principles_for_choice()` | `search.get_for_choice()` |
| `get_principles_for_goal()` | `search.get_for_goal()` |
| `get_principles_needing_review()` | `search.get_needing_review()` |
| `get_related_principles()` | `search.get_related_principles()` |
| `list_all_principle_categories()` | `search.list_all_categories()` |

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
