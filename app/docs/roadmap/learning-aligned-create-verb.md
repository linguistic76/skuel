---
title: The learning-aligned create verb — ideas preserved from the deleted bridge create half
updated: '2026-09-03'
category: roadmap
status: UNSCHEDULED — build when a lived workflow demands it
related_docs:
  - patterns/LEARNING_ALIGNMENT_BRIDGE.md
---
# The learning-aligned create verb

**What this is:** the two genuinely valuable feature ideas that lived inside the
`LearningAlignmentBridge` create half, preserved when that code was deleted
(2026-08-06) — plus the census of remaining dict-door creates found during the
same investigation.

**Why the code went:** `/docs/patterns/LEARNING_ALIGNMENT_BRIDGE.md` § The create
half was DELETED holds the record. Broken ≠ staged, so this is a roadmap note
rather than a PLANNED-tier bloat entry: there is no working code to stage.

---

## Thread 1: Act on a learning recommendation

**The verb:** turn "you should practice X next" into an actual Task/Event with
one click. The ZPD capstone (`context.zpd_assessment`) computes recommended
learning actions; intelligence services return plans. Nothing yet CREATES an
activity from a recommendation.

**Build surface when wanted:**
- A thin gate-plus-primitive wrapper per domain — `create_task_with_context`
  (TasksSchedulingService) is the worked example: validate against UserContext,
  then delegate to the core primitive (`core.create_task(request, user_uid)`),
  which handles events, embedding, and guarded link edges.
- OR the committed curriculum→activity mechanism: **ActivityTemplates + the
  PsEngagement spawn orchestrator** (`create_with_spawned_from`, graph-native
  `SPAWNED_FROM` edge). A recommendation that points at a PS can spawn that
  PS's template. Prefer this over a new bespoke path — One Path Forward.

Both surfaces create through the primitive, and the primitive is the whole
create path: an alignment assessment is a read, so a create-with-alignment
layer above the primitive has nothing of its own to persist.

## Thread 2: Learning path → calendar schedule

**The verb:** "turn my LP into a weekly study rhythm on the calendar." The
deleted `create_learning_path_schedule` batch-created naive one-hour weekly
events for 4 weeks; `create_study_session` created a single study event for a
set of Kus and linked them via APPLIES_KNOWLEDGE.

**Build surface when wanted:** design against the CURRENT calendar/rhythm
architecture, not the deleted code — `TimeOfDay` slots + duration (habit-rhythm
arc, no clock times), the habitual week on the calendar week view, and the
Events core primitive for creation (each event announced via
`CalendarEventCreated`, knowledge linked through the guarded
`link_event_to_knowledge` path). The deleted 9:00-AM-every-week logic predates
all of that and was not worth carrying.

---

## Census: remaining dict-door creates

Found 2026-08-06 while scoping; each reaches `backend.create_{domain}` (the
dynamic alias to `create(entity)`) with a dict.

**Fixed in the same PR as the bridge deletion** (the route-attribute audit
revealed `POST /api/goals/create-with-scheduling` was LIVE on one of them, so
"broken but unreachable" did not hold):
- `GoalsSchedulingService.create_goal_with_context` — rewired: capacity gate,
  then `core.create_goal`. Its route now works instead of persisting a corrupt
  node per call.
- `HabitsSchedulingService.create_habit_with_context` — same rewire
  (facade-exposed via `create_habit_with_scheduling_context`, no route).
- `HabitsSchedulingService.create_habit_from_path_step` — rewired to the entity
  door (`core.create`) with a properly built frozen `Habit`; its old dict used
  DTO-era key names ("name", "category", "difficulty") that matched no model
  field, further proof it never worked.
- `POST /api/goals/create-with-learning-scheduling` — route DELETED with its
  target (the bridge wrapper); it had never returned anything but an error.

  Note the NAME COLLISION that survives: `create_goal_with_context` /
  `create_habit_with_context` exist BOTH as facade orchestrators
  (`_orchestration_mixin.py` — prereq/habit gates) and as scheduling-service
  methods (capacity gates). Both pairs now create through the core primitives;
  whether two gate-flavors per domain should remain is a separate design
  question.

**Still open — probably functional but bypassing the primitives (DTO
`to_dict()` carries uid/user_uid; no events published, no embedding requested,
no admission guard):**
- `GoalTaskGenerator.generate_tasks_for_goal` — `tasks_backend.create_task(task_template.to_dict())`
- `HabitEventScheduler.schedule_events_for_habit` and
  `schedule_streak_maintenance` — `events_backend.create_event(...to_dict())`

These are live-documented features (GoalTaskGenerator mints tasks on goal
creation), so the fix direction is the #969 treatment — route through the
domain's core primitive — not deletion. Decide as its own arc.
