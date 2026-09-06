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

An **Activity Template** is a blueprint a PathStep owns. When a learner engages that
PathStep, each attached template spawns **one instance owned by that learner**, with
every engagement-relative offset resolved against the moment they engaged. One
`HabitTemplate` on a PathStep becomes a personal Habit for every learner who starts it.

Templates are curriculum, so they are authored the way all curriculum is authored —
as files in the content vault. A JSON API remains as a second door — one route file per
kind, `POST /api/pathstep-{domain}-templates/` to create and
`POST /api/pathstep-{domain}-templates/attach?ps_uid=…&template_uid=…` to attach — but the
vault is the one you should use.

| | Instance (`Task`, `Habit`, …) | Template (`TaskTemplate`, `HabitTemplate`, …) |
|---|---|---|
| Owner | one user | none — PS-owned curriculum |
| Dates | absolute (`due_date: 2026-10-01`) | offsets (`due_offset: {days: 7}`) |
| Cross-refs | `fulfills_goal_uid` | `fulfills_goal_template_uid` |
| Attached from a PS by | `task_uids:` (`ASSIGNS_TASK`) | `task_template_uids:` (`HAS_TASK_TEMPLATE`) |
| Per learner | shared — everyone sees the same node | one fresh instance each |

---

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

## The six kinds

Fields shared by all six come from `Entity`: `uid`, `title`, `description`, `summary`,
`content`, `status`, `tags`, `domain`, `metadata`, `parent_entity_uid`. The tables below
list what each template adds. Everything a template carries is copied to the instance it
spawns, except the offsets and `*_template_uid` refs noted above.

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

## What engagement does

Templates spawn in dependency layers so a later layer can point at an instance the
earlier one just created: Choice / Habit / Principle, then Goal, then Event, then Task.
Each spawned instance carries `(instance)-[:SPAWNED_FROM]->(template)` back to its
blueprint — there is no `template_uid` property.

A cross-reference is written either as a property or as an edge, depending on the pair:
`fulfills_goal_template_uid` becomes the instance's `fulfills_goal_uid` property, while
`reinforces_habit_template_uid` becomes a `REINFORCES_HABIT` edge. Both are resolved to
the *spawned* instance, so a reference only works when both templates hang off the same
PathStep.

Both `publish_pathstep` and `engage_pathstep` run the same validation over the whole
bundle first, and it is all-or-nothing: one template that is not `active`, one
cross-reference pointing outside this PathStep, or one self-reference fails the
PathStep — not just that template. A PathStep with no templates attached at all cannot
be engaged either.

---

## Syncing

Both ingest doors read templates: the admin "Sync content vault" button
(`POST /api/vault/sync/content`) and the one-shot script.

```bash
./dev vault-sync --vault content --preview   # dry run: what would ingest, what would be deleted
./dev vault-sync --vault content             # write
```

Deleting a template file deletes its node on the next sync. Removing a UID from a
PathStep's `*_template_uids:` retracts that edge on the next sync of the PathStep — only
edges that file authored are retracted.

`--preview` cannot see file *moves*: a pure rename renders as `N new + N deleted` and may
trip the mass-deletion refusal. The real sync detects the move by content hash and
rewrites the tracker row instead.

---

## Related Documentation

- [YAML Authoring Guide](YAML_AUTHORING_GUIDE.md) — entity structure, `connections`, edge files
- [Curriculum Developer Guide](CURRICULUM_DEVELOPER_GUIDE.md) — authoring a PathStep end to end
- [Unified Ingestion Guide](../patterns/UNIFIED_INGESTION_GUIDE.md) — the ingest pipeline
- [ADR-061 — spawn layer consolidation](../decisions/ADR-061-spawn-layer-consolidation.md) — the spawn registry
- [Activity Templates get a vault door](../roadmap/done/activity-templates-vault-door.md) — why the vault is the door
