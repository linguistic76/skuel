---
title: Activity Template Authoring
created: 2026-09-06
updated: 2026-09-06
status: current
category: guides
tags: [yaml, ingestion, authoring, curriculum, activity-templates, pathstep, engagement]
---

# Activity Template Authoring

How to author the 6 Activity Templates as vault files.

This guide runs beginner → advanced. **Part 1** walks one template end to end and is
enough to author your first. **Part 2** is the authoring rules in depth. **Part 3** is the
field reference for all six kinds. **Part 4** is what happens after you author — the part
that decides whether a mistake is fixable.

---

# Part 1 — Start here

## Why templates exist

A PathStep is a lesson. A learner can read it, understand it, and change nothing about
their week — reading is not practice. A **template** is how the lesson reaches into the
learner's actual life: when they press *Start learning*, each template attached to that
PathStep becomes **their own** Habit, Task, Goal, Event, Choice or Principle, dated from
the day *they* started.

One `HabitTemplate` you author once becomes a personal Habit for every learner who ever
engages that step. You are not writing a habit; you are writing the blueprint a habit is
stamped from.

| | Instance (`Task`, `Habit`, …) | Template (`TaskTemplate`, `HabitTemplate`, …) |
|---|---|---|
| Owner | one user | none — PS-owned curriculum |
| Dates | absolute (`due_date: 2026-10-01`) | offsets (`due_offset: {days: 7}`) |
| Cross-refs | `fulfills_goal_uid` | `fulfills_goal_template_uid` |
| Attached from a PS by | `task_uids:` (`ASSIGNS_TASK`) | `task_template_uids:` (`HAS_TASK_TEMPLATE`) |
| Per learner | shared — everyone sees the same node | one fresh instance each |

## The idea in one picture

```
   YOU AUTHOR                 A LEARNER ENGAGES            THE LEARNER ACTS
   (content vault)            (presses "Start learning")   (their own week)
   ───────────────            ──────────────────────────   ────────────────

   ht.mind.daily-breath  ───► habit_a1b2                ─► ticks it off,
     one shared node            owner: that learner          builds a streak
     no owner, no dates         recurrence: daily

   tt.mind.log-five      ───► task_c3d4                 ─► completes it
     due_offset: {days: 7}     owner: that learner
                               due_date: today + 7

                                                        then, at the completion review:
                                                          keep    → it becomes theirs for
                                                                    good (OWNED)
                                                          discard → it is deleted
```

Three facts follow from that picture, and most beginner mistakes are one of them:

1. **The template is shared; the instances are private.** Editing the template changes
   what *future* learners get. It does not touch a single instance already spawned.
2. **Dates are offsets, never calendar dates** — the template does not know when anyone
   will start.
3. **The PathStep names its templates**, not the other way round. A template file says
   nothing about which step uses it.

## Walkthrough — one habit, start to finish

The smallest thing that works. Five steps.

**1. Write the template file.** Anywhere in the content vault; the folder is not read.
`Tmpl/` is the convention.

```yaml
# 0vault/Tmpl/two-minutes-daily_tmpl.md
---
type: habit_template
uid: ht.mindfulness.daily-2min-breath
title: Two Minutes of Breath Awareness
description: Two minutes. Attention on the breath. When it wanders, come back.

polarity: build
habit_category: mindfulness
recurrence_pattern: daily
duration_minutes: 2
---
```

**2. Attach it from the PathStep** — the step's frontmatter, not the template's.

```yaml
# 0vault/Ps/breath-awareness-basics_Ps.md
---
type: PathStep
uid: ps.mindfulness.breath-awareness-basics
title: Breath Awareness — Basics

habit_template_uids:
  - ht.mindfulness.daily-2min-breath
---
```

**3. Preview the sync.** Nothing is written; you are checking that both files are seen.

```bash
./dev vault-sync --vault content --preview
```

**4. Sync for real.**

```bash
./dev vault-sync --vault content
```

**5. Verify it landed.** Open the PathStep at `/explore/ps/ps.mindfulness.breath-awareness-basics`.
Teachers and admins see a read-only **Activity Templates** panel near the bottom listing
what is attached, grouped by domain. Your habit should appear under *Habits* with the
count at 1. If the panel says *No habit templates yet*, the edge was not written — go to
[When a sync goes wrong](#when-a-sync-goes-wrong); the sync will have reported success
either way.

That is the whole loop. Everything below is detail on top of these five steps.

## Which kind should I reach for?

Do not start with all six. Most steps need one or two.

| You want the learner to… | Use | Spawns |
|---|---|---|
| do something once, by a deadline | **TaskTemplate** | a Task with a `due_date` |
| do something repeatedly, building a streak | **HabitTemplate** | a Habit with a recurrence |
| aim at a measurable outcome over weeks | **GoalTemplate** | a Goal with milestones |
| put a block in their calendar | **EventTemplate** | an Event on a date, at a time |
| decide something before going further | **ChoiceTemplate** | a Choice with options |
| hold a stance they can act from | **PrincipleTemplate** | a Principle with expressions |

A good first PathStep is **one HabitTemplate and one TaskTemplate**: the practice, and
the thing that proves they did it. Add a Goal when you want the practice measured, a
Choice when the learner must commit to a *how* before starting.

## The four rules you cannot skip

1. **Always author `uid:`.** Its prefix is validated (`ht.`, `tt.`, …) and identity
   depends on it. See [The file](#the-file) for what happens if you omit it.
2. **Never author `status:`.** The ingest door stamps `active`, which is what a template
   needs to spawn.
3. **`title:` is the only required field.** Everything else is optional on all six kinds.
4. **Body text is not read.** Everything goes in the frontmatter.

---

# Part 2 — Authoring in depth

## The file

One file, one template. Name it `<slug>_tmpl.md`, following the content vault's suffix
convention (`_Ku`, `_Ps`, `_exer`, `_edge`). The suffix is a **human** label — nothing
machine-side reads the filename or the folder. The six kinds share the one suffix and
are told apart by `type:`, because that is what the ingest detector actually reads;
six suffixes would buy nothing and would drift.

```yaml
---
type: task_template
uid: tt.mindfulness.log-first-5-sessions
title: Log Your First 5 Sessions
description: |
  After each of your first five breath-awareness sessions, write two or three
  sentences about what you noticed.

due_offset: {days: 14}
duration_minutes: 30
completion_updates_goal: true

tags:
  - mindfulness
  - practice
---
```

**`type:`** — the discriminator. Both spellings resolve: `task_template` (canonical) and
`TaskTemplate` (the PascalCase class name, matching how the vault spells `PathStep` and
`Ku`).

| Kind | `type:` | UID prefix | PS attaches with |
|------|---------|------------|------------------|
| TaskTemplate | `task_template` | `tt.` | `task_template_uids:` |
| GoalTemplate | `goal_template` | `gt.` | `goal_template_uids:` |
| HabitTemplate | `habit_template` | `ht.` | `habit_template_uids:` |
| EventTemplate | `event_template` | `et.` | `event_template_uids:` |
| ChoiceTemplate | `choice_template` | `ct.` | `choice_template_uids:` |
| PrincipleTemplate | `principle_template` | `pt.` | `principle_template_uids:` |

**`uid:`** — always author it. Its prefix is validated, and a file with no `uid:` derives one
from the filename stem — which leaks the stem into the UID and makes identity depend on the
filename. The sync's move pre-pass recovers a pure rename by content hash, but a rename plus an
edit in the same sync is a new node; templates carry no body for the similarity fallback to
compare, so hash matching is the only net. Dot form only (`tt.{grouping}.{slug}`); the colon
spelling was retired 2026-08-14 and fails validation.

**`title:`** — the only required field on all six. Everything else is optional.

**`status:`** — omit it. The ingest door stamps `active`, which is what a template needs:
engagement refuses to spawn from a non-active template, and ingestion applies no model
defaults, so an unstamped node would read as `draft` and silently never spawn.

An authored `status:` still wins, but **do not use `status: draft` to park a template
that is already attached to a PathStep** — a single non-active template fails validation
for the whole bundle, so it blocks that PathStep from being published *and* from being
engaged by anyone. To park one, take its UID out of the PathStep's `*_template_uids:`
list; the file can stay.

**Body text** is not read for templates. Put everything in the frontmatter.

---

---

## Attaching to a PathStep

The PathStep names its templates; the template says nothing about its PathStep. One
template may be listed by several PathSteps — reuse is a second line, not a second file.

```yaml
---
type: PathStep
uid: ps.mindfulness.breath-awareness-basics
title: Breath Awareness — Basics

task_template_uids:
  - tt.mindfulness.log-first-5-sessions
habit_template_uids:
  - ht.mindfulness.daily-2min-breath
goal_template_uids:
  - gt.mindfulness.beginner-consistency
---
```

Each channel targets its own label, so a UID pointing at the wrong kind matches nothing
rather than writing an edge no reader consults. Drop a UID from the list and the edge is
retracted on the next sync of that file.

⚠ **These edges are written only when the PathStep file itself is ingested.** A template
that did not yet exist when the PathStep was last synced — because its own file was added
later, or failed validation on that run — gets *no edge*, and nothing says so: the sync
reports success and the PathStep simply has one fewer template. Re-sync the PathStep
after fixing the template (any edit to the file, or `--force`), then check the count.

Do not confuse the two grains: `habit_uids:` points at a Habit that already exists and is
shared by everyone; `habit_template_uids:` points at a HabitTemplate the PathStep spawns
a fresh Habit from, per learner. `event_uids:` is the instance channel — it was renamed
from `event_template_uids:` when the template channel took the name it reads like.

---

---

## Offsets

Every date on a template is **relative to engagement**, written as a map of any of
`days`, `hours`, `minutes`:

```yaml
due_offset: {days: 7}                    # due a week after the learner engages
target_offset: {days: 30}
decision_deadline_offset: {days: 3, hours: 12}
```

A key that is not one of those three is rejected at ingest with a per-file message —
without that gate a mistyped `{day: 7}` would persist happily and rebuild as a **zero**
offset, spawning something due today while the write reported success.

| Template | Offset fields | Resolves to |
|----------|---------------|-------------|
| TaskTemplate | `due_offset`, `scheduled_offset`, `recurrence_end_offset` | `due_date`, `scheduled_date`, `recurrence_end_date` |
| GoalTemplate | `start_offset`, `target_offset` | `start_date`, `target_date` |
| HabitTemplate | `recurrence_end_offset` | `recurrence_end_date` |
| EventTemplate | `event_offset`, `recurrence_end_offset` | `event_date`, `recurrence_end_date` |
| ChoiceTemplate | `decision_deadline_offset` | `decision_deadline` |
| PrincipleTemplate | — | — |

---

---

## Structured lists

Three fields take a list of maps rather than a list of strings: `GoalTemplate.milestones`,
`ChoiceTemplate.options`, and `PrincipleTemplate.expressions`.

**`milestones` and `options` require a `uid:` on every item.** An item without one cannot
be rebuilt on read — the field comes back as the raw JSON string it was stored as, and
the spawned instance carries that string where a list of milestones should be. The UID
only has to be unique within its own template.

```yaml
milestones:
  - uid: ms.first-week
    title: Practised on five separate days
    target_value: 5
```

`expressions` takes `context` / `behavior` / `example` and needs no UID.

---

---

## Connecting templates to each other

A template can point at another template on the same PathStep. At spawn time the
reference is re-pointed at the *instance* that other template just produced, so the
learner's Task fulfils the learner's Goal — not a shared one.

```yaml
# tt.mindfulness.log-first-5-sessions
fulfills_goal_template_uid: gt.mindfulness.beginner-consistency
reinforces_habit_template_uid: ht.mindfulness.daily-2min-breath
```

Nine such fields exist. Each lands on the spawned instance either as a **property** or as
a **graph edge**:

| On this template | Reference field | Must point at | Lands on the instance as |
|---|---|---|---|
| GoalTemplate | `fulfills_goal_template_uid` | GoalTemplate | property `fulfills_goal_uid` |
| GoalTemplate | `selected_choice_option_template_uid` | **ChoiceTemplate** | property `selected_choice_option_uid` |
| GoalTemplate | `inspired_by_choice_template_uid` | ChoiceTemplate | edge `(Goal)-[:INSPIRED_BY_CHOICE]->(Choice)` |
| EventTemplate | `reinforces_habit_template_uid` | HabitTemplate | edge `(Event)-[:REINFORCES_HABIT]->(Habit)` |
| EventTemplate | `milestone_celebration_for_goal_template_uid` | GoalTemplate | edge `(Event)-[:CELEBRATES_GOAL]->(Goal)` |
| TaskTemplate | `fulfills_goal_template_uid` | GoalTemplate | property `fulfills_goal_uid` |
| TaskTemplate | `scheduled_event_template_uid` | EventTemplate | property `scheduled_event_uid` |
| TaskTemplate | `parent_template_uid` | TaskTemplate | property `parent_uid` (spawns as a sub-task) |
| TaskTemplate | `reinforces_habit_template_uid` | HabitTemplate | edge `(Task)-[:REINFORCES_HABIT]->(Habit)` |

**You do not have to memorise the split.** It mirrors how the *instance* already stores
that relationship: where the instance model keeps a `*_uid` property, the template writes
a property; where the graph edge is the instance's single source of truth
(`REINFORCES_HABIT`, `INSPIRED_BY_CHOICE`, `CELEBRATES_GOAL`), the template writes that
edge. The practical consequence is only in how you read it back — an edge-backed link is
not a property on the spawned node; ask the domain service for it.

⚠ **`selected_choice_option_template_uid` wants a ChoiceTemplate UID, not an option UID.**
The name reads like it wants `opt.morning` from an `options:` list. It does not — write
the `ct.…` UID. An option UID fails validation as `target_missing`.

### Two constraints on any reference

**Both templates must hang off the same PathStep.** A reference to a template attached to
a different step fails as `cross_ps`, and one to a template that exists nowhere fails as
`target_missing`. So a set of templates that reference each other travels as a set — see
[Reuse across PathSteps](#reuse-across-pathsteps) before listing one template on two
steps.

**Direction is already decided for you.** Templates spawn in four dependency layers so a
later layer can point at what an earlier one just made:

```
Layer 1   Choice, Habit, Principle     (depend on nothing)
Layer 2   Goal                         (may reference Choice)
Layer 3   Event                        (may reference Habit, Goal)
Layer 4   Task                         (may reference Goal, Habit, Event)
```

You cannot get this wrong by accident: the nine fields above are exactly the legal
directions, so there is no field with which to reference upward. A `PrincipleTemplate`
has no reference fields at all.

---

## When a sync goes wrong

Validation runs over the **whole PathStep bundle**, on both publish and engage, and it is
all-or-nothing: one bad template fails the step, not just itself. Six violations exist;
each names the offending template and field, and carries a fuzzy-matched `hint` when a
near-miss UID is on the step.

| Violation | Means | Usual cause |
|---|---|---|
| `not_active` | the template's status is not `active` | you authored `status: draft`. Checked first |
| `target_missing` | the reference points at no template on this step | typo in the UID, or the target's file has not synced yet |
| `wrong_type` | the reference points at the wrong kind | a `gt.` UID in a habit field — or an option UID in `selected_choice_option_template_uid` |
| `cross_ps` | the target is attached to a different PathStep | give this step its own copy of the target template (see [Reuse](#reuse-across-pathsteps)) |
| `self_reference` | a template references its own UID | a copy-pasted UID that was not edited |
| `cycle` | `parent_template_uid` chains back on itself | A → B → A among TaskTemplates |

Two failures are **silent** — the sync reports success and you get less than you authored:

| Symptom | Cause | Fix |
|---|---|---|
| the panel shows one fewer template than you attached | the template did not exist when the PathStep was last ingested — its file was added later, or failed validation on that run | re-sync the PathStep (any edit to its file, or `--force`), then re-check the count |
| a `milestones` / `options` list comes back as a JSON string | an item is missing its nested `uid:` | add `uid:` to every item and re-sync |

**Start any diagnosis at the panel**, not the sync log: `/explore/ps/{uid}` shows what the
graph actually holds, which is the only thing engagement reads.

---

## Syncing

Both ingest doors read templates: the admin **Sync content vault** button
(`POST /api/vault/sync/content`) and the one-shot script shown in the walkthrough. They
are the same call.

Deleting a template file deletes its node on the next sync. Removing a UID from a
PathStep's `*_template_uids:` retracts that edge on the next sync of the PathStep — only
edges that file authored are retracted.

`--preview` cannot see file *moves*: a pure rename renders as `N new + N deleted` and may
trip the mass-deletion refusal. The real sync detects the move by content hash and
rewrites the tracker row instead.

### The third door

A JSON API exists too — one route file per kind, `POST /api/pathstep-{domain}-templates/`
to create and `POST /api/pathstep-{domain}-templates/attach?ps_uid=…&template_uid=…` to
attach, TEACHER+. It works, but the vault is the door to use: it is the one with a diff,
a history and a preview.

---

# Part 3 — Field reference

Fields shared by all six come from `Entity`: `uid`, `title`, `description`, `summary`,
`content`, `status`, `tags`, `domain`, `metadata`, `parent_entity_uid`. The tables below
list what each template adds. Everything a template carries is copied to the instance it
spawns — [What the learner's instance carries](#what-the-learners-instance-carries) is the
exact account of what spawning changes.

A field the model types as a plain string may still be **enum-checked at the ingest
door** — `event_type` and `recurrence_pattern` both are. The Type column below is the
authoring vocabulary, not the Python annotation; an off-vocabulary value fails the file
with the accepted list in the message.

### TaskTemplate — `type: task_template`

```yaml
---
type: task_template
uid: tt.mindfulness.breath-practice-primary
title: Complete 5 Breath-Awareness Sessions
description: Five separate sessions of any length. One minute counts.

due_offset: {days: 7}
duration_minutes: 10
completion_updates_goal: true
fulfills_goal_template_uid: gt.mindfulness.beginner-consistency
---
```

| Field | Type | Purpose |
|-------|------|---------|
| `due_offset` | offset map | Due date = engagement + offset |
| `scheduled_offset` | offset map | Scheduled date = engagement + offset |
| `duration_minutes` | int | Estimated duration |
| `recurrence_pattern` | `none`/`daily`/`weekdays`/`weekends`/`weekly`/`biweekly`/`monthly`/`quarterly`/`yearly`/`custom` | Optional recurrence |
| `recurrence_end_offset` | offset map | When recurrence ends |
| `parent_template_uid` | `tt.…` | Spawns as a sub-task of that template's instance |
| `project` | string | Free-text project grouping |
| `fulfills_goal_template_uid` | `gt.…` | Resolves to the spawned Goal |
| `reinforces_habit_template_uid` | `ht.…` | Becomes a `REINFORCES_HABIT` edge to the spawned Habit |
| `scheduled_event_template_uid` | `et.…` | Resolves to the spawned Event |
| `goal_progress_contribution` | float 0.0–1.0 | How much completion advances the goal |
| `knowledge_mastery_check` | bool | Completion marks a mastery checkpoint |
| `habit_streak_maintainer` | bool | Completion maintains a habit streak |
| `completion_updates_goal` | bool | Completion triggers a goal progress update |

### GoalTemplate — `type: goal_template`

```yaml
---
type: goal_template
uid: gt.mindfulness.beginner-consistency
title: Practise on 10 Separate Days
goal_type: process
timeframe: monthly
measurement_type: numeric
target_value: 10
unit_of_measurement: days
target_offset: {days: 30}

why_important: |
  Consistency matters more than session length at the beginning.

milestones:
  - uid: ms.first-five
    title: Five separate days
    target_value: 5
---
```

| Field | Type | Purpose |
|-------|------|---------|
| `goal_type` | `outcome`/`process`/`learning`/`project`/`milestone`/`mastery` | Classification |
| `timeframe` | `daily`/`weekly`/`monthly`/`quarterly`/`yearly`/`multi_year` | Horizon |
| `measurement_type` | `binary`/`percentage`/`numeric`/`milestone`/`habit_based`/`knowledge_based`/`task_based`/`mixed` | How progress is measured |
| `target_value` | float | Numeric target |
| `unit_of_measurement` | string | Unit for `target_value` |
| `start_offset` | offset map | Start date = engagement + offset |
| `target_offset` | offset map | Target date = engagement + offset |
| `milestones` | list of maps (each needs `uid`, `title`) | Checkpoints, cloned to the instance |
| `vision_statement` | string | The pull |
| `why_important` | string | The reason |
| `success_criteria` | string | What done looks like |
| `potential_obstacles` | list of strings | Anticipated friction |
| `strategies` | list of strings | How to get there |
| `fulfills_goal_template_uid` | `gt.…` | Makes this a sub-goal of that template's instance |
| `inspired_by_choice_template_uid` | `ct.…` | Becomes an `INSPIRED_BY_CHOICE` edge to the spawned Choice |
| `selected_choice_option_template_uid` | `ct.…` | Resolves to the spawned Choice |
| `target_identity` | string | Who this makes the learner |
| `identity_evidence_required` | int | Evidence count for the identity claim |

### HabitTemplate — `type: habit_template`

```yaml
---
type: habit_template
uid: ht.mindfulness.daily-2min-breath
title: Two Minutes of Breath Awareness
polarity: build
habit_category: mindfulness
habit_difficulty: easy

cue: Right after you sit down at your desk
routine: |
  Two minutes. Attention on the breath. When it wanders, come back.
reward: A settled start to the work

recurrence_pattern: daily
target_days_per_week: 7
preferred_time: morning
duration_minutes: 2
is_identity_habit: true
target_identity: someone who notices
---
```

| Field | Type | Purpose |
|-------|------|---------|
| `polarity` | `build`/`break`/`neutral` | Building or breaking |
| `habit_category` | `health`/`fitness`/`mindfulness`/`learning`/`productivity`/`creative`/`social`/`financial`/`other` | Classification |
| `habit_difficulty` | `trivial`/`easy`/`moderate`/`challenging`/`hard` | Difficulty |
| `cue` | string | Atomic Habits: the trigger |
| `routine` | string | Atomic Habits: the behaviour |
| `reward` | string | Atomic Habits: the payoff |
| `reinforces_identity` | string | Identity the habit builds |
| `is_identity_habit` | bool | Whether identity is the point |
| `target_identity` | string | Who this makes the learner |
| `identity_evidence_required` | int | Evidence count for the identity claim |
| `duration_minutes` | int | Per-occurrence duration |
| `recurrence_pattern` | same values as TaskTemplate | How often — enum-checked at ingest even though the model types it as a string |
| `recurrence_end_offset` | offset map | When recurrence ends |
| `target_days_per_week` | int | Weekly target |
| `preferred_time` | `early_morning`/`morning`/`afternoon`/`evening`/`night`/`late_night`/`anytime` | Time of day |
| `reminder_time` | string `HH:MM` | Default reminder time |
| `reminder_days` | list of strings | Days the reminder fires |
| `reminder_enabled` | bool | Whether reminders are on by default |

### EventTemplate — `type: event_template`

```yaml
---
type: event_template
uid: et.mindfulness.week-one-practice-block
title: Week One Practice Block
event_offset: {days: 3}
start_time: "07:30:00"
end_time: "07:45:00"
duration_minutes: 15
event_type: learning
location: wherever you sit
reminder_minutes: 10
reinforces_habit_template_uid: ht.mindfulness.daily-2min-breath
---
```

| Field | Type | Purpose |
|-------|------|---------|
| `event_offset` | offset map | Event date = engagement + offset |
| `start_time` | `HH:MM:SS` | Absolute time of day (not engagement-relative) — quote it, or YAML reads it as a number |
| `end_time` | `HH:MM:SS` | Absolute time of day (not engagement-relative) |
| `duration_minutes` | int | Duration |
| `event_type` | `meeting`/`conference`/`workshop`/`deadline`/`reminder`/`personal`/`work`/`social`/`learning`/`health` | Kind of event — enum-checked at ingest even though the model types it as a string |
| `location` | string | Where |
| `is_online` | bool | Online or in person |
| `meeting_url` | string | Join link |
| `recurrence_pattern` | same values as TaskTemplate | How often — enum-checked at ingest even though the model types it as a string |
| `recurrence_end_offset` | offset map | When recurrence ends |
| `reminder_minutes` | int | Lead time |
| `max_attendees` | int | Cap |
| `reinforces_habit_template_uid` | `ht.…` | Becomes a `REINFORCES_HABIT` edge to the spawned Habit |
| `milestone_celebration_for_goal_template_uid` | `gt.…` | Becomes a `CELEBRATES_GOAL` edge to the spawned Goal |
| `is_milestone_event` | bool | Whether this marks a milestone |
| `milestone_type` | string | Which kind of milestone |
| `curriculum_week` | int | Week within the curriculum |
| `knowledge_retention_check` | bool | Attendance is a retention checkpoint |
| `recurrence_maintains_habit` | bool | Recurrence sustains a habit |
| `skip_breaks_habit_streak` | bool | Skipping breaks the streak |

### ChoiceTemplate — `type: choice_template`

```yaml
---
type: choice_template
uid: ct.mindfulness.when-to-practise
title: When Will You Practise?
choice_type: multiple
decision_deadline_offset: {days: 2}
decision_criteria:
  - A time you are reliably alone
  - A time you are not already rushed
options:
  - uid: opt.morning
    title: First thing in the morning
    description: Before the day starts making demands.
  - uid: opt.commute
    title: On the commute
    description: Same time every day, already a habit slot.
  - uid: opt.evening
    title: Before bed
    description: A closing rather than an opening.
---
```

| Field | Type | Purpose |
|-------|------|---------|
| `choice_type` | `binary`/`multiple`/`ranking`/`allocation`/`strategic`/`operational` | Shape of the decision |
| `options` | list of maps (each needs `uid`, `title`) | The options, cloned to the instance |
| `decision_rationale` | string | Why this decision is being framed |
| `decision_criteria` | list of strings | What to weigh |
| `constraints` | list of strings | What is fixed |
| `stakeholders` | list of strings | Who is affected |
| `decision_deadline_offset` | offset map | Deadline = engagement + offset |
| `inspiration_type` | string | Free-text kind of prompt |
| `expands_possibilities` | bool | Whether the choice opens options rather than narrowing them |

### PrincipleTemplate — `type: principle_template`

```yaml
---
type: principle_template
uid: pt.mindfulness.noticing-is-the-practice
title: Noticing Is the Practice
statement: |
  The moment you notice your attention has wandered IS the practice —
  not the moment before it wandered.
principle_category: personal
principle_source: philosophical
strength: core
key_behaviors:
  - Return without commentary
  - Count the return, not the lapse
expressions:
  - context: practice
    behavior: Treat each return as a repetition, not a failure
    example: Attention drifts to email; you notice; that is one rep.
---
```

| Field | Type | Purpose |
|-------|------|---------|
| `statement` | string | The principle itself |
| `principle_category` | `spiritual`/`ethical`/`relational`/`personal`/`professional`/`intellectual`/`health`/`creative` | Domain of life |
| `principle_source` | `philosophical`/`religious`/`cultural`/`personal`/`scientific`/`mentor`/`literature` | Where it comes from |
| `strength` | `core`/`strong`/`moderate`/`developing`/`exploring` | How firmly held |
| `tradition` | string | Named tradition |
| `original_source` | string | Book, person, text |
| `personal_interpretation` | string | The learner-facing reading |
| `expressions` | list of maps (`context`, `behavior`, `example`) | How it shows up in practice |
| `key_behaviors` | list of strings | What acting on it looks like |
| `potential_conflicts` | list of strings | Where it strains |
| `conflicting_principles` | list of strings | Which principles it pulls against |
| `resolution_strategies` | list of strings | How to resolve the strain |
| `origin_story` | string | Where it came from |
| `evolution_notes` | string | How the reading has changed |

---

---

# Part 4 — After you author

Everything above is about getting a template into the graph. This part is about what
happens to it afterwards — which is what decides whether an authoring mistake is
recoverable.

## The engagement lifecycle

```
  learner presses "Start learning"
        │
        ├── validation over the whole bundle          ← fails ⇒ nothing spawns
        ├── engagement edge opens; its timestamp is the offset anchor
        └── instances spawn, layer 1 → 4              state: ENGAGED
                │
                ├── learner works …
                │
                ├── COMPLETION REVIEW ─── keep     ⇒  state: OWNED (outlives the step)
                │                     └── discard  ⇒  instance deleted
                │
                └── ABANDON             ⇒  every spawned instance deleted;
                                           the engagement edge stays, marked abandoned
```

Three consequences for you as the author:

- **Keep is the default.** A template the learner does not explicitly discard at the
  review is kept. Author as though what you spawn will stay in their life.
- **Abandon is total.** It removes every instance of that engagement, finished or not —
  and, until [the scope defect](../roadmap/shared-template-engagement-scope.md) is fixed,
  instances of *other* engagements too. Two flows reach it: re-engaging one step (below)
  and [sharing a template across steps](#reuse-across-pathsteps).
- **One engagement at a time, per step.** A second `engage` on the same step while one is
  active is refused (`engagement_already_active`) — a learner does not accumulate
  duplicates by clicking twice. After completing or abandoning, they *may* engage the
  same step again, and that opens a fresh engagement. Engagements on *different* steps
  run concurrently as a matter of course.

  ⚠ **Re-engaging a step is not safe yet, and this one needs no template sharing.**
  Keep an instance at the review (it becomes `owned`), engage the same step again, then
  abandon: the instance lookup returns the kept instance too — `owned` is in its state
  list — and abandon deletes what the learner earned in the first engagement. Case 1 in
  [shared-template-engagement-scope.md](../roadmap/shared-template-engagement-scope.md).

Spawning is **best-effort, not one transaction**: if a later layer fails to persist, the
orchestrator deletes the instances it already wrote and returns the failure. You will not
find a learner holding half a bundle.

## Editing a template after learners have engaged

**Your edit does not reach them.** Spawning copies every authoring field onto a new,
learner-owned node; the only link back is `(instance)-[:SPAWNED_FROM]->(template)`, which
nothing reads to re-sync. So:

| You change | Learners who already engaged | Learners who engage next |
|---|---|---|
| a typo in `title` or `description` | keep the old text | get the new text |
| an offset (`due_offset: {days: 7}` → `{days: 14}`) | keep their original dates | get the new spacing |
| a cross-reference | keep the old wiring | get the new wiring |
| delete the template file | keep their instances — see below | the step spawns one fewer |

There is no re-stamp and no migration path. If a mistake must reach people who already
started, that is a data fix on their instances, not an edit here.

⚠ **Deleting a template file orphans the instances it spawned.** The node goes with a
`DETACH DELETE`, which takes the `SPAWNED_FROM` edges with it. The instances survive and
stay in their owners' lists, but the engagement can no longer find them: they cannot be
kept or discarded at the completion review, and abandon will not remove them. Prefer
taking the UID out of the PathStep's `*_template_uids:` — that retracts the edge and
leaves the file, the node and every live engagement intact.

This cuts the other way too, and it is the reason the model is worth its complexity: a
learner's Habit is *theirs* the moment it spawns. You cannot reach into their week by
editing curriculum, and neither can anyone else.

## Reuse across PathSteps

One template may be listed by any number of PathSteps — reuse is a second line in a
second step's frontmatter, not a second file:

```yaml
# ps.mindfulness.breath-awareness-basics_Ps.md
habit_template_uids:
  - ht.mindfulness.daily-2min-breath
```

```yaml
# ps.mindfulness.week-two_Ps.md
habit_template_uids:
  - ht.mindfulness.daily-2min-breath          # the same file, listed again
```

A learner who engages **both** steps gets **two** instances — one per engagement, each
dated from its own anchor. Engagement does not de-duplicate across PathSteps; the second
is not an error, it is a second engagement.

Because references are per-PathStep, a shared template's cross-references must resolve on
*every* step that lists it — a `fulfills_goal_template_uid` pointing at a Goal that only
step A carries fails step B with `cross_ps`.

⚠ **Sharing one template across two steps is not safe yet.** Completing or abandoning
either step reaches the *other* step's instances as well, because the "which instances
belong to this engagement" query scopes by template rather than by engagement. The same
gap makes a second engagement of a single step delete what the learner kept from the
first. Until it is fixed, give each PathStep its own template file. Tracked in
[shared-template-engagement-scope.md](../roadmap/shared-template-engagement-scope.md).

## Sub-tasks

`parent_template_uid` on a TaskTemplate spawns its Task as a child of another spawned
Task, giving the learner a small tree rather than a flat list:

```yaml
# tt.mindfulness.log-session-1
title: Log session 1
parent_template_uid: tt.mindfulness.log-first-5-sessions
```

Both templates must be on the same step, and the chain is cycle-checked — A → B → A
fails the step with `cycle`. This is the only reference field whose targets form a
hierarchy, and it is Tasks only.

## What the learner's instance carries

Everything you authored is copied through, except the fields spawning owns:

| Field | On the instance |
|---|---|
| `uid` | freshly generated (`task_…`, `habit_…`), not yours |
| `user_uid` | the learner |
| `entity_type` | the instance type (`Task`, not `TaskTemplate`) |
| `engagement_state` | `engaged`, then `owned` if kept |
| `source_path_step_uid` | the step they engaged |
| every `*_offset` | resolved to an absolute date against the engagement moment |
| every `*_template_uid` | re-pointed at the sibling instance, as a property or an edge |

`status`, `tags`, `description`, and every domain field you set ride through unchanged.

---

## Related Documentation

- [YAML Authoring Guide](YAML_AUTHORING_GUIDE.md) — entity structure, `connections`, edge files
- [Curriculum Developer Guide](CURRICULUM_DEVELOPER_GUIDE.md) — authoring a PathStep end to end
- [Unified Ingestion Guide](../patterns/UNIFIED_INGESTION_GUIDE.md) — the ingest pipeline
- [ADR-061 — spawn layer consolidation](../decisions/ADR-061-spawn-layer-consolidation.md) — the spawn registry
- [Activity Templates get a vault door](../roadmap/done/activity-templates-vault-door.md) — why the vault is the door
- [Engagement instance scope](../roadmap/shared-template-engagement-scope.md) — the open defect behind the reuse warning
