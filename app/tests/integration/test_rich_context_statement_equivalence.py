"""
The six rich-context statements, merged, read every section of a learner's graph.

``RICH_CONTEXT_STATEMENTS`` carries each read family in a statement of its own,
and each statement's ``WITH`` lists carry only its own names. That is where a
field goes quietly wrong: a name dropped from a carry list is a Cypher error
(good), but a name that survives with the wrong content is not. So this seeds a
learner with at least one node in EVERY section — a task with a subtask, a
dependency and applied knowledge (direct and through a PathStep), a goal with a
subgoal, a mastered and an in-progress Ku, a viewed / read / bookmarked Ku, a
habit with a prerequisite, an event with a conflict, a principle, a choice, an
enrolled path with an in-progress step, a life path, an organizer, two activity
reports, a live and a dismissed insight — and pins every field group of the
merged map and of the built context. The pinned values are the contract; the
measurement behind the split and the record of how they were captured is
``docs/roadmap/done/mega-query-plan-cache-cliff.md``.

Two of the pinned values are quirks, kept deliberately: a ``PathStep`` the user
is ``IN_PROGRESS`` on is matched by the knowledge section's
``MASTERED|IN_PROGRESS`` alternation and lands in ``knowledge_mastery`` at the
0.1 default, and a ``REQUIRES_KNOWLEDGE`` edge without a ``confidence`` projects
``null``. Changing either is a decision, not a regression, and re-pins here.

Two invariants have a test of their own below: a learner whose every insight is
dismissed, actioned or expired keeps the rest of the context (the insight
predicate is on the ``OPTIONAL MATCH``, not a row filter after the grouped
``WITH``), and a goal with milestones builds (``Goal.milestones`` is a JSON
string on the node, which no Cypher projection iterates).
"""

import json
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from neo4j import AsyncDriver

from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.user_context_queries import UserContextQueryExecutor
from core.models.type_hints import UserUID
from core.models.user.user import User
from core.services.user.user_context_builder import UserContextBuilder

_USER_UID = UserUID("user_test")
_SEEDED_AT = datetime(2026, 9, 13, 12, 0, 0)

_SEED = """
MATCH (u:User {uid: $user_uid})
// knowledge
CREATE (ku_a:Entity:Ku {uid: 'ku.eq.a', entity_type: 'ku', title: 'Ku A', domain: 'sel'})
CREATE (ku_b:Entity:Ku {uid: 'ku.eq.b', entity_type: 'ku', title: 'Ku B'})
CREATE (ku_c:Entity:Ku {uid: 'ku.eq.c', entity_type: 'ku', title: 'Ku C'})
CREATE (ku_pre:Entity:Ku {uid: 'ku.eq.pre', entity_type: 'ku', title: 'Ku Pre'})
CREATE (ku_dep:Entity:Ku {uid: 'ku.eq.dep', entity_type: 'ku', title: 'Ku Dep'})
CREATE (u)-[:MASTERED {mastery_score: 0.9, mastered_at: $iso, confidence: 0.8}]->(ku_a)
CREATE (u)-[:IN_PROGRESS {progress: 0.4}]->(ku_b)
CREATE (ku_a)-[:REQUIRES_KNOWLEDGE {confidence: 0.9}]->(ku_pre)
CREATE (ku_dep)-[:REQUIRES_KNOWLEDGE {confidence: 0.75}]->(ku_a)
CREATE (u)-[:VIEWED {view_count: 3, time_spent_seconds: 120, last_viewed_at: $iso}]->(ku_a)
CREATE (u)-[:MARKED_AS_READ]->(ku_a)
CREATE (u)-[:BOOKMARKED]->(ku_b)
// curriculum
CREATE (lp:Entity:LearningPath {uid: 'lp.eq.path', entity_type: 'learning_path', title: 'Path'})
CREATE (ps0:Entity:PathStep {uid: 'ps.eq.zero', entity_type: 'path_step', title: 'Step 0', completed: true})
CREATE (ps1:Entity:PathStep {uid: 'ps.eq.one', entity_type: 'path_step', title: 'Step 1', completed: false})
CREATE (ps2:Entity:PathStep {uid: 'ps.eq.two', entity_type: 'path_step', title: 'Step 2', completed: true})
CREATE (u)-[:ENROLLED_IN]->(lp)
CREATE (lp)-[:HAS_STEP {sequence: 1}]->(ps1)
CREATE (lp)-[:HAS_STEP {sequence: 2}]->(ps2)
CREATE (lp)-[:REQUIRES_KNOWLEDGE]->(ku_pre)
CREATE (u)-[:IN_PROGRESS]->(ps1)
CREATE (ps1)-[:REQUIRES_STEP]->(ps0)
CREATE (ps1)-[:USES_KU]->(ku_c)
CREATE (ps1)-[:REQUIRES_KNOWLEDGE]->(ku_pre)
// tasks
CREATE (t_open:Entity:Task {uid: 'task.eq.open', entity_type: 'task', title: 'Open task', status: 'active',
                            due_date: $today, updated_at: $iso, user_uid: $user_uid})
CREATE (t_sub:Entity:Task {uid: 'task.eq.sub', entity_type: 'task', title: 'Done subtask', status: 'completed',
                           updated_at: $old, user_uid: $user_uid})
CREATE (t_dep:Entity:Task {uid: 'task.eq.dep', entity_type: 'task', title: 'Blocking task', status: 'scheduled',
                           due_date: $yesterday, updated_at: $iso, user_uid: $user_uid})
CREATE (u)-[:OWNS]->(t_open) CREATE (u)-[:OWNS]->(t_sub) CREATE (u)-[:OWNS]->(t_dep)
CREATE (t_open)-[:HAS_SUBTASK]->(t_sub)
CREATE (t_open)-[:DEPENDS_ON {confidence: 0.9}]->(t_dep)
CREATE (t_open)-[:APPLIES_KNOWLEDGE {confidence: 0.95}]->(ku_a)
CREATE (t_open)-[:APPLIES_KNOWLEDGE {confidence: 0.3}]->(ku_b)
CREATE (t_open)-[:APPLIES_KNOWLEDGE]->(ps1)
// goals
CREATE (g_active:Entity:Goal {uid: 'goal.eq.active', entity_type: 'goal', title: 'Active goal', status: 'active',
                              progress_percentage: 40.0, updated_at: $iso, user_uid: $user_uid})
CREATE (g_done:Entity:Goal {uid: 'goal.eq.done', entity_type: 'goal', title: 'Done goal', status: 'completed',
                            progress_percentage: 100.0, updated_at: $old, user_uid: $user_uid})
CREATE (u)-[:OWNS]->(g_active) CREATE (u)-[:OWNS]->(g_done)
CREATE (t_open)-[:FULFILLS_GOAL]->(g_active)
CREATE (g_active)-[:HAS_SUBGOAL]->(g_done)
CREATE (g_active)-[:REQUIRES_KNOWLEDGE {confidence: 0.8}]->(ku_a)
// habits
CREATE (h_active:Entity:Habit {uid: 'habit.eq.active', entity_type: 'habit', title: 'Active habit', status: 'active',
                               current_streak: 5, completion_rate: 0.8, updated_at: $iso, user_uid: $user_uid})
CREATE (h_pre:Entity:Habit {uid: 'habit.eq.pre', entity_type: 'habit', title: 'Prereq habit', status: 'active',
                            updated_at: $iso, user_uid: $user_uid})
CREATE (h_old:Entity:Habit {uid: 'habit.eq.old', entity_type: 'habit', title: 'Old habit', status: 'completed',
                            updated_at: $old, user_uid: $user_uid})
CREATE (h_other:Entity:Habit {uid: 'habit.eq.other', entity_type: 'habit', title: 'Other user habit',
                              status: 'active', updated_at: $iso, user_uid: 'user_other'})
CREATE (u)-[:OWNS]->(h_active) CREATE (u)-[:OWNS]->(h_pre) CREATE (u)-[:OWNS]->(h_old)
CREATE (h_active)-[:SUPPORTS_GOAL]->(g_active)
CREATE (h_active)-[:REINFORCES_KNOWLEDGE]->(ku_a)
CREATE (h_active)-[:APPLIES_KNOWLEDGE]->(ps1)
CREATE (h_pre)-[:ENABLES_HABIT]->(h_active)
CREATE (h_active)-[:REQUIRES_PREREQUISITE_HABIT]->(h_pre)
CREATE (ps1)-[:BUILDS_HABIT]->(h_active)
CREATE (ps1)-[:BUILDS_HABIT]->(h_other)
CREATE (ps1)-[:ASSIGNS_TASK]->(t_open)
// events
CREATE (e_today:Entity:Event {uid: 'event.eq.today', entity_type: 'event', title: 'Today event', event_date: $today,
                              updated_at: $iso, user_uid: $user_uid})
CREATE (e_next:Entity:Event {uid: 'event.eq.next', entity_type: 'event', title: 'Tomorrow event',
                             event_date: $tomorrow, updated_at: $iso, user_uid: $user_uid})
CREATE (e_past:Entity:Event {uid: 'event.eq.past', entity_type: 'event', title: 'Past event', event_date: $old_date,
                             updated_at: $old, user_uid: $user_uid})
CREATE (u)-[:OWNS]->(e_today) CREATE (u)-[:OWNS]->(e_next) CREATE (u)-[:OWNS]->(e_past)
CREATE (e_today)-[:APPLIES_KNOWLEDGE]->(ku_a)
CREATE (e_today)-[:CONTRIBUTES_TO_GOAL]->(g_active)
CREATE (h_active)-[:PRACTICED_AT_EVENT]->(e_today)
CREATE (e_today)-[:CONFLICTS_WITH]->(e_next)
CREATE (e_today)-[:REINFORCES_HABIT]->(h_active)
// principles
CREATE (p:Entity:Principle {uid: 'principle.eq.core', entity_type: 'principle', title: 'Core principle',
                            status: 'active', user_uid: $user_uid})
CREATE (u)-[:OWNS]->(p)
CREATE (p)-[:GROUNDED_IN_KNOWLEDGE]->(ku_a)
CREATE (p)-[:GUIDES_GOAL]->(g_active)
CREATE (h_active)-[:EMBODIES_PRINCIPLE]->(p)
CREATE (t_open)-[:ALIGNED_WITH_PRINCIPLE]->(p)
CREATE (lp)-[:ALIGNED_WITH_GOAL]->(g_active)
CREATE (lp)-[:EMBODIES_PRINCIPLE]->(p)
// choices
CREATE (c:Entity:Choice {uid: 'choice.eq.pending', entity_type: 'choice', title: 'Pending choice', status: 'draft',
                         created_at: $iso, user_uid: $user_uid})
CREATE (c_old:Entity:Choice {uid: 'choice.eq.old', entity_type: 'choice', title: 'Old choice', status: 'completed',
                             created_at: $old, decided_at: $old, user_uid: $user_uid})
CREATE (u)-[:OWNS]->(c) CREATE (u)-[:OWNS]->(c_old)
CREATE (p)-[:GUIDES_CHOICE]->(c)
CREATE (c)-[:INFORMED_BY_KNOWLEDGE]->(ku_a)
CREATE (c)-[:INFORMED_BY_PRINCIPLE]->(p)
CREATE (c)-[:AFFECTS_GOAL]->(g_active)
CREATE (c)-[:OPENS_LEARNING_PATH]->(lp)
CREATE (t_dep)-[:IMPLEMENTS_CHOICE]->(c)
// life path, organizer, activity reports, insights
CREATE (life:Entity:LearningPath {uid: 'lp.eq.life', entity_type: 'learning_path', title: 'Life path'})
CREATE (u)-[:ULTIMATE_PATH {designated_at: $iso, alignment_score: 0.7}]->(life)
CREATE (moc:Entity {uid: 'moc.eq.one', entity_type: 'ku', title: 'MOC', updated_at: $iso})
CREATE (u)-[:OWNS]->(moc)
CREATE (moc)-[:ORGANIZES {order: 1}]->(ku_a)
CREATE (moc)-[:ORGANIZES {order: 2}]->(ku_b)
CREATE (ar_old:Entity:ActivityReport {uid: 'ar.eq.old', entity_type: 'activity_report', time_period: '2026-08',
                                      period_end: '2026-08-31', processed_content: 'Older'})
CREATE (ar_new:Entity:ActivityReport {uid: 'ar.eq.new', entity_type: 'activity_report', time_period: '2026-W36',
                                      period_end: '2026-09-07', processed_content: 'Latest',
                                      user_annotation: 'note'})
// An admin's report about the user is the user's own (Submit & Share arc R11) and the
// newest by period — and never the latest report for intelligence: it is a
// review, not the user's generation.
CREATE (ar_admin:Entity:ActivityReport {uid: 'ar.eq.admin', entity_type: 'activity_report', time_period: '2026-W38',
                                        period_end: '2026-09-21', processed_content: 'Admin review',
                                        processor_type: 'human', created_by: 'user_admin'})
CREATE (u)-[:OWNS]->(ar_old) CREATE (u)-[:OWNS]->(ar_new) CREATE (u)-[:OWNS]->(ar_admin)
CREATE (i_live:Insight {uid: 'ins.eq.active', insight_type: 'cross_domain', title: 'Live insight', impact: 'high',
                        confidence: 0.9, dismissed: false, actioned: false})
CREATE (i_gone:Insight {uid: 'ins.eq.dismissed', insight_type: 'cross_domain', title: 'Dismissed insight',
                        impact: 'low', confidence: 0.5, dismissed: true, actioned: false})
CREATE (u)-[:HAS_INSIGHT]->(i_live) CREATE (u)-[:HAS_INSIGHT]->(i_gone)
"""


def _seed_params(user_uid: UserUID) -> dict[str, Any]:
    today = date.today()
    return {
        "user_uid": user_uid,
        "iso": _SEEDED_AT.isoformat(),
        "old": (_SEEDED_AT - timedelta(days=60)).isoformat(),
        "today": today.isoformat(),
        "yesterday": (today - timedelta(days=1)).isoformat(),
        "tomorrow": (today + timedelta(days=1)).isoformat(),
        "old_date": (today - timedelta(days=60)).isoformat(),
    }


def _canon(value: Any) -> Any:
    """Order-insensitive view of a projection: ``collect()`` order is not a contract."""
    if isinstance(value, dict):
        return {k: _canon(v) for k, v in value.items()}
    if isinstance(value, list):
        return sorted(json.dumps(_canon(item), sort_keys=True, default=str) for item in value)
    return value


def _by_uid(items: list[dict[str, Any]], key: str = "entity") -> dict[str, dict[str, Any]]:
    return {item[key]["uid"]: item["graph_context"] for item in items}


@pytest.fixture
async def every_section_seeded(neo4j_driver: AsyncDriver, clean_neo4j) -> None:
    async with neo4j_driver.session() as session:
        await session.run(_SEED, **_seed_params(_USER_UID))


@pytest.mark.asyncio
async def test_the_merged_map_has_the_shape_the_populator_reads(
    neo4j_driver: AsyncDriver, every_section_seeded: None
) -> None:
    """The six partials merge into the one map, every section and every key present."""
    executor = UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver))

    result = await executor.execute_mega_query(_USER_UID)

    assert result.is_ok, result.error
    mega = result.value
    assert sorted(mega) == [
        "active_insights_raw",
        "activity_report",
        "entities",
        "life_path",
        "progress_counts",
        "rich",
        "uids",
    ]
    assert sorted(mega["uids"]) == [
        "active_goal_uids",
        "active_habit_uids",
        "active_moc_uids",
        "active_task_uids",
        "completed_goal_uids",
        "completed_task_uids",
        "core_principle_uids",
        "enrolled_path_uids",
        "goal_progress",
        "habit_metadata",
        "knowledge_mastery",
        "ku_bookmarked_uids",
        "ku_marked_as_read_uids",
        "ku_view_data",
        "moc_metadata",
        "overdue_task_uids",
        "pending_choice_uids",
        "today_event_uids",
        "today_task_uids",
        "upcoming_event_uids",
    ]
    assert sorted(mega["entities"]) == [
        "choices",
        "events",
        "goals",
        "habits",
        "learning_paths",
        "path_steps",
        "principles",
        "tasks",
    ]
    assert sorted(mega["rich"]) == ["knowledge", "learning_paths", "path_steps"]


@pytest.mark.asyncio
async def test_every_section_reads_what_the_one_statement_read(
    neo4j_driver: AsyncDriver, every_section_seeded: None
) -> None:
    """Field group by field group, the pinned values for a learner seeded in every section."""
    executor = UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver))

    result = await executor.execute_mega_query(_USER_UID)

    assert result.is_ok, result.error
    mega = result.value
    uids = mega["uids"]

    # tasks & goals
    assert sorted(uids["active_task_uids"]) == ["task.eq.dep", "task.eq.open"]
    assert uids["completed_task_uids"] == ["task.eq.sub"]
    assert uids["overdue_task_uids"] == ["task.eq.dep"]  # scheduled → overdue-eligible
    assert uids["today_task_uids"] == ["task.eq.open"]
    assert uids["active_goal_uids"] == ["goal.eq.active"]
    assert uids["completed_goal_uids"] == ["goal.eq.done"]
    assert _canon(uids["goal_progress"]) == _canon(
        [{"uid": "goal.eq.active", "progress": 0.4}, {"uid": "goal.eq.done", "progress": 1.0}]
    )
    assert mega["progress_counts"] == {
        "tasks_completed": 1,
        "tasks_total": 3,
        "goals_completed": 1,
        "goals_total": 2,
    }
    tasks = _by_uid(mega["entities"]["tasks"])
    # the completed subtask is untouched inside the window: in the uids, not in the rich rows
    assert sorted(tasks) == ["task.eq.dep", "task.eq.open"]
    assert _canon(tasks["task.eq.open"]) == _canon(
        {
            "subtasks": [{"uid": "task.eq.sub", "title": "Done subtask", "status": "completed"}],
            "dependencies": [{"uid": "task.eq.dep", "title": "Blocking task", "confidence": 0.9}],
            # the 0.3-confidence edge is under the floor; the PathStep rolls up to Ku C
            "applied_knowledge": [
                {"uid": "ku.eq.a", "title": "Ku A"},
                {"uid": "ku.eq.c", "title": "Ku C"},
            ],
            "goal_context": {"uid": "goal.eq.active", "title": "Active goal", "progress": 0.4},
        }
    )
    assert tasks["task.eq.dep"] == {
        "subtasks": [],
        "dependencies": [],
        "applied_knowledge": [],
        "goal_context": None,
    }
    goals = _by_uid(mega["entities"]["goals"])
    assert sorted(goals) == ["goal.eq.active"]  # the completed goal is outside the window
    assert _canon(goals["goal.eq.active"]) == _canon(
        {
            "contributing_tasks": [
                {"uid": "task.eq.open", "title": "Open task", "status": "active"}
            ],
            "sub_goals": [{"uid": "goal.eq.done", "title": "Done goal", "progress": 1.0}],
            "required_knowledge": [{"uid": "ku.eq.a", "title": "Ku A", "confidence": 0.8}],
        }
    )

    # habits & events
    assert sorted(uids["active_habit_uids"]) == ["habit.eq.active", "habit.eq.pre"]
    assert _canon(uids["habit_metadata"]) == _canon(
        [
            {"uid": "habit.eq.active", "streak": 5, "rate": 0.8},
            {"uid": "habit.eq.pre", "streak": 0, "rate": 0.0},
        ]
    )
    habits = _by_uid(mega["entities"]["habits"])
    assert sorted(habits) == ["habit.eq.active", "habit.eq.pre"]  # the completed one is out
    assert _canon(habits["habit.eq.active"]) == _canon(
        {
            "linked_goals": [{"uid": "goal.eq.active", "title": "Active goal", "status": "active"}],
            "applied_knowledge": [
                {"uid": "ku.eq.a", "title": "Ku A"},
                {"uid": "ku.eq.c", "title": "Ku C"},
            ],
            # declared both ways (ENABLES_HABIT in, REQUIRES_PREREQUISITE_HABIT out), listed once
            "prerequisites": [{"uid": "habit.eq.pre", "title": "Prereq habit"}],
        }
    )
    assert habits["habit.eq.pre"] == {
        "linked_goals": [],
        "applied_knowledge": [],
        "prerequisites": [],
    }
    assert _canon(uids["upcoming_event_uids"]) == _canon(["event.eq.today", "event.eq.next"])
    assert uids["today_event_uids"] == ["event.eq.today"]
    events = _by_uid(mega["entities"]["events"])
    assert sorted(events) == ["event.eq.next", "event.eq.today"]  # the past one is out
    assert _canon(events["event.eq.today"]) == _canon(
        {
            "applied_knowledge": [{"uid": "ku.eq.a", "title": "Ku A"}],
            "linked_goals": [{"uid": "goal.eq.active", "title": "Active goal", "status": "active"}],
            "practiced_habits": [{"uid": "habit.eq.active", "title": "Active habit"}],
            "conflicting_events": [{"uid": "event.eq.next", "title": "Tomorrow event"}],
            "reinforced_habits": [{"uid": "habit.eq.active", "title": "Active habit"}],
        }
    )
    assert events["event.eq.next"]["conflicting_events"] == [
        {"uid": "event.eq.today", "title": "Today event"}
    ]

    # principles & choices
    assert uids["core_principle_uids"] == ["principle.eq.core"]
    assert uids["pending_choice_uids"] == ["choice.eq.pending"]
    principles = _by_uid(mega["entities"]["principles"])
    assert _canon(principles["principle.eq.core"]) == _canon(
        {
            "grounded_knowledge": [{"uid": "ku.eq.a", "title": "Ku A"}],
            "guided_goals": [{"uid": "goal.eq.active", "title": "Active goal", "status": "active"}],
            "guided_choices": [{"uid": "choice.eq.pending", "title": "Pending choice"}],
            "embodying_habits": [{"uid": "habit.eq.active", "title": "Active habit"}],
            "aligned_tasks": [{"uid": "task.eq.open", "title": "Open task", "status": "active"}],
        }
    )
    choices = _by_uid(mega["entities"]["choices"])
    assert sorted(choices) == ["choice.eq.pending"]  # the decided one is outside the window
    assert _canon(choices["choice.eq.pending"]) == _canon(
        {
            "informing_knowledge": [{"uid": "ku.eq.a", "title": "Ku A"}],
            "guiding_principles": [{"uid": "principle.eq.core", "title": "Core principle"}],
            "affected_goals": [
                {"uid": "goal.eq.active", "title": "Active goal", "status": "active"}
            ],
            "opened_paths": [{"uid": "lp.eq.path", "title": "Path"}],
            "implementing_tasks": [
                {"uid": "task.eq.dep", "title": "Blocking task", "status": "scheduled"}
            ],
        }
    )

    # knowledge — the IN_PROGRESS PathStep rides along at the 0.1 default (old semantics)
    assert _canon(uids["knowledge_mastery"]) == _canon(
        [
            {
                "uid": "ku.eq.a",
                "score": 0.9,
                "mastered_at": _SEEDED_AT.isoformat(),
                "confidence": 0.8,
            },
            {"uid": "ku.eq.b", "score": 0.4, "mastered_at": None, "confidence": 1.0},
            {"uid": "ps.eq.one", "score": 0.1, "mastered_at": None, "confidence": 1.0},
        ]
    )
    assert uids["ku_view_data"] == [
        {
            "uid": "ku.eq.a",
            "view_count": 3,
            "time_spent_seconds": 120,
            "last_viewed_at": _SEEDED_AT.isoformat(),
        }
    ]
    assert uids["ku_marked_as_read_uids"] == ["ku.eq.a"]
    assert uids["ku_bookmarked_uids"] == ["ku.eq.b"]
    knowledge = {item["uid"]: item["graph_context"] for item in mega["rich"]["knowledge"]}
    assert sorted(knowledge) == ["ku.eq.a", "ku.eq.b", "ps.eq.one"]
    assert _canon(knowledge["ku.eq.a"]) == _canon(
        {
            "prerequisites": [{"uid": "ku.eq.pre", "title": "Ku Pre", "confidence": 0.9}],
            # a Goal that REQUIRES_KNOWLEDGE is a dependent too — the edge is matched on :Entity
            "dependents": [
                {"uid": "ku.eq.dep", "title": "Ku Dep", "confidence": 0.75},
                {"uid": "goal.eq.active", "title": "Active goal", "confidence": 0.8},
            ],
        }
    )
    assert knowledge["ps.eq.one"] == {
        "prerequisites": [{"uid": "ku.eq.pre", "title": "Ku Pre", "confidence": None}],
        "dependents": [],
    }

    # curriculum
    assert uids["enrolled_path_uids"] == ["lp.eq.path"]
    paths = _by_uid(mega["entities"]["learning_paths"])
    assert sorted(paths) == ["lp.eq.path"]  # the life path is designated, not enrolled
    assert _canon(paths["lp.eq.path"]) == _canon(
        {
            "steps": [
                {"uid": "ps.eq.one", "title": "Step 1", "completed": False, "sequence": 1},
                {"uid": "ps.eq.two", "title": "Step 2", "completed": True, "sequence": 2},
            ],
            "prerequisite_knowledge": [{"uid": "ku.eq.pre", "title": "Ku Pre"}],
            "aligned_goals": [
                {"uid": "goal.eq.active", "title": "Active goal", "status": "active"}
            ],
            "embodied_principles": [{"uid": "principle.eq.core", "title": "Core principle"}],
            "total_steps": 2,
            "completed_steps": 1,
            "progress_percentage": 50.0,
        }
    )
    assert _canon(mega["rich"]["learning_paths"]) == _canon(
        [
            {"path": item["entity"], "graph_context": item["graph_context"]}
            for item in mega["entities"]["learning_paths"]
        ]
    )
    steps = _by_uid(mega["entities"]["path_steps"])
    assert sorted(steps) == ["ps.eq.one"]
    assert _canon(steps["ps.eq.one"]) == _canon(
        {
            "prerequisite_steps": [{"uid": "ps.eq.zero", "title": "Step 0", "completed": True}],
            # BUILDS_HABIT also points at another user's habit — re-tied to the anchored user (ADR-085 G2)
            "practice_habits": [{"uid": "habit.eq.active", "title": "Active habit"}],
            "practice_tasks": [{"uid": "task.eq.open", "title": "Open task", "status": "active"}],
            "knowledge_relationships": [
                {
                    "uid": "ku.eq.c",
                    "title": "Ku C",
                    "domain": None,
                    "entity_type": "ku",
                    "rel_type": "USES_KU",
                },
                {
                    "uid": "ku.eq.pre",
                    "title": "Ku Pre",
                    "domain": None,
                    "entity_type": "ku",
                    "rel_type": "REQUIRES_KNOWLEDGE",
                },
            ],
            "learning_path": {"uid": "lp.eq.path", "name": "Path"},
            "total_prerequisites": 1,
            "total_practice_opportunities": 2,
            "is_sequenced": True,
        }
    )
    assert _canon(mega["rich"]["path_steps"]) == _canon(
        [
            {"step": item["entity"], "graph_context": item["graph_context"]}
            for item in mega["entities"]["path_steps"]
        ]
    )
    assert uids["active_moc_uids"] == ["moc.eq.one"]
    assert uids["moc_metadata"] == [{"uid": "moc.eq.one", "updated": _SEEDED_AT.isoformat()}]

    # learner state
    assert mega["life_path"] == {
        "uid": "lp.eq.life",
        "designated_at": _SEEDED_AT.isoformat(),
        "alignment_score": 0.7,
    }
    assert mega["activity_report"] == {
        "uid": "ar.eq.new",
        "period": "2026-W36",
        "period_end": "2026-09-07",
        "content": "Latest",
        "user_annotation": "note",
    }
    assert mega["active_insights_raw"] == [
        {
            "uid": "ins.eq.active",
            "type": "cross_domain",
            "title": "Live insight",
            "impact": "high",
            "confidence": 0.9,
        }
    ]


@pytest.mark.asyncio
async def test_the_rich_context_carries_every_section(
    neo4j_driver: AsyncDriver, every_section_seeded: None
) -> None:
    """Through the builder: the populated fields of the rich context for this graph."""
    builder = UserContextBuilder(UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver)))
    user = User(uid=_USER_UID, title="eq", email="eq@test.com")

    result = await builder.build_rich_user_context(_USER_UID, user)

    assert result.is_ok, result.error
    context = result.value
    # standard fields
    assert sorted(context.active_task_uids) == ["task.eq.dep", "task.eq.open"]
    assert context.completed_task_uids == {"task.eq.sub"}
    assert context.overdue_task_uids == ["task.eq.dep"]
    assert context.active_goal_uids == ["goal.eq.active"]
    assert context.goal_progress == {"goal.eq.active": 0.4, "goal.eq.done": 1.0}
    assert context.habit_streaks == {"habit.eq.active": 5, "habit.eq.pre": 0}
    assert context.knowledge_mastery == {"ku.eq.a": 0.9, "ku.eq.b": 0.4, "ps.eq.one": 0.1}
    assert context.mastered_knowledge_uids == {"ku.eq.a"}
    assert context.in_progress_knowledge_uids == {"ku.eq.b", "ps.eq.one"}
    assert context.mastery_confidence_scores == {"ku.eq.a": 0.8, "ku.eq.b": 1.0, "ps.eq.one": 1.0}
    assert context.ku_view_counts == {"ku.eq.a": 3}
    assert context.ku_marked_as_read_uids == {"ku.eq.a"}
    assert context.ku_bookmarked_uids == {"ku.eq.b"}
    assert context.enrolled_path_uids == ["lp.eq.path"]
    assert sorted(context.upcoming_event_uids) == ["event.eq.next", "event.eq.today"]
    assert context.core_principle_uids == ["principle.eq.core"]
    assert context.pending_choice_uids == ["choice.eq.pending"]
    assert context.active_moc_uids == ["moc.eq.one"]
    assert context.recently_viewed_moc_uids == ["moc.eq.one"]
    assert context.current_ps_uids == {"ps.eq.one"}
    # rich fields
    assert {
        domain: sorted(item["entity"]["uid"] for item in items)
        for domain, items in context.entities_rich.items()
    } == {
        "tasks": ["task.eq.dep", "task.eq.open"],
        "goals": ["goal.eq.active"],
        "habits": ["habit.eq.active", "habit.eq.pre"],
        "events": ["event.eq.next", "event.eq.today"],
        "principles": ["principle.eq.core"],
        "choices": ["choice.eq.pending"],
        "learning_paths": ["lp.eq.path"],
        "path_steps": ["ps.eq.one"],
        # derived Python-side from mastery + view data inside the window, not a statement
        "ku": ["ku.eq.a"],
    }
    assert sorted(context.knowledge_units_rich) == ["ku.eq.a", "ku.eq.b", "ps.eq.one"]
    # the curriculum rich lists keep the old ``path`` / ``step`` keys, not ``entity``
    assert [item["path"]["uid"] for item in context.enrolled_paths_rich] == ["lp.eq.path"]
    assert [item["step"]["uid"] for item in context.active_path_steps_rich] == ["ps.eq.one"]
    # graph-sourced and derived
    assert context.task_dependencies == {"task.eq.open": ["task.eq.dep"]}
    assert context.blocked_task_uids == {"task.eq.open"}
    assert context.task_knowledge_applied == {"task.eq.open": ["ku.eq.a", "ku.eq.c"]}
    assert context.task_goal_associations == {"task.eq.open": "goal.eq.active"}
    assert context.tasks_by_goal == {"goal.eq.active": ["task.eq.open"]}
    assert context.habits_by_goal == {"goal.eq.active": ["habit.eq.active"]}
    assert context.habit_prerequisites == {"habit.eq.active": ["habit.eq.pre"]}
    assert context.goal_knowledge_required == {"goal.eq.active": ["ku.eq.a"]}
    assert context.goal_knowledge_mastered == {"goal.eq.active": ["ku.eq.a"]}
    assert context.event_knowledge_applied == {"event.eq.today": ["ku.eq.a"]}
    assert context.principle_knowledge_grounded == {"principle.eq.core": ["ku.eq.a"]}
    assert context.choice_knowledge_informed == {"choice.eq.pending": ["ku.eq.a"]}
    assert context.principle_guided_choice_counts == {"principle.eq.core": 1}
    assert context.prerequisite_counts == {"ku.eq.a": 1, "ku.eq.b": 0, "ps.eq.one": 1}
    assert context.ready_to_learn_uids == {"ku.eq.b"}
    assert context.overall_progress == pytest.approx(1 / 3)
    # learner state
    assert context.life_path_uid == "lp.eq.life"
    assert context.life_path_alignment_score == 0.7
    assert context.latest_activity_report_uid == "ar.eq.new"  # not the admin's ar.eq.admin
    assert context.latest_activity_report_period == "2026-W36"
    assert context.latest_activity_report_content == "Latest"
    assert context.cross_domain_insights == {
        "active_count": 1,
        "top_insights": [
            {
                "uid": "ins.eq.active",
                "type": "cross_domain",
                "title": "Live insight",
                "impact": "high",
                "confidence": 0.9,
            }
        ],
    }


@pytest.mark.asyncio
async def test_the_standard_context_skips_the_admin_report_too(
    neo4j_driver: AsyncDriver, every_section_seeded: None
) -> None:
    """The standard build reads the latest report through its own statement
    (CONSOLIDATED_QUERY); it applies the same rule as the rich one."""
    builder = UserContextBuilder(UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver)))
    user = User(uid=_USER_UID, title="eq", email="eq@test.com")

    result = await builder.build_user_context(_USER_UID, user)

    assert result.is_ok, result.error
    assert result.value.latest_activity_report_uid == "ar.eq.new"


@pytest.mark.asyncio
async def test_an_unknown_user_reads_as_the_empty_sentinel(
    neo4j_driver: AsyncDriver, clean_neo4j
) -> None:
    executor = UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver))

    result = await executor.execute_mega_query(UserUID("user_nobody"))

    assert result.is_ok and result.value == {"uids": {}, "entities": {}, "rich": {}}


@pytest.mark.asyncio
async def test_a_learner_whose_every_insight_is_dismissed_keeps_the_rest_of_the_context(
    neo4j_driver: AsyncDriver, clean_neo4j
) -> None:
    """The insight predicate is on the OPTIONAL MATCH, so no row is filtered before the aggregation."""
    user_uid = UserUID("user_test_123")
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (u:User {uid: $user_uid})
            CREATE (u)-[:OWNS]->(:Entity:Task {uid: 'task.dismissed.only', entity_type: 'task', title: 'Still here',
                                               status: 'active', updated_at: $iso, user_uid: $user_uid})
            CREATE (u)-[:ULTIMATE_PATH {designated_at: $iso, alignment_score: 0.5}]->
                   (:Entity:LearningPath {uid: 'lp.dismissed.life', entity_type: 'learning_path', title: 'Life'})
            CREATE (u)-[:HAS_INSIGHT]->(:Insight {uid: 'ins.dismissed.only', insight_type: 'x', title: 'gone',
                                                  impact: 'low', confidence: 0.5, dismissed: true, actioned: false})
            """,
            user_uid=user_uid,
            iso=datetime.now().isoformat(),
        )
    builder = UserContextBuilder(UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver)))
    user = User(uid=user_uid, title="dismissed", email="dismissed@test.com")

    result = await builder.build_rich_user_context(user_uid, user)

    assert result.is_ok, result.error
    context = result.value
    assert context.active_task_uids == ["task.dismissed.only"]
    assert context.life_path_uid == "lp.dismissed.life"
    assert context.cross_domain_insights == {"active_count": 0, "top_insights": []}


@pytest.mark.asyncio
async def test_a_goal_with_milestones_builds(neo4j_driver: AsyncDriver, clean_neo4j) -> None:
    """Goal.milestones is a JSON string on the node; no projection iterates it as a list."""
    user_uid = UserUID("user_test_456")
    milestones = '[{"uid": "m1", "title": "First", "is_completed": true}]'
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (u:User {uid: $user_uid})
            CREATE (u)-[:OWNS]->(:Entity:Goal {uid: 'goal.with.milestones', entity_type: 'goal', title: 'Staged',
                                               status: 'active', progress_percentage: 10.0, updated_at: $iso,
                                               user_uid: $user_uid, milestones: $milestones})
            """,
            user_uid=user_uid,
            iso=datetime.now().isoformat(),
            milestones=milestones,
        )
    executor = UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver))

    result = await executor.execute_mega_query(user_uid)

    assert result.is_ok, result.error
    goals = result.value["entities"]["goals"]
    assert [goal["entity"]["uid"] for goal in goals] == ["goal.with.milestones"]
    # the string rides along on the entity for whoever parses it; no derived count in Cypher
    assert goals[0]["entity"]["milestones"] == milestones
    assert "milestone_progress" not in goals[0]["graph_context"]
