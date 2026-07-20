"""
User Context Queries - Cypher Query Definitions and Execution
==============================================================

**EXTRACTED (December 2025):** From user_context_builder.py for separation of concerns.

This module contains:
- MEGA_QUERY: Complete user context in single query (rich + standard)
- CONSOLIDATED_QUERY: Standard context query (UIDs only)
- UserContextQueryExecutor: Query execution with error handling

Architecture:
- Pure query logic, no context population
- Used by UserContextBuilder for orchestration
"""

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityStatus
from core.models.type_hints import UserUID
from core.ports.query_types import CurrentPathStepItem, GroupSummary
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.sort_functions import get_updated_timestamp

if TYPE_CHECKING:
    from core.ports import QueryExecutor

logger = get_logger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _sort_by_last_viewed_at(item: dict[str, Any]) -> Any:
    """Sort key function for last_viewed_at timestamp."""
    return item["last_viewed_at"]


# =============================================================================
# STATUS-SET PARAMETERS
# =============================================================================

# MEGA_QUERY and CONSOLIDATED_QUERY express the same status-set business rules
# ("which statuses count as open / overdue-eligible / pending"). They ride in
# as parameters computed from EntityStatus so each rule exists exactly once
# and cannot drift between the two queries or from the enum.
STATUS_PARAMS: dict[str, Any] = {
    "open_task_statuses": [
        EntityStatus.DRAFT.value,
        EntityStatus.SCHEDULED.value,
        EntityStatus.ACTIVE.value,
        EntityStatus.BLOCKED.value,
    ],
    "overdue_eligible_task_statuses": [
        EntityStatus.DRAFT.value,
        EntityStatus.SCHEDULED.value,
        EntityStatus.ACTIVE.value,
    ],
    "pending_choice_statuses": [EntityStatus.DRAFT.value, EntityStatus.ACTIVE.value],
    "open_ps_statuses": [EntityStatus.DRAFT.value, EntityStatus.ACTIVE.value],
    "status_active": EntityStatus.ACTIVE.value,
    "status_completed": EntityStatus.COMPLETED.value,
}


# =============================================================================
# QUERY CONSTANTS
# =============================================================================

MEGA_QUERY: str = """
MATCH (user:User {uid: $user_uid})

// ====================================================================
// TASKS - Fetch with BOTH UIDs and rich data
// ====================================================================
OPTIONAL MATCH (user)-[:OWNS]->(task:Task)

// Collect UIDs by status (for standard context)
WITH user,
     collect(CASE WHEN task.status IN $open_task_statuses THEN task.uid END) as active_task_uids,
     collect(CASE WHEN task.status = $status_completed THEN task.uid END) as completed_task_uids,
     collect(CASE WHEN task.status IN $overdue_eligible_task_statuses AND task.due_date IS NOT NULL AND date(task.due_date) < date($today) THEN task.uid END) as overdue_task_uids,
     collect(CASE WHEN task.due_date IS NOT NULL AND date(task.due_date) = date($today) THEN task.uid END) as today_task_uids,
     collect(task) as all_tasks_nodes

// Filter tasks for rich data — active status always included; window entities included if touched since $window_start
UNWIND CASE WHEN size(all_tasks_nodes) > 0 THEN all_tasks_nodes ELSE [null] END as task
OPTIONAL MATCH (task)-[:HAS_SUBTASK]->(subtask:Task)
WHERE task IS NOT NULL AND (task.status IN $open_task_statuses OR task.updated_at >= datetime($window_start))
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     task, collect(DISTINCT {uid: subtask.uid, title: subtask.title, status: subtask.status}) as task_subtasks

OPTIONAL MATCH (task)-[dep_rel:DEPENDS_ON]->(dependency:Task)
WHERE task IS NOT NULL AND coalesce(dep_rel.confidence, 1.0) >= $min_confidence
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     task, task_subtasks,
     collect(DISTINCT {uid: dependency.uid, title: dependency.title, confidence: dep_rel.confidence}) as task_dependencies

// Roll activity→knowledge edges up to atomic Ku grain (ADR-046 § Ku-grain substance):
// keep direct :Ku targets (1-hop) and bridge :PathStep targets to the Kus they
// compose via curriculum-internal TRAINS_KU|USES_KU (2-hop). DISTINCT per task.
OPTIONAL MATCH (task)-[app_rel:APPLIES_KNOWLEDGE]->(applied:Entity)
WHERE task IS NOT NULL AND coalesce(app_rel.confidence, 1.0) >= $min_confidence
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     task, task_subtasks, task_dependencies,
     collect(DISTINCT applied) as applied_nodes
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     task, task_subtasks, task_dependencies,
     [n IN applied_nodes WHERE n:Ku | {uid: n.uid, title: n.title}] +
     reduce(acc = [], p IN applied_nodes | acc + [(p)-[:TRAINS_KU|USES_KU]->(k:Ku) | {uid: k.uid, title: k.title}])
     as task_knowledge

OPTIONAL MATCH (task)-[:FULFILLS_GOAL]->(goal:Goal)
WHERE task IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     collect(CASE WHEN task IS NOT NULL THEN {
         entity: properties(task),
         graph_context: {
             subtasks: task_subtasks,
             dependencies: task_dependencies,
             applied_knowledge: task_knowledge,
             goal_context: CASE WHEN goal IS NOT NULL THEN {uid: goal.uid, title: goal.title, progress: goal.progress} ELSE null END
         }
     } END) as tasks_rich

// ====================================================================
// GOALS - Fetch with BOTH UIDs and rich data
// ====================================================================
OPTIONAL MATCH (user)-[:OWNS]->(goal:Goal)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     collect(CASE WHEN goal.status = $status_active THEN goal.uid END) as active_goal_uids,
     collect(CASE WHEN goal.status = $status_completed THEN goal.uid END) as completed_goal_uids,
     collect({uid: goal.uid, progress: coalesce(goal.progress, 0.0)}) as goal_progress_data,
     collect(goal) as all_goals_nodes

// Filter goals for rich data — active status always included; window entities included if touched since $window_start
UNWIND CASE WHEN size(all_goals_nodes) > 0 THEN all_goals_nodes ELSE [null] END as goal
OPTIONAL MATCH (contributing_task:Task)-[:FULFILLS_GOAL]->(goal)
WHERE goal IS NOT NULL AND (goal.status = $status_active OR goal.updated_at >= datetime($window_start))
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data,
     goal, collect(DISTINCT {uid: contributing_task.uid, title: contributing_task.title, status: contributing_task.status}) as goal_tasks

OPTIONAL MATCH (goal)-[:HAS_SUBGOAL]->(subgoal:Goal)
WHERE goal IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data,
     goal, goal_tasks,
     collect(DISTINCT {uid: subgoal.uid, title: subgoal.title, progress: subgoal.progress}) as goal_subgoals

OPTIONAL MATCH (goal)-[req_rel:REQUIRES_KNOWLEDGE]->(req_ku:Entity)
WHERE goal IS NOT NULL AND coalesce(req_rel.confidence, 1.0) >= $min_confidence
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data,
     goal, goal_tasks, goal_subgoals,
     collect(DISTINCT {uid: req_ku.uid, title: req_ku.title, confidence: req_rel.confidence}) as goal_required_knowledge

WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data,
     collect(CASE WHEN goal IS NOT NULL THEN {
         entity: properties(goal),
         graph_context: {
             contributing_tasks: goal_tasks,
             sub_goals: goal_subgoals,
             required_knowledge: goal_required_knowledge,
             milestone_progress: {
                 total: size(coalesce(goal.milestones, [])),
                 completed: size([m IN coalesce(goal.milestones, []) WHERE m.completed = true])
             }
         }
     } END) as goals_rich

// ====================================================================
// KNOWLEDGE - Fetch with BOTH UIDs and rich data
// ====================================================================
OPTIONAL MATCH (user)-[mastered:MASTERED|IN_PROGRESS]->(ku:Entity)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     collect({
         uid: ku.uid,
         // MASTERED carries mastery_score; IN_PROGRESS carries progress (0.0-1.0)
         // from record_knowledge_progress / UserProgressBackend.record_progress.
         // The constants are the last resort for an edge with neither.
         score: coalesce(mastered.mastery_score, mastered.progress, CASE WHEN type(mastered) = 'MASTERED' THEN 1.0 ELSE 0.1 END),
         mastered_at: mastered.mastered_at,
         confidence: coalesce(mastered.confidence, 1.0)
     }) as knowledge_mastery_data,
     collect(ku) as all_knowledge_nodes

// Filter knowledge for rich data (with prerequisites/dependents)
UNWIND CASE WHEN size(all_knowledge_nodes) > 0 THEN all_knowledge_nodes ELSE [null] END as ku
OPTIONAL MATCH (ku)-[prereq_rel:REQUIRES_KNOWLEDGE]->(prereq:Entity)
WHERE ku IS NOT NULL AND coalesce(prereq_rel.confidence, 1.0) >= $min_confidence
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data,
     ku, collect(DISTINCT {uid: prereq.uid, title: prereq.title, confidence: prereq_rel.confidence}) as ku_prerequisites

OPTIONAL MATCH (dependent:Entity)-[dep_rel:REQUIRES_KNOWLEDGE]->(ku)
WHERE ku IS NOT NULL AND coalesce(dep_rel.confidence, 1.0) >= $min_confidence
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data,
     ku, ku_prerequisites,
     collect(DISTINCT {uid: dependent.uid, title: dependent.title, confidence: dep_rel.confidence}) as ku_dependents

WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data,
     collect(CASE WHEN ku IS NOT NULL THEN {
         uid: ku.uid,
         ku: properties(ku),
         graph_context: {
             prerequisites: ku_prerequisites,
             dependents: ku_dependents
         }
     } END) as knowledge_rich

// ====================================================================
// KU INTERACTION TRACKING (MVP - Phase B)
// ====================================================================
// Track view counts, time spent, and recently viewed KUs from VIEWED relationships
OPTIONAL MATCH (user)-[viewed:VIEWED]->(viewed_ku:Entity)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     collect({
         uid: viewed_ku.uid,
         view_count: coalesce(viewed.view_count, 1),
         time_spent_seconds: coalesce(viewed.time_spent_seconds, 0),
         last_viewed_at: viewed.last_viewed_at
     }) as ku_view_data

// Track marked as read KUs
OPTIONAL MATCH (user)-[:MARKED_AS_READ]->(read_ku:Entity)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data,
     collect(read_ku.uid) as ku_marked_as_read_uids

// Track bookmarked KUs
OPTIONAL MATCH (user)-[:BOOKMARKED]->(bookmarked_ku:Entity)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids,
     collect(bookmarked_ku.uid) as ku_bookmarked_uids

// ====================================================================
// HABITS - Fetch UIDs, metadata, AND rich data with graph neighborhoods
// ====================================================================
OPTIONAL MATCH (user)-[:OWNS]->(habit:Habit)
WHERE habit.status = $status_active OR habit.updated_at >= datetime($window_start)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     collect(CASE WHEN habit.status = $status_active THEN habit.uid END) as active_habit_uids,
     collect(CASE WHEN habit.status = $status_active THEN {uid: habit.uid, streak: coalesce(habit.current_streak, 0), rate: coalesce(habit.completion_rate, 0.0)} END) as habit_metadata,
     collect(habit) as all_habit_nodes

// Filter habits for rich data (with graph neighborhoods)
UNWIND CASE WHEN size(all_habit_nodes) > 0 THEN all_habit_nodes ELSE [null] END as habit
OPTIONAL MATCH (habit)-[:FULFILLS_GOAL|SUPPORTS_GOAL|CONTRIBUTES_TO_GOAL]->(linked_goal:Goal)
WHERE habit IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata,
     habit, collect(DISTINCT {uid: linked_goal.uid, title: linked_goal.title, status: linked_goal.status}) as habit_linked_goals

// Roll activity→knowledge edges up to atomic Ku grain (ADR-046 § Ku-grain substance).
OPTIONAL MATCH (habit)-[:APPLIES_KNOWLEDGE|REINFORCES_KNOWLEDGE]->(habit_applied:Entity)
WHERE habit IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata,
     habit, habit_linked_goals,
     collect(DISTINCT habit_applied) as habit_applied_nodes
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata,
     habit, habit_linked_goals,
     [n IN habit_applied_nodes WHERE n:Ku | {uid: n.uid, title: n.title}] +
     reduce(acc = [], p IN habit_applied_nodes | acc + [(p)-[:TRAINS_KU|USES_KU]->(k:Ku) | {uid: k.uid, title: k.title}])
     as habit_applied_knowledge

OPTIONAL MATCH (prereq_habit:Habit)-[:ENABLES_HABIT|PREREQUISITE_FOR]->(habit)
WHERE habit IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata,
     habit, habit_linked_goals, habit_applied_knowledge,
     collect(DISTINCT {uid: prereq_habit.uid, title: prereq_habit.title}) as habit_prerequisites

WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata,
     collect(CASE WHEN habit IS NOT NULL THEN {
         entity: properties(habit),
         graph_context: {
             linked_goals: habit_linked_goals,
             applied_knowledge: habit_applied_knowledge,
             prerequisites: [p IN habit_prerequisites WHERE p.uid IS NOT NULL]
         }
     } END) as habits_rich

// ====================================================================
// EVENTS - Fetch UIDs AND rich data with graph neighborhoods
// ====================================================================
OPTIONAL MATCH (user)-[:OWNS]->(event:Event)
WHERE date(event.event_date) >= date(datetime($window_start))
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     collect(CASE WHEN date(event.event_date) >= date($today) THEN event.uid END) as upcoming_event_uids,
     collect(CASE WHEN date(event.event_date) = date($today) THEN event.uid END) as today_event_uids,
     collect(event) as all_event_nodes

// Filter events for rich data (with graph neighborhoods)
UNWIND CASE WHEN size(all_event_nodes) > 0 THEN all_event_nodes ELSE [null] END as event
// Roll activity→knowledge edges up to atomic Ku grain (ADR-046 § Ku-grain substance).
OPTIONAL MATCH (event)-[:APPLIES_KNOWLEDGE]->(event_applied:Entity)
WHERE event IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids,
     event, collect(DISTINCT event_applied) as event_applied_nodes
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids,
     event, (
       [n IN event_applied_nodes WHERE n:Ku | {uid: n.uid, title: n.title}] +
       reduce(acc = [], p IN event_applied_nodes | acc + [(p)-[:TRAINS_KU|USES_KU]->(k:Ku) | {uid: k.uid, title: k.title}])
     )[0..10] as event_applied_knowledge

OPTIONAL MATCH (event)-[:CONTRIBUTES_TO_GOAL]->(event_goal:Goal)
WHERE event IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids,
     event, event_applied_knowledge,
     collect(DISTINCT {uid: event_goal.uid, title: event_goal.title, status: event_goal.status})[0..10] as event_linked_goals

OPTIONAL MATCH (event_habit:Habit)-[:PRACTICED_AT_EVENT]->(event)
WHERE event IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids,
     event, event_applied_knowledge, event_linked_goals,
     collect(DISTINCT {uid: event_habit.uid, title: event_habit.title})[0..10] as event_practiced_habits

OPTIONAL MATCH (event)-[:CONFLICTS_WITH]-(conflicting_event:Event)
WHERE event IS NOT NULL AND conflicting_event.uid <> event.uid
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids,
     event, event_applied_knowledge, event_linked_goals, event_practiced_habits,
     collect(DISTINCT {uid: conflicting_event.uid, title: conflicting_event.title})[0..5] as event_conflicting_events

// Event → Habit reinforcement edge (graph-native; replaces the former
// reinforces_habit_uid property). Loaded into graph_context.reinforced_habits.
OPTIONAL MATCH (event)-[:REINFORCES_HABIT]->(event_reinforced_habit:Habit)
WHERE event IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids,
     event, event_applied_knowledge, event_linked_goals, event_practiced_habits,
     event_conflicting_events,
     collect(DISTINCT {uid: event_reinforced_habit.uid, title: event_reinforced_habit.title})[0..10] as event_reinforced_habits

// Aggregate events into rich format
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids,
     collect(CASE WHEN event IS NOT NULL THEN {
         entity: properties(event),
         graph_context: {
             applied_knowledge: event_applied_knowledge,
             linked_goals: event_linked_goals,
             practiced_habits: event_practiced_habits,
             conflicting_events: event_conflicting_events,
             reinforced_habits: event_reinforced_habits
         }
     } END) as events_rich

// ====================================================================
// PRINCIPLES - Fetch UIDs AND rich data with graph neighborhoods
// ====================================================================
OPTIONAL MATCH (user)-[:OWNS]->(principle:Principle)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     collect(principle.uid) as core_principle_uids,
     collect(principle) as all_principle_nodes

// Filter principles for rich data (with graph neighborhoods)
UNWIND CASE WHEN size(all_principle_nodes) > 0 THEN all_principle_nodes ELSE [null] END as principle
// Roll activity→knowledge edges up to atomic Ku grain (ADR-046 § Ku-grain substance).
OPTIONAL MATCH (principle)-[:GROUNDED_IN_KNOWLEDGE]->(principle_grounded:Entity)
WHERE principle IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids,
     principle, collect(DISTINCT principle_grounded) as principle_grounded_nodes
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids,
     principle, (
       [n IN principle_grounded_nodes WHERE n:Ku | {uid: n.uid, title: n.title}] +
       reduce(acc = [], p IN principle_grounded_nodes | acc + [(p)-[:TRAINS_KU|USES_KU]->(k:Ku) | {uid: k.uid, title: k.title}])
     )[0..10] as principle_grounded_knowledge

OPTIONAL MATCH (principle)-[:GUIDES_GOAL]->(principle_goal:Goal)
WHERE principle IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids,
     principle, principle_grounded_knowledge,
     collect(DISTINCT {uid: principle_goal.uid, title: principle_goal.title, status: principle_goal.status})[0..10] as principle_guided_goals

OPTIONAL MATCH (principle)-[:GUIDES_CHOICE]->(principle_choice:Choice)
WHERE principle IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids,
     principle, principle_grounded_knowledge, principle_guided_goals,
     collect(DISTINCT {uid: principle_choice.uid, title: principle_choice.title})[0..10] as principle_guided_choices

OPTIONAL MATCH (principle_habit:Habit)-[:EMBODIES_PRINCIPLE]->(principle)
WHERE principle IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids,
     principle, principle_grounded_knowledge, principle_guided_goals, principle_guided_choices,
     collect(DISTINCT {uid: principle_habit.uid, title: principle_habit.title})[0..10] as principle_embodying_habits

OPTIONAL MATCH (principle_task:Task)-[:ALIGNED_WITH_PRINCIPLE]->(principle)
WHERE principle IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids,
     principle, principle_grounded_knowledge, principle_guided_goals, principle_guided_choices, principle_embodying_habits,
     collect(DISTINCT {uid: principle_task.uid, title: principle_task.title, status: principle_task.status})[0..10] as principle_aligned_tasks

// Aggregate principles into rich format
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids,
     collect(CASE WHEN principle IS NOT NULL THEN {
         entity: properties(principle),
         graph_context: {
             grounded_knowledge: principle_grounded_knowledge,
             guided_goals: principle_guided_goals,
             guided_choices: principle_guided_choices,
             embodying_habits: principle_embodying_habits,
             aligned_tasks: principle_aligned_tasks
         }
     } END) as principles_rich

// ====================================================================
// CHOICES - Fetch UIDs AND rich data (pending/active; windowed completed also included)
// ====================================================================
OPTIONAL MATCH (user)-[:OWNS]->(choice:Choice)
WHERE choice.status IN $pending_choice_statuses OR datetime(choice.created_at) >= datetime($window_start)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     collect(CASE WHEN choice.status IN $pending_choice_statuses THEN choice.uid END) as pending_choice_uids,
     collect(choice) as all_choice_nodes

// Filter choices for rich data (with graph neighborhoods)
UNWIND CASE WHEN size(all_choice_nodes) > 0 THEN all_choice_nodes ELSE [null] END as choice
// Roll activity→knowledge edges up to atomic Ku grain (ADR-046 § Ku-grain substance).
OPTIONAL MATCH (choice)-[:INFORMED_BY_KNOWLEDGE]->(choice_informing:Entity)
WHERE choice IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids,
     choice, collect(DISTINCT choice_informing) as choice_informing_nodes
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids,
     choice, (
       [n IN choice_informing_nodes WHERE n:Ku | {uid: n.uid, title: n.title}] +
       reduce(acc = [], p IN choice_informing_nodes | acc + [(p)-[:TRAINS_KU|USES_KU]->(k:Ku) | {uid: k.uid, title: k.title}])
     )[0..10] as choice_informing_knowledge

OPTIONAL MATCH (choice)-[:INFORMED_BY_PRINCIPLE]->(choice_principle:Principle)
WHERE choice IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids,
     choice, choice_informing_knowledge,
     collect(DISTINCT {uid: choice_principle.uid, title: choice_principle.title})[0..10] as choice_guiding_principles

OPTIONAL MATCH (choice)-[:AFFECTS_GOAL]->(choice_goal:Goal)
WHERE choice IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids,
     choice, choice_informing_knowledge, choice_guiding_principles,
     collect(DISTINCT {uid: choice_goal.uid, title: choice_goal.title, status: choice_goal.status})[0..10] as choice_affected_goals

OPTIONAL MATCH (choice)-[:OPENS_LEARNING_PATH]->(choice_path:LearningPath)
WHERE choice IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids,
     choice, choice_informing_knowledge, choice_guiding_principles, choice_affected_goals,
     collect(DISTINCT {uid: choice_path.uid, title: choice_path.title})[0..5] as choice_opened_paths

OPTIONAL MATCH (choice_task:Task)-[:IMPLEMENTS_CHOICE]->(choice)
WHERE choice IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids,
     choice, choice_informing_knowledge, choice_guiding_principles, choice_affected_goals, choice_opened_paths,
     collect(DISTINCT {uid: choice_task.uid, title: choice_task.title, status: choice_task.status})[0..10] as choice_implementing_tasks

// Aggregate choices into rich format
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids,
     collect(CASE WHEN choice IS NOT NULL THEN {
         entity: properties(choice),
         graph_context: {
             informing_knowledge: choice_informing_knowledge,
             guiding_principles: choice_guiding_principles,
             affected_goals: choice_affected_goals,
             opened_paths: choice_opened_paths,
             implementing_tasks: choice_implementing_tasks
         }
     } END) as choices_rich

// ====================================================================
// LEARNING PATHS - Fetch with BOTH UIDs and rich data
// ====================================================================
OPTIONAL MATCH (user)-[:ENROLLED_IN|OWNS]->(lp:LearningPath)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     collect(lp.uid) as enrolled_path_uids,
     collect(lp) as all_lp_nodes

// Filter learning paths for rich data (with graph neighborhoods)
UNWIND CASE WHEN size(all_lp_nodes) > 0 THEN all_lp_nodes ELSE [null] END as lp
// HAS_STEP is the one containment edge (RelationshipName.HAS_STEP) — written by
// both ingestion (connections.contains_steps) and the LP step mixin; CONTAINS_STEP
// never had a writer.
OPTIONAL MATCH (lp)-[r_step:HAS_STEP]->(step:PathStep)
WHERE lp IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids,
     lp, collect(DISTINCT {
         uid: step.uid,
         title: step.title,
         completed: step.completed,
         sequence: coalesce(r_step.sequence, step.sequence)
     }) as lp_steps

OPTIONAL MATCH (lp)-[:REQUIRES_KNOWLEDGE]->(prereq_ku:Entity)
WHERE lp IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids,
     lp, lp_steps,
     collect(DISTINCT {uid: prereq_ku.uid, title: prereq_ku.title}) as lp_prereqs

OPTIONAL MATCH (lp)-[:ALIGNED_WITH_GOAL]->(lp_goal:Goal)
WHERE lp IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids,
     lp, lp_steps, lp_prereqs,
     collect(DISTINCT {uid: lp_goal.uid, title: lp_goal.title, status: lp_goal.status}) as lp_goals

OPTIONAL MATCH (lp)-[:EMBODIES_PRINCIPLE]->(lp_principle:Principle)
WHERE lp IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids,
     lp, lp_steps, lp_prereqs, lp_goals,
     collect(DISTINCT {uid: lp_principle.uid, title: lp_principle.title}) as lp_embodied_principles

WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids,
     collect(CASE WHEN lp IS NOT NULL THEN {
         path: properties(lp),
         graph_context: {
             steps: lp_steps,
             prerequisite_knowledge: lp_prereqs,
             aligned_goals: lp_goals,
             embodied_principles: lp_embodied_principles,
             total_steps: size(lp_steps),
             completed_steps: size([s IN lp_steps WHERE s.completed = true]),
             progress_percentage: CASE WHEN size(lp_steps) > 0
                 THEN toFloat(size([s IN lp_steps WHERE s.completed = true])) / size(lp_steps) * 100.0
                 ELSE 0.0 END
         }
     } END) as paths_rich

// ====================================================================
// PATH STEPS - Fetch active steps with rich data
// IN_PROGRESS is the edge the PS enrollment door writes (PsMasteryService);
// WORKING_ON/ENROLLED_IN had no production writer targeting PathStep, which
// left active_path_steps_rich permanently empty (systems-review Arc B).
// ====================================================================
OPTIONAL MATCH (user)-[:IN_PROGRESS]->(ps:PathStep)
// Vault-ingested PathSteps carry no status property (NULL) — treat missing
// status as active; the filter only excludes explicitly terminal states.
WHERE ps.status IS NULL OR ps.status IN $open_ps_statuses
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     collect(ps) as all_ps_nodes

// Filter path steps for rich data (with graph neighborhoods)
UNWIND CASE WHEN size(all_ps_nodes) > 0 THEN all_ps_nodes ELSE [null] END as ps
OPTIONAL MATCH (ps)-[:REQUIRES_STEP]->(prereq_step:PathStep)
WHERE ps IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     ps, collect(DISTINCT {uid: prereq_step.uid, title: prereq_step.title, completed: prereq_step.completed}) as ps_prereq_steps

OPTIONAL MATCH (ps)-[:BUILDS_HABIT]->(ps_habit:Habit)
WHERE ps IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     ps, ps_prereq_steps,
     collect(DISTINCT {uid: ps_habit.uid, title: ps_habit.title}) as ps_habits

OPTIONAL MATCH (ps)-[:ASSIGNS_TASK]->(ps_task:Task)
WHERE ps IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     ps, ps_prereq_steps, ps_habits,
     collect(DISTINCT {uid: ps_task.uid, title: ps_task.title, status: ps_task.status}) as ps_tasks

// USES_KU is THE canonical composition edge (PathStep composes atomic Kus);
// TEACHES was a phantom name with no RelationshipName entry and no writer.
// entity_type rides along so consumers split Ku vs PathStep targets by
// label-derived type, never by UID prefix (ADR-013 never-sniff rule);
// rel_type rides along so consumers can separate composition (USES_KU/
// TRAINS_KU/CONTAINS_KNOWLEDGE) from prerequisite/enabled neighbors.
OPTIONAL MATCH (ps)-[ps_ku_r:USES_KU|TRAINS_KU|CONTAINS_KNOWLEDGE|REQUIRES_KNOWLEDGE|ENABLES_KNOWLEDGE]->(ps_ku:Entity)
WHERE ps IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     ps, ps_prereq_steps, ps_habits, ps_tasks,
     collect(DISTINCT {uid: ps_ku.uid, title: ps_ku.title, domain: ps_ku.domain, entity_type: ps_ku.entity_type, rel_type: type(ps_ku_r)}) as ps_knowledge

OPTIONAL MATCH (lp_parent:LearningPath)-[:HAS_STEP]->(ps)
WHERE ps IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     collect(CASE WHEN ps IS NOT NULL THEN {
         step: properties(ps),
         graph_context: {
             prerequisite_steps: ps_prereq_steps,
             practice_habits: ps_habits,
             practice_tasks: ps_tasks,
             knowledge_relationships: ps_knowledge,
             learning_path: CASE WHEN lp_parent IS NOT NULL
                 THEN {uid: lp_parent.uid, name: lp_parent.title}
                 ELSE null END,
             total_prerequisites: size(ps_prereq_steps),
             total_practice_opportunities: size(ps_habits) + size(ps_tasks),
             is_sequenced: lp_parent IS NOT NULL
         }
     } END) as steps_rich

// ====================================================================
// LIFE PATH - Fetch user's designated life path
// Designation flips entity_type on the LP node (no label swap) and stores
// the alignment score on the ULTIMATE_PATH edge — match/read accordingly
// (LifePathBackend.designate_life_path / update_alignment_score).
// ====================================================================
OPTIONAL MATCH (user)-[lp_rel:ULTIMATE_PATH]->(life_path:Entity {entity_type: 'life_path'})
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     steps_rich,
     life_path.uid AS life_path_uid,
     lp_rel.designated_at AS life_path_designated_at,
     lp_rel.alignment_score AS life_path_alignment_score

// ====================================================================
// MOCs - Maps of Content (emergent — any Entity with ORGANIZES relationships)
// ====================================================================
OPTIONAL MATCH (user)-[:OWNS]->(moc:Entity)-[:ORGANIZES]->(:Entity)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     steps_rich,
     life_path_uid, life_path_designated_at, life_path_alignment_score,
     collect(DISTINCT moc.uid) as active_moc_uids,
     collect(DISTINCT {uid: moc.uid, updated: moc.updated_at}) as moc_metadata

// ====================================================================
// ACTIVITY REPORT - Latest report for intelligence reasoning
// ====================================================================
OPTIONAL MATCH (user)-[:OWNS]->(ar:ActivityReport)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     steps_rich,
     life_path_uid, life_path_designated_at, life_path_alignment_score,
     active_moc_uids, moc_metadata,
     ar
ORDER BY ar.period_end DESC
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     steps_rich,
     life_path_uid, life_path_designated_at, life_path_alignment_score,
     active_moc_uids, moc_metadata,
     collect(ar)[0] AS latest_ar

// ====================================================================
// ACTIVE INSIGHTS - For cross_domain_insights intelligence field
// ====================================================================
OPTIONAL MATCH (user)-[:HAS_INSIGHT]->(ins:Insight)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     steps_rich,
     life_path_uid, life_path_designated_at, life_path_alignment_score,
     active_moc_uids, moc_metadata,
     latest_ar, ins
WHERE ins IS NULL OR (
    NOT ins.dismissed AND NOT ins.actioned
    AND (ins.expires_at IS NULL OR datetime(ins.expires_at) > datetime())
)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     steps_rich,
     life_path_uid, life_path_designated_at, life_path_alignment_score,
     active_moc_uids, moc_metadata,
     latest_ar,
     [x IN collect(CASE WHEN ins IS NOT NULL THEN {
         uid: ins.uid,
         type: ins.insight_type,
         title: ins.title,
         impact: ins.impact,
         confidence: coalesce(ins.confidence, 0.0)
     } ELSE null END) WHERE x IS NOT NULL][0..10] AS active_insights_raw

// ====================================================================
// SUBMISSION & FEEDBACK STATS - Learning loop engagement tracking
// ====================================================================
OPTIONAL MATCH (user)-[:OWNS]->(sub:Entity)
WHERE sub.entity_type IN ['exercise_submission', 'je_input', 'je_output', 'user_entry']
  AND NOT (sub.entity_type = 'user_entry' AND sub.pipeline IN ['reference', 'knowledge'])
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     steps_rich,
     life_path_uid, life_path_designated_at, life_path_alignment_score,
     active_moc_uids, moc_metadata,
     latest_ar, active_insights_raw,
     count(CASE WHEN sub.entity_type = 'exercise_submission' OR (sub.entity_type = 'user_entry' AND sub.pipeline IS NOT NULL AND sub.pipeline <> 'transcribe_and_structure' AND sub.pipeline <> 'journal' AND sub.pipeline <> 'reference') THEN 1 END) AS total_submission_count,
     count(CASE WHEN sub.entity_type = 'je_input' OR (sub.entity_type = 'user_entry' AND (sub.pipeline = 'transcribe_and_structure' OR sub.pipeline = 'journal')) THEN 1 END) AS total_journal_count,
     count(CASE WHEN (sub.entity_type <> 'user_entry' OR sub.pipeline <> 'reference') AND datetime(sub.created_at) >= datetime($window_start) THEN 1 END) AS submissions_in_window,
     max(sub.created_at) AS last_submission_date,
     collect(sub.uid) AS all_submission_uids

// Feedback received for user's submissions
OPTIONAL MATCH (user)-[:OWNS]->(owned_sub:Entity)<-[:REPORT_FOR]-(fb:Entity)
WHERE owned_sub.entity_type IN ['exercise_submission', 'je_input', 'je_output', 'user_entry']
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     steps_rich,
     life_path_uid, life_path_designated_at, life_path_alignment_score,
     active_moc_uids, moc_metadata,
     latest_ar, active_insights_raw,
     total_submission_count, total_journal_count, submissions_in_window,
     last_submission_date, all_submission_uids,
     count(fb) AS feedback_received_count,
     count(CASE WHEN datetime(fb.created_at) >= datetime($window_start) THEN 1 END) AS feedback_in_window,
     collect(DISTINCT owned_sub.uid) AS submissions_with_feedback

// Pending feedback = submissions without any feedback
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     steps_rich,
     life_path_uid, life_path_designated_at, life_path_alignment_score,
     active_moc_uids, moc_metadata,
     latest_ar, active_insights_raw,
     total_submission_count, total_journal_count, submissions_in_window,
     last_submission_date,
     feedback_received_count, feedback_in_window,
     size([uid IN all_submission_uids WHERE NOT uid IN submissions_with_feedback]) AS pending_feedback_count

// Assigned exercises and unsubmitted exercises
OPTIONAL MATCH (user)-[:MEMBER_OF]->(grp:Group)<-[:SHARED_WITH_GROUP]-(ex:Entity {entity_type: 'exercise', scope: 'assigned'})
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     steps_rich,
     life_path_uid, life_path_designated_at, life_path_alignment_score,
     active_moc_uids, moc_metadata,
     latest_ar, active_insights_raw,
     total_submission_count, total_journal_count, submissions_in_window,
     last_submission_date,
     feedback_received_count, feedback_in_window, pending_feedback_count,
     count(ex) AS assigned_exercise_count,
     collect(CASE WHEN NOT (:Entity {user_uid: user.uid})-[:FULFILLS_EXERCISE]->(ex) THEN {
         uid: ex.uid,
         title: coalesce(ex.title, 'Untitled Exercise'),
         due_date: ex.due_date
     } END) AS unsubmitted_raw

WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     steps_rich,
     life_path_uid, life_path_designated_at, life_path_alignment_score,
     active_moc_uids, moc_metadata,
     latest_ar, active_insights_raw,
     total_submission_count, total_journal_count, submissions_in_window,
     last_submission_date,
     feedback_received_count, feedback_in_window, pending_feedback_count,
     assigned_exercise_count,
     assigned_exercise_count - size([x IN unsubmitted_raw WHERE x IS NOT NULL]) AS completed_exercise_count,
     [x IN unsubmitted_raw WHERE x IS NOT NULL][0..5] AS unsubmitted_exercises

// REVISED EXERCISES — Pending teacher-created revisions targeting this student
// A RevisedExercise is "pending" when the student hasn't submitted against it yet.
OPTIONAL MATCH (re:RevisedExercise {student_uid: user.uid})
WHERE NOT EXISTS {
    MATCH (:Entity {user_uid: user.uid})-[:FULFILLS_EXERCISE]->(re)
}
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     steps_rich,
     life_path_uid, life_path_designated_at, life_path_alignment_score,
     active_moc_uids, moc_metadata,
     latest_ar, active_insights_raw,
     total_submission_count, total_journal_count, submissions_in_window,
     last_submission_date,
     feedback_received_count, feedback_in_window, pending_feedback_count,
     assigned_exercise_count, completed_exercise_count, unsubmitted_exercises,
     [x IN collect(CASE WHEN re IS NOT NULL THEN {
         uid: re.uid,
         title: coalesce(re.title, 'Revision'),
         instructions: re.instructions,
         original_exercise_uid: re.original_exercise_uid,
         report_uid: re.report_uid,
         revision_number: re.revision_number,
         created_at: re.created_at
     } END) WHERE x IS NOT NULL][0..5] AS pending_revised_exercises

// ====================================================================
// ENTRY KNOWLEDGE APPLIED — (UserEntry)-[:APPLIES_KNOWLEDGE]->(Ku)
// Written by the EXTRACT_ACTIVITIES pipeline (ADR-069); read here for the
// substance "entries" channel and the ZPD entry_application signal.
// Same Ku-grain rollup as the task subquery above (ADR-046).
// ====================================================================
OPTIONAL MATCH (user)-[:OWNS]->(entry:UserEntry)-[entry_app_rel:APPLIES_KNOWLEDGE]->(entry_applied:Entity)
WHERE coalesce(entry_app_rel.confidence, 1.0) >= $min_confidence
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     steps_rich,
     life_path_uid, life_path_designated_at, life_path_alignment_score,
     active_moc_uids, moc_metadata,
     latest_ar, active_insights_raw,
     total_submission_count, total_journal_count, submissions_in_window,
     last_submission_date,
     feedback_received_count, feedback_in_window, pending_feedback_count,
     assigned_exercise_count, completed_exercise_count, unsubmitted_exercises,
     pending_revised_exercises,
     entry, collect(DISTINCT entry_applied) AS entry_applied_nodes
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     steps_rich,
     life_path_uid, life_path_designated_at, life_path_alignment_score,
     active_moc_uids, moc_metadata,
     latest_ar, active_insights_raw,
     total_submission_count, total_journal_count, submissions_in_window,
     last_submission_date,
     feedback_received_count, feedback_in_window, pending_feedback_count,
     assigned_exercise_count, completed_exercise_count, unsubmitted_exercises,
     pending_revised_exercises,
     collect(CASE WHEN entry IS NOT NULL THEN {
         uid: entry.uid,
         ku_uids: [n IN entry_applied_nodes WHERE n:Ku | n.uid] +
                  reduce(acc = [], p IN entry_applied_nodes | acc + [(p)-[:TRAINS_KU|USES_KU]->(k:Ku) | k.uid])
     } END) AS entry_knowledge_raw

// ====================================================================
// Return BOTH UIDs (standard context) AND rich data (rich context)
// ====================================================================
RETURN {
    uids: {
        active_task_uids: [uid IN active_task_uids WHERE uid IS NOT NULL],
        completed_task_uids: [uid IN completed_task_uids WHERE uid IS NOT NULL],
        overdue_task_uids: [uid IN overdue_task_uids WHERE uid IS NOT NULL],
        today_task_uids: [uid IN today_task_uids WHERE uid IS NOT NULL],
        active_goal_uids: [uid IN active_goal_uids WHERE uid IS NOT NULL],
        completed_goal_uids: [uid IN completed_goal_uids WHERE uid IS NOT NULL],
        active_habit_uids: active_habit_uids,
        upcoming_event_uids: upcoming_event_uids,
        today_event_uids: [uid IN today_event_uids WHERE uid IS NOT NULL],
        core_principle_uids: [uid IN core_principle_uids WHERE uid IS NOT NULL],
        pending_choice_uids: [uid IN pending_choice_uids WHERE uid IS NOT NULL],
        enrolled_path_uids: enrolled_path_uids,
        goal_progress: [item IN goal_progress_data WHERE item.uid IS NOT NULL | {uid: item.uid, progress: item.progress}],
        knowledge_mastery: [item IN knowledge_mastery_data WHERE item.uid IS NOT NULL | {uid: item.uid, score: item.score, mastered_at: item.mastered_at, confidence: item.confidence}],
        ku_view_data: [item IN ku_view_data WHERE item.uid IS NOT NULL | {uid: item.uid, view_count: item.view_count, time_spent_seconds: item.time_spent_seconds, last_viewed_at: item.last_viewed_at}],
        ku_marked_as_read_uids: [uid IN ku_marked_as_read_uids WHERE uid IS NOT NULL],
        ku_bookmarked_uids: [uid IN ku_bookmarked_uids WHERE uid IS NOT NULL],
        habit_metadata: habit_metadata,
        active_moc_uids: [uid IN active_moc_uids WHERE uid IS NOT NULL],
        moc_metadata: [item IN moc_metadata WHERE item.uid IS NOT NULL]
    },
    entities: {
        tasks: [item IN tasks_rich WHERE item.entity IS NOT NULL],
        goals: [item IN goals_rich WHERE item.entity IS NOT NULL],
        habits: [item IN habits_rich WHERE item.entity IS NOT NULL],
        events: [item IN events_rich WHERE item.entity IS NOT NULL],
        principles: [item IN principles_rich WHERE item.entity IS NOT NULL],
        choices: [item IN choices_rich WHERE item.entity IS NOT NULL],
        learning_paths: [item IN paths_rich WHERE item.path IS NOT NULL | {entity: item.path, graph_context: item.graph_context}],
        path_steps: [item IN steps_rich WHERE item.step IS NOT NULL | {entity: item.step, graph_context: item.graph_context}]
    },
    rich: {
        knowledge: knowledge_rich,
        learning_paths: [item IN paths_rich WHERE item.path IS NOT NULL],
        path_steps: [item IN steps_rich WHERE item.step IS NOT NULL]
    },
    life_path: {
        uid: life_path_uid,
        designated_at: life_path_designated_at,
        alignment_score: life_path_alignment_score
    },
    progress_counts: {
        tasks_completed: size([uid IN completed_task_uids WHERE uid IS NOT NULL]),
        tasks_total: size([uid IN active_task_uids WHERE uid IS NOT NULL]) + size([uid IN completed_task_uids WHERE uid IS NOT NULL]),
        goals_completed: size([uid IN completed_goal_uids WHERE uid IS NOT NULL]),
        goals_total: size([uid IN active_goal_uids WHERE uid IS NOT NULL]) + size([uid IN completed_goal_uids WHERE uid IS NOT NULL])
    },
    activity_report: CASE WHEN latest_ar IS NOT NULL THEN {
        uid: latest_ar.uid,
        period: latest_ar.time_period,
        period_end: latest_ar.period_end,
        content: latest_ar.processed_content,
        user_annotation: latest_ar.user_annotation
    } ELSE null END,
    active_insights_raw: active_insights_raw,
    entry_knowledge_applied: [x IN entry_knowledge_raw WHERE x IS NOT NULL],
    submission_stats: {
        total_submission_count: total_submission_count,
        total_journal_count: total_journal_count,
        submissions_in_window: submissions_in_window,
        last_submission_date: last_submission_date,
        feedback_received_count: feedback_received_count,
        feedback_in_window: feedback_in_window,
        pending_feedback_count: pending_feedback_count,
        assigned_exercise_count: assigned_exercise_count,
        completed_exercise_count: completed_exercise_count,
        unsubmitted_exercises: unsubmitted_exercises,
        pending_revised_exercises: pending_revised_exercises
    }
} as result
"""


CONSOLIDATED_QUERY: str = """
// Start with user node
MATCH (user:User {uid: $user_uid})

// Tasks - parallel collection with conditional aggregation
OPTIONAL MATCH (user)-[:OWNS]->(task:Task)
WITH user,
     collect(CASE WHEN task.status IN $open_task_statuses THEN task.uid END) as active_task_uids,
     collect(CASE WHEN task.status = $status_completed THEN task.uid END) as completed_task_uids,
     collect(CASE WHEN task.status IN $overdue_eligible_task_statuses AND task.due_date IS NOT NULL AND date(task.due_date) < date($today) THEN task.uid END) as overdue_task_uids,
     collect(CASE WHEN task.due_date IS NOT NULL AND date(task.due_date) = date($today) THEN task.uid END) as today_task_uids

// Habits - parallel collection with metrics
OPTIONAL MATCH (user)-[:OWNS]->(habit:Habit)
WHERE habit.status = $status_active
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     collect(habit.uid) as active_habit_uids,
     collect({uid: habit.uid, streak: coalesce(habit.current_streak, 0), rate: coalesce(habit.completion_rate, 0.0)}) as habit_data

// Goals - parallel collection with status and progress
OPTIONAL MATCH (user)-[:OWNS]->(goal:Goal)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     active_habit_uids, habit_data,
     collect(CASE WHEN goal.status = $status_active THEN goal.uid END) as active_goal_uids,
     collect(CASE WHEN goal.status = $status_completed THEN goal.uid END) as completed_goal_uids,
     collect({uid: goal.uid, progress: coalesce(goal.progress, 0.0)}) as goal_data

// Knowledge - parallel collection with mastery scores
OPTIONAL MATCH (user)-[mastered:MASTERED]->(ku:Entity)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     active_habit_uids, habit_data,
     active_goal_uids, completed_goal_uids, goal_data,
     collect({uid: ku.uid, score: coalesce(mastered.mastery_score, 1.0)}) as knowledge_data

// KU Tracking - view counts, time spent, marked as read, bookmarked (Phase B)
OPTIONAL MATCH (user)-[viewed:VIEWED]->(viewed_ku:Entity)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     active_habit_uids, habit_data,
     active_goal_uids, completed_goal_uids, goal_data,
     knowledge_data,
     collect({uid: viewed_ku.uid, view_count: coalesce(viewed.view_count, 1), time_spent_seconds: coalesce(viewed.time_spent_seconds, 0), last_viewed_at: viewed.last_viewed_at}) as ku_view_data

OPTIONAL MATCH (user)-[:MARKED_AS_READ]->(read_ku:Entity)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     active_habit_uids, habit_data,
     active_goal_uids, completed_goal_uids, goal_data,
     knowledge_data,
     ku_view_data,
     collect(read_ku.uid) as ku_marked_as_read_uids

OPTIONAL MATCH (user)-[:BOOKMARKED]->(bookmarked_ku:Entity)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     active_habit_uids, habit_data,
     active_goal_uids, completed_goal_uids, goal_data,
     knowledge_data,
     ku_view_data, ku_marked_as_read_uids,
     collect(bookmarked_ku.uid) as ku_bookmarked_uids

// Learning Paths - parallel collection
OPTIONAL MATCH (user)-[:ENROLLED_IN]->(lp:LearningPath)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     active_habit_uids, habit_data,
     active_goal_uids, completed_goal_uids, goal_data,
     knowledge_data,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     collect(lp.uid) as enrolled_path_uids

// MOCs - emergent identity (any Entity with ORGANIZES relationships)
OPTIONAL MATCH (user)-[:OWNS]->(moc:Entity)-[:ORGANIZES]->(:Entity)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     active_habit_uids, habit_data,
     active_goal_uids, completed_goal_uids, goal_data,
     knowledge_data,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     enrolled_path_uids,
     collect(DISTINCT moc.uid) as active_moc_uids,
     collect(DISTINCT {uid: moc.uid, updated: moc.updated_at}) as moc_data

// Events - parallel collection with date filtering
OPTIONAL MATCH (user)-[:OWNS]->(event:Event)
WHERE date(event.event_date) >= date($today)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     active_habit_uids, habit_data,
     active_goal_uids, completed_goal_uids, goal_data,
     knowledge_data,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     enrolled_path_uids,
     active_moc_uids, moc_data,
     collect(event.uid) as upcoming_event_uids,
     collect(CASE WHEN date(event.event_date) = date($today) THEN event.uid END) as today_event_uids

// Principles - active principles guide daily decisions
OPTIONAL MATCH (user)-[:OWNS]->(principle:Principle)
WHERE principle.status = $status_active
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     active_habit_uids, habit_data,
     active_goal_uids, completed_goal_uids, goal_data,
     knowledge_data,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     enrolled_path_uids,
     active_moc_uids, moc_data,
     upcoming_event_uids, today_event_uids,
     collect(principle.uid) as core_principle_uids

// Choices - pending decisions block forward motion
OPTIONAL MATCH (user)-[:OWNS]->(choice:Choice)
WHERE choice.status IN $pending_choice_statuses
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     active_habit_uids, habit_data,
     active_goal_uids, completed_goal_uids, goal_data,
     knowledge_data,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     enrolled_path_uids,
     active_moc_uids, moc_data,
     upcoming_event_uids, today_event_uids,
     core_principle_uids,
     collect(choice.uid) as pending_choice_uids

// ACTIVITY REPORT - Latest report for standard context
OPTIONAL MATCH (user)-[:OWNS]->(ar:ActivityReport)
WITH active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     active_habit_uids, habit_data,
     active_goal_uids, completed_goal_uids, goal_data,
     knowledge_data,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     enrolled_path_uids,
     active_moc_uids, moc_data,
     upcoming_event_uids, today_event_uids,
     core_principle_uids, pending_choice_uids,
     ar
ORDER BY ar.period_end DESC
WITH active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     active_habit_uids, habit_data,
     active_goal_uids, completed_goal_uids, goal_data,
     knowledge_data,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     enrolled_path_uids,
     active_moc_uids, moc_data,
     upcoming_event_uids, today_event_uids,
     core_principle_uids, pending_choice_uids,
     collect(ar)[0] AS latest_ar

// Final aggregation - return all domain data
RETURN
    active_task_uids,
    completed_task_uids,
    overdue_task_uids,
    today_task_uids,
    active_habit_uids,
    habit_data,
    active_goal_uids,
    completed_goal_uids,
    goal_data,
    knowledge_data,
    ku_view_data,
    ku_marked_as_read_uids,
    ku_bookmarked_uids,
    enrolled_path_uids,
    active_moc_uids,
    moc_data,
    upcoming_event_uids,
    today_event_uids,
    core_principle_uids,
    pending_choice_uids,
    CASE WHEN latest_ar IS NOT NULL THEN {
        uid: latest_ar.uid,
        period: latest_ar.time_period,
        period_end: latest_ar.period_end,
        content: latest_ar.processed_content,
        user_annotation: latest_ar.user_annotation
    } ELSE null END AS latest_ar
"""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def empty_context_data() -> dict[str, Any]:
    """Return empty context data structure."""
    return {
        "tasks": {
            "active_uids": [],
            "completed_uids": set(),
            "overdue_uids": [],
            "today_uids": [],
        },
        "habits": {"active_uids": [], "habit_streaks": {}, "completion_rates": {}},
        "goals": {"active_uids": [], "completed_uids": set(), "goal_progress": {}},
        "knowledge": {
            "mastered_uids": set(),
            "enrolled_path_uids": [],
            "knowledge_mastery": {},
            "ku_view_counts": {},
            "recently_viewed_ku_uids": [],
            "ku_marked_as_read_uids": set(),
        },
        "events": {"upcoming_uids": [], "today_uids": []},
        "principles": {"core_uids": []},
        "choices": {"pending_uids": []},
        "mocs": {"active_uids": [], "recently_viewed_uids": []},
        "submission_stats": {
            "total_submission_count": 0,
            "total_journal_count": 0,
            "submissions_in_window": 0,
            "last_submission_date": None,
            "feedback_received_count": 0,
            "feedback_in_window": 0,
            "pending_feedback_count": 0,
            "assigned_exercise_count": 0,
            "completed_exercise_count": 0,
            "unsubmitted_exercises": [],
        },
    }


# =============================================================================
# QUERY EXECUTOR
# =============================================================================


class UserContextQueryExecutor:
    """
    Execute user context queries against Neo4j.

    Separated from context building for cleaner architecture.
    Contains only query execution logic, no result processing.
    """

    def __init__(self, executor: "QueryExecutor") -> None:
        """
        Initialize query executor.

        Args:
            executor: QueryExecutor for database queries

        Raises:
            ValueError: If executor is None
        """
        if not executor:
            raise ValueError("QueryExecutor is required for query execution")
        self.executor = executor

    @with_error_handling("execute_mega_query", error_type="database", uid_param="user_uid")
    async def execute_mega_query(
        self,
        user_uid: UserUID,
        min_confidence: float = 0.7,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Execute the MEGA-QUERY for complete user context.

        Returns both UIDs (standard) and rich data (entities + graph neighborhoods)
        in a single database round-trip.

        Always passes $window_start and $window_end parameters to the query.
        These control which completed/past entities are included in entities_rich
        alongside the always-present active entities.

        Args:
            user_uid: User identifier
            min_confidence: Minimum relationship confidence (default 0.7)
            window_start: Activity window start datetime (default: 30d ago)
            window_end: Activity window end datetime (default: now)

        Returns:
            Result containing dict with "uids", "entities", and "rich" keys
        """
        today = date.today().isoformat()

        # Always compute window bounds — default 30d lookback when not provided
        effective_end = window_end or datetime.now()
        effective_start = window_start or (effective_end - timedelta(days=30))

        params: dict[str, Any] = {
            "user_uid": user_uid,
            "today": today,
            "min_confidence": min_confidence,
            "window_start": effective_start.isoformat(),
            "window_end": effective_end.isoformat(),
            **STATUS_PARAMS,
        }

        result = await self.executor.execute_query(MEGA_QUERY, params)
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        record = records[0] if records else None

        if not record or not record["result"]:
            return Result.ok({"uids": {}, "entities": {}, "rich": {}})

        return Result.ok(record["result"])

    @with_error_handling("fetch_current_ps_uids", error_type="database", uid_param="user_uid")
    async def fetch_current_ps_uids(self, user_uid: UserUID) -> Result[list[str]]:
        """Fetch PathStep UIDs the user is actively studying."""
        result = await self.fetch_current_path_steps(user_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([item["uid"] for item in result.value])

    @with_error_handling("fetch_current_path_steps", error_type="database", uid_param="user_uid")
    async def fetch_current_path_steps(
        self, user_uid: UserUID
    ) -> Result[list[CurrentPathStepItem]]:
        """Fetch path steps the user is actively studying (IN_PROGRESS relationship)."""
        query = """
        MATCH (user:User {uid: $user_uid})-[:IN_PROGRESS]->(ps:Entity:PathStep)
        RETURN ps.uid as uid, ps.title as title
        ORDER BY ps.title
        """
        result = await self.executor.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        return Result.ok(
            [
                CurrentPathStepItem(uid=str(r["uid"]), title=str(r.get("title", "Untitled")))
                for r in records
            ]
        )

    @with_error_handling("fetch_user_groups", error_type="database", uid_param="user_uid")
    async def fetch_user_groups(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """
        Fetch group memberships, ownerships, and curriculum shared with the user's groups.

        Returns a dict with:
        - user_groups: groups the user is a MEMBER_OF (student role)
        - teacher_groups: groups the user OWNS (teacher role) with member counts
        - group_assigned_exercise_uids / group_assigned_path_step_uids /
          group_assigned_learning_path_uids: curriculum shared to any of the
          user's groups via SHARED_WITH_GROUP (ADR-053).
        """
        query = """
        MATCH (user:User {uid: $user_uid})
        OPTIONAL MATCH (user)-[:MEMBER_OF]->(mg:Group)
        WITH user, collect(DISTINCT {
            uid: mg.uid,
            name: coalesce(mg.name, 'Untitled Group'),
            role: 'student',
            member_count: 0,
            is_active: coalesce(mg.is_active, true)
        }) AS member_groups_raw
        OPTIONAL MATCH (user)-[:OWNS]->(og:Group)
        OPTIONAL MATCH (og)<-[:MEMBER_OF]-(member:User)
        WITH user, member_groups_raw, og,
             count(DISTINCT member) AS member_count
        WITH user, member_groups_raw,
             collect(DISTINCT CASE WHEN og IS NOT NULL THEN {
                 uid: og.uid,
                 name: coalesce(og.name, 'Untitled Group'),
                 role: 'owner',
                 member_count: member_count,
                 is_active: coalesce(og.is_active, true)
             } END) AS teacher_groups_raw
        OPTIONAL MATCH (user)-[:MEMBER_OF|OWNS]->(g:Group)<-[:SHARED_WITH_GROUP]-(ex:Entity {entity_type: 'exercise'})
        WITH user, member_groups_raw, teacher_groups_raw,
             collect(DISTINCT ex.uid) AS exercise_uids
        OPTIONAL MATCH (user)-[:MEMBER_OF|OWNS]->(g2:Group)<-[:SHARED_WITH_GROUP]-(ps:Entity {entity_type: 'path_step'})
        WITH user, member_groups_raw, teacher_groups_raw, exercise_uids,
             collect(DISTINCT ps.uid) AS path_step_uids
        OPTIONAL MATCH (user)-[:MEMBER_OF|OWNS]->(g3:Group)<-[:SHARED_WITH_GROUP]-(lp:Entity {entity_type: 'learning_path'})
        RETURN
            [x IN member_groups_raw WHERE x.uid IS NOT NULL] AS user_groups,
            [x IN teacher_groups_raw WHERE x IS NOT NULL AND x.uid IS NOT NULL] AS teacher_groups,
            exercise_uids AS group_assigned_exercise_uids,
            path_step_uids AS group_assigned_path_step_uids,
            collect(DISTINCT lp.uid) AS group_assigned_learning_path_uids
        """
        result = await self.executor.execute_query(query, {"user_uid": user_uid})
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(
                {
                    "user_groups": [],
                    "teacher_groups": [],
                    "group_assigned_exercise_uids": [],
                    "group_assigned_path_step_uids": [],
                    "group_assigned_learning_path_uids": [],
                }
            )
        record = records[0]
        return Result.ok(
            {
                "user_groups": [
                    GroupSummary(
                        uid=str(g["uid"]),
                        name=str(g.get("name", "Untitled Group")),
                        role=str(g.get("role", "student")),
                        member_count=int(g.get("member_count") or 0),
                        is_active=bool(g.get("is_active", True)),
                    )
                    for g in (record.get("user_groups") or [])
                ],
                "teacher_groups": [
                    GroupSummary(
                        uid=str(g["uid"]),
                        name=str(g.get("name", "Untitled Group")),
                        role=str(g.get("role", "owner")),
                        member_count=int(g.get("member_count") or 0),
                        is_active=bool(g.get("is_active", True)),
                    )
                    for g in (record.get("teacher_groups") or [])
                ],
                "group_assigned_exercise_uids": [
                    str(u) for u in (record.get("group_assigned_exercise_uids") or []) if u
                ],
                "group_assigned_path_step_uids": [
                    str(u) for u in (record.get("group_assigned_path_step_uids") or []) if u
                ],
                "group_assigned_learning_path_uids": [
                    str(u) for u in (record.get("group_assigned_learning_path_uids") or []) if u
                ],
            }
        )

    @with_error_handling("execute_consolidated_query", error_type="database", uid_param="user_uid")
    async def execute_consolidated_query(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """
        Execute the consolidated query for standard context (UIDs only).

        This is the simpler query path, without rich entity data.

        Args:
            user_uid: User identifier

        Returns:
            Result containing structured domain data
        """
        today = date.today().isoformat()
        params = {"user_uid": user_uid, "today": today, **STATUS_PARAMS}

        result = await self.executor.execute_query(CONSOLIDATED_QUERY, params)
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        record = records[0] if records else None

        if not record:
            return Result.ok(empty_context_data())

        # Extract and structure all domain data
        return Result.ok(
            {
                "tasks": {
                    "active_uids": [uid for uid in (record["active_task_uids"] or []) if uid],
                    "completed_uids": {uid for uid in (record["completed_task_uids"] or []) if uid},
                    "overdue_uids": [uid for uid in (record["overdue_task_uids"] or []) if uid],
                    "today_uids": [uid for uid in (record["today_task_uids"] or []) if uid],
                },
                "habits": {
                    "active_uids": [uid for uid in (record["active_habit_uids"] or []) if uid],
                    "habit_streaks": {
                        item["uid"]: item["streak"]
                        for item in (record["habit_data"] or [])
                        if item and item.get("uid") is not None
                    },
                    "completion_rates": {
                        item["uid"]: item["rate"]
                        for item in (record["habit_data"] or [])
                        if item and item.get("uid") is not None
                    },
                },
                "goals": {
                    "active_uids": [uid for uid in (record["active_goal_uids"] or []) if uid],
                    "completed_uids": {uid for uid in (record["completed_goal_uids"] or []) if uid},
                    "goal_progress": {
                        item["uid"]: item["progress"]
                        for item in (record["goal_data"] or [])
                        if item and item.get("uid") is not None
                    },
                },
                "knowledge": {
                    "mastered_uids": {
                        item["uid"]
                        for item in (record["knowledge_data"] or [])
                        if item and item.get("uid") is not None
                    },
                    "enrolled_path_uids": [
                        uid for uid in (record["enrolled_path_uids"] or []) if uid
                    ],
                    "knowledge_mastery": {
                        item["uid"]: item["score"]
                        for item in (record["knowledge_data"] or [])
                        if item and item.get("uid") is not None
                    },
                    "ku_view_counts": {
                        item["uid"]: item["view_count"]
                        for item in (record["ku_view_data"] or [])
                        if item and item.get("uid") is not None
                    },
                    "recently_viewed_ku_uids": [
                        item["uid"]
                        for item in sorted(
                            [
                                i
                                for i in (record["ku_view_data"] or [])
                                if i and i.get("uid") and i.get("last_viewed_at")
                            ],
                            key=_sort_by_last_viewed_at,
                            reverse=True,
                        )
                    ][:10],
                    "ku_marked_as_read_uids": {
                        uid for uid in (record["ku_marked_as_read_uids"] or []) if uid
                    },
                    "ku_bookmarked_uids": {
                        uid for uid in (record["ku_bookmarked_uids"] or []) if uid
                    },
                    "ku_time_spent_seconds": {
                        item["uid"]: item.get("time_spent_seconds", 0)
                        for item in (record["ku_view_data"] or [])
                        if item and item.get("uid") is not None
                    },
                },
                "events": {
                    "upcoming_uids": record["upcoming_event_uids"] or [],
                    "today_uids": [uid for uid in (record["today_event_uids"] or []) if uid],
                },
                "principles": {
                    "core_uids": [uid for uid in (record["core_principle_uids"] or []) if uid],
                },
                "choices": {
                    "pending_uids": [uid for uid in (record["pending_choice_uids"] or []) if uid],
                },
                "mocs": {
                    "active_uids": [uid for uid in (record["active_moc_uids"] or []) if uid],
                    "recently_viewed_uids": [
                        item["uid"]
                        for item in sorted(
                            [i for i in (record["moc_data"] or []) if i and i.get("uid")],
                            key=get_updated_timestamp,
                            reverse=True,
                        )[:10]
                    ],
                },
                "activity_report": record.get("latest_ar"),
            }
        )
