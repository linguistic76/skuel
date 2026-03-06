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
     collect(CASE WHEN task.status IN ['draft', 'scheduled', 'active', 'blocked'] THEN task.uid END) as active_task_uids,
     collect(CASE WHEN task.status = 'completed' THEN task.uid END) as completed_task_uids,
     collect(CASE WHEN task.status IN ['draft', 'scheduled', 'active'] AND task.due_date IS NOT NULL AND date(task.due_date) < date($today) THEN task.uid END) as overdue_task_uids,
     collect(CASE WHEN task.due_date IS NOT NULL AND date(task.due_date) = date($today) THEN task.uid END) as today_task_uids,
     collect(task) as all_tasks_nodes

// Filter tasks for rich data — active status always included; window entities included if touched since $window_start
UNWIND CASE WHEN size(all_tasks_nodes) > 0 THEN all_tasks_nodes ELSE [null] END as task
OPTIONAL MATCH (task)-[:HAS_SUBTASK]->(subtask:Task)
WHERE task IS NOT NULL AND (task.status IN ['draft', 'scheduled', 'active', 'blocked'] OR task.updated_at >= datetime($window_start))
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     task, collect(DISTINCT {uid: subtask.uid, title: subtask.title, status: subtask.status}) as task_subtasks

OPTIONAL MATCH (task)-[dep_rel:DEPENDS_ON]->(dependency:Task)
WHERE task IS NOT NULL AND coalesce(dep_rel.confidence, 1.0) >= $min_confidence
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     task, task_subtasks,
     collect(DISTINCT {uid: dependency.uid, title: dependency.title, confidence: dep_rel.confidence}) as task_dependencies

OPTIONAL MATCH (task)-[app_rel:APPLIES_KNOWLEDGE]->(ku:Entity)
WHERE task IS NOT NULL AND coalesce(app_rel.confidence, 1.0) >= $min_confidence
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     task, task_subtasks, task_dependencies,
     collect(DISTINCT {uid: ku.uid, title: ku.title, confidence: app_rel.confidence}) as task_knowledge

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
     collect(CASE WHEN goal.status = 'active' THEN goal.uid END) as active_goal_uids,
     collect(CASE WHEN goal.status = 'completed' THEN goal.uid END) as completed_goal_uids,
     collect({uid: goal.uid, progress: coalesce(goal.progress, 0.0)}) as goal_progress_data,
     collect(goal) as all_goals_nodes

// Filter goals for rich data — active status always included; window entities included if touched since $window_start
UNWIND CASE WHEN size(all_goals_nodes) > 0 THEN all_goals_nodes ELSE [null] END as goal
OPTIONAL MATCH (contributing_task:Task)-[:FULFILLS_GOAL]->(goal)
WHERE goal IS NOT NULL AND (goal.status = 'active' OR goal.updated_at >= datetime($window_start))
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
OPTIONAL MATCH (user)-[mastered:MASTERED|LEARNING]->(ku:Entity)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     collect({
         uid: ku.uid,
         score: coalesce(mastered.mastery_score, CASE WHEN type(mastered) = 'MASTERED' THEN 1.0 ELSE 0.5 END),
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
WHERE habit.status = 'active' OR habit.updated_at >= datetime($window_start)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     collect(CASE WHEN habit.status = 'active' THEN habit.uid END) as active_habit_uids,
     collect(CASE WHEN habit.status = 'active' THEN {uid: habit.uid, streak: coalesce(habit.current_streak, 0), rate: coalesce(habit.completion_rate, 0.0)} END) as habit_metadata,
     collect(habit) as all_habit_nodes

// Filter habits for rich data (with graph neighborhoods)
UNWIND CASE WHEN size(all_habit_nodes) > 0 THEN all_habit_nodes ELSE [null] END as habit
OPTIONAL MATCH (habit)-[:FULFILLS_GOAL|SUPPORTS_GOAL|CONTRIBUTES_TO]->(linked_goal:Goal)
WHERE habit IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata,
     habit, collect(DISTINCT {uid: linked_goal.uid, title: linked_goal.title, status: linked_goal.status}) as habit_linked_goals

OPTIONAL MATCH (habit)-[:APPLIES_KNOWLEDGE|REINFORCES_KNOWLEDGE]->(habit_ku:Entity)
WHERE habit IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata,
     habit, habit_linked_goals,
     collect(DISTINCT {uid: habit_ku.uid, title: habit_ku.title}) as habit_applied_knowledge

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
WHERE event.event_date >= date(datetime($window_start))
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     collect(CASE WHEN event.event_date >= date($today) THEN event.uid END) as upcoming_event_uids,
     collect(CASE WHEN date(event.event_date) = date($today) THEN event.uid END) as today_event_uids,
     collect(event) as all_event_nodes

// Filter events for rich data (with graph neighborhoods)
UNWIND CASE WHEN size(all_event_nodes) > 0 THEN all_event_nodes ELSE [null] END as event
OPTIONAL MATCH (event)-[:APPLIES_KNOWLEDGE]->(event_ku:Entity)
WHERE event IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids,
     event, collect(DISTINCT {uid: event_ku.uid, title: event_ku.title})[0..10] as event_applied_knowledge

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
             conflicting_events: event_conflicting_events
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
OPTIONAL MATCH (principle)-[:GROUNDED_IN_KNOWLEDGE]->(principle_ku:Entity)
WHERE principle IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids,
     principle, collect(DISTINCT {uid: principle_ku.uid, title: principle_ku.title})[0..10] as principle_grounded_knowledge

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
WHERE choice.status IN ['draft', 'active'] OR choice.created_at >= datetime($window_start)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     collect(CASE WHEN choice.status IN ['draft', 'active'] THEN choice.uid END) as pending_choice_uids,
     collect(choice) as all_choice_nodes

// Filter choices for rich data (with graph neighborhoods)
UNWIND CASE WHEN size(all_choice_nodes) > 0 THEN all_choice_nodes ELSE [null] END as choice
OPTIONAL MATCH (choice)-[:INFORMED_BY_KNOWLEDGE]->(choice_ku:Entity)
WHERE choice IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids,
     choice, collect(DISTINCT {uid: choice_ku.uid, title: choice_ku.title})[0..10] as choice_informing_knowledge

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
OPTIONAL MATCH (lp)-[r_step:HAS_STEP|CONTAINS_STEP]->(step:LearningStep)
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
// LEARNING STEPS - Fetch active steps with rich data
// ====================================================================
OPTIONAL MATCH (user)-[:WORKING_ON|ENROLLED_IN]->(ls:LearningStep)
WHERE ls.status IN ['draft', 'active']
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     collect(ls) as all_ls_nodes

// Filter learning steps for rich data (with graph neighborhoods)
UNWIND CASE WHEN size(all_ls_nodes) > 0 THEN all_ls_nodes ELSE [null] END as ls
OPTIONAL MATCH (ls)-[:REQUIRES_STEP]->(prereq_step:LearningStep)
WHERE ls IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     ls, collect(DISTINCT {uid: prereq_step.uid, title: prereq_step.title, completed: prereq_step.completed}) as ls_prereq_steps

OPTIONAL MATCH (ls)-[:BUILDS_HABIT]->(ls_habit:Habit)
WHERE ls IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     ls, ls_prereq_steps,
     collect(DISTINCT {uid: ls_habit.uid, title: ls_habit.title}) as ls_habits

OPTIONAL MATCH (ls)-[:ASSIGNS_TASK]->(ls_task:Task)
WHERE ls IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     ls, ls_prereq_steps, ls_habits,
     collect(DISTINCT {uid: ls_task.uid, title: ls_task.title, status: ls_task.status}) as ls_tasks

OPTIONAL MATCH (ls)-[:REQUIRES_KNOWLEDGE|TEACHES]->(ls_ku:Entity)
WHERE ls IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     ls, ls_prereq_steps, ls_habits, ls_tasks,
     collect(DISTINCT {uid: ls_ku.uid, title: ls_ku.title, domain: ls_ku.domain}) as ls_knowledge

OPTIONAL MATCH (lp_parent:LearningPath)-[:CONTAINS_STEP]->(ls)
WHERE ls IS NOT NULL
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids, tasks_rich,
     active_goal_uids, completed_goal_uids, goal_progress_data, goals_rich,
     knowledge_mastery_data, knowledge_rich,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     active_habit_uids, habit_metadata, habits_rich,
     upcoming_event_uids, today_event_uids, events_rich,
     core_principle_uids, principles_rich,
     pending_choice_uids, choices_rich,
     enrolled_path_uids, paths_rich,
     collect(CASE WHEN ls IS NOT NULL THEN {
         step: properties(ls),
         graph_context: {
             prerequisite_steps: ls_prereq_steps,
             practice_habits: ls_habits,
             practice_tasks: ls_tasks,
             knowledge_relationships: ls_knowledge,
             learning_path: CASE WHEN lp_parent IS NOT NULL
                 THEN {uid: lp_parent.uid, name: lp_parent.name}
                 ELSE null END,
             total_prerequisites: size(ls_prereq_steps),
             total_practice_opportunities: size(ls_habits) + size(ls_tasks),
             is_sequenced: lp_parent IS NOT NULL
         }
     } END) as steps_rich

// ====================================================================
// LIFE PATH - Fetch user's designated life path
// ====================================================================
OPTIONAL MATCH (user)-[lp_rel:ULTIMATE_PATH]->(life_path:LifePath)
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
     user.life_path_alignment_score AS life_path_alignment_score

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
     collect(DISTINCT {uid: moc.uid, view_count: coalesce(moc.view_count, 0), updated: moc.updated_at}) as moc_metadata

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
    AND (ins.expires_at IS NULL OR ins.expires_at > datetime())
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
WHERE sub.entity_type IN ['submission', 'journal']
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
     count(CASE WHEN sub.entity_type = 'submission' THEN 1 END) AS total_submission_count,
     count(CASE WHEN sub.entity_type = 'journal' THEN 1 END) AS total_journal_count,
     count(CASE WHEN sub.created_at >= datetime($window_start) THEN 1 END) AS submissions_in_window,
     max(sub.created_at) AS last_submission_date,
     collect(sub.uid) AS all_submission_uids

// Feedback received for user's submissions
OPTIONAL MATCH (user)-[:OWNS]->(owned_sub:Entity)<-[:FEEDBACK_FOR]-(fb:Entity)
WHERE owned_sub.entity_type IN ['submission', 'journal']
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
     count(CASE WHEN fb.created_at >= datetime($window_start) THEN 1 END) AS feedback_in_window,
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
OPTIONAL MATCH (user)-[:MEMBER_OF]->(grp:Group)<-[:FOR_GROUP]-(ex:Entity {entity_type: 'exercise', scope: 'assigned'})
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
        learning_steps: [item IN steps_rich WHERE item.step IS NOT NULL | {entity: item.step, graph_context: item.graph_context}]
    },
    rich: {
        knowledge: knowledge_rich,
        learning_paths: [item IN paths_rich WHERE item.path IS NOT NULL],
        learning_steps: [item IN steps_rich WHERE item.step IS NOT NULL]
    },
    user_properties: {
        learning_level: user.learning_level,
        preferred_time: user.preferred_time_of_day,
        energy_level: user.energy_level,
        available_minutes: user.available_minutes_daily,
        preferred_personality: user.preferred_personality,
        preferred_tone: user.preferred_tone,
        preferred_guidance: user.preferred_guidance
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
        unsubmitted_exercises: unsubmitted_exercises
    }
} as result
"""


CONSOLIDATED_QUERY: str = """
// Start with user node
MATCH (user:User {uid: $user_uid})

// Tasks - parallel collection with conditional aggregation
OPTIONAL MATCH (user)-[:OWNS]->(task:Task)
WITH user,
     collect(CASE WHEN task.status IN ['draft', 'scheduled', 'active', 'blocked'] THEN task.uid END) as active_task_uids,
     collect(CASE WHEN task.status = 'completed' THEN task.uid END) as completed_task_uids,
     collect(CASE WHEN task.status IN ['draft', 'scheduled', 'active'] AND task.due_date IS NOT NULL AND date(task.due_date) < date($today) THEN task.uid END) as overdue_task_uids,
     collect(CASE WHEN task.due_date IS NOT NULL AND date(task.due_date) = date($today) THEN task.uid END) as today_task_uids

// Habits - parallel collection with metrics
OPTIONAL MATCH (user)-[:OWNS]->(habit:Habit)
WHERE habit.status = 'active'
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     collect(habit.uid) as active_habit_uids,
     collect({uid: habit.uid, streak: coalesce(habit.current_streak, 0), rate: coalesce(habit.completion_rate, 0.0)}) as habit_data

// Goals - parallel collection with status and progress
OPTIONAL MATCH (user)-[:OWNS]->(goal:Goal)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     active_habit_uids, habit_data,
     collect(CASE WHEN goal.status = 'active' THEN goal.uid END) as active_goal_uids,
     collect(CASE WHEN goal.status = 'completed' THEN goal.uid END) as completed_goal_uids,
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
     collect(DISTINCT {uid: moc.uid, view_count: coalesce(moc.view_count, 0), updated: moc.updated_at}) as moc_data

// Events - parallel collection with date filtering
OPTIONAL MATCH (user)-[:OWNS]->(event:Event)
WHERE event.event_date >= date($today)
WITH user, active_task_uids, completed_task_uids, overdue_task_uids, today_task_uids,
     active_habit_uids, habit_data,
     active_goal_uids, completed_goal_uids, goal_data,
     knowledge_data,
     ku_view_data, ku_marked_as_read_uids, ku_bookmarked_uids,
     enrolled_path_uids,
     active_moc_uids, moc_data,
     collect(event.uid) as upcoming_event_uids,
     collect(CASE WHEN date(event.event_date) = date($today) THEN event.uid END) as today_event_uids

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
        "mocs": {"active_uids": [], "view_counts": {}, "recently_viewed_uids": []},
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
        user_uid: str,
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
        }

        result = await self.executor.execute_query(MEGA_QUERY, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        record = records[0] if records else None

        if not record or not record["result"]:
            return Result.ok({"uids": {}, "entities": {}, "rich": {}})

        return Result.ok(record["result"])

    @with_error_handling("execute_consolidated_query", error_type="database", uid_param="user_uid")
    async def execute_consolidated_query(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Execute the consolidated query for standard context (UIDs only).

        This is the simpler query path, without rich entity data.

        Args:
            user_uid: User identifier

        Returns:
            Result containing structured domain data
        """
        today = date.today().isoformat()
        params = {"user_uid": user_uid, "today": today}

        result = await self.executor.execute_query(CONSOLIDATED_QUERY, params)
        if result.is_error:
            return Result.fail(result.expect_error())

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
                "mocs": {
                    "active_uids": [uid for uid in (record["active_moc_uids"] or []) if uid],
                    "view_counts": {
                        item["uid"]: item["view_count"]
                        for item in (record["moc_data"] or [])
                        if item and item.get("uid") is not None
                    },
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
