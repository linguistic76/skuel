---
title: Tasks User Guide
created: 2026-06-25
updated: 2026-06-25
status: current
category: guides
tags: [tasks, user-guide, goals, subtasks, obsidian, learning-loop, applied-knowledge]
related_docs:
  - /docs/guides/VOICE_JOURNALING_AND_OBSIDIAN_GUIDE.md
  - /docs/guides/YAML_AUTHORING_GUIDE.md
  - /docs/decisions/ADR-070-bidirectional-vault-bridge.md
  - /docs/architecture/knowledge_substance_philosophy.md
---

# Tasks User Guide

Tasks in SKUEL are applied knowledge — they're how concepts become actions, and actions become lived experience. This guide covers everything from creating a task to tracking it, decomposing it into sub-tasks, and keeping it in sync between SKUEL and your Obsidian vault.

---

## What a Task Is (and Isn't)

A SKUEL Task is not just a to-do item. It carries:

- **A knowledge connection** — linking the task to a PathStep or Ku tells the system *what you're practicing* when you do this work. Completing the task increments your substance score for that knowledge.
- **A goal link** — connecting the task to a Goal shows how discrete actions accumulate toward an outcome.
- **Graph context** — the task lives in your personal knowledge graph, where it can be related to habits, events, and principles.

This makes tasks searchable, analyzable, and pedagogically meaningful — not just a checkbox.

---

## Four Ways to Create a Task

### 1. UI Form at `/tasks/create`

The fastest route for one-off tasks:

1. Go to **[/tasks/create](/tasks/create)**
2. Fill in the title, description, priority, and optional due date
3. Use the **Goal** picker to link to a goal (the task appears in that goal's progress)
4. Use the **Habit** picker to link the task to a habit you want to reinforce
5. Click **Create Task**

You'll be redirected to the task detail page.

**Key form fields:**

| Field | Purpose |
|-------|---------|
| Title | Required. What you're doing. |
| Description | Context, constraints, or success criteria. |
| Priority | `low` / `medium` / `high` / `critical` — drives ordering in your task list. |
| Due Date | Optional. Sets a deadline. |
| Goal | Optional. Links this task to a goal via `FULFILLS_GOAL`. |
| Habit | Optional. Links this task to a habit via `REINFORCES_HABIT`. |
| Parent Task | Optional. Makes this a sub-task of another task. |

### 2. YAML File in Your Vault

For tasks you're authoring as part of a learning plan or curriculum bundle, write a `.yaml` file:

```yaml
version: 1.0
type: Task

uid: task.sel.daily-reflection-week-1
title: Daily Reflection — Week 1
description: >
  Each evening, spend 5 minutes writing down one emotion you noticed today
  and what triggered it. Use the Knowing Yourself PathStep as your guide.
priority: medium
status: active
tags: [sel, self-awareness, practice]

connections:
  applies_knowledge:
    - ps.sel.knowing-yourself          # Knowledge substance channel
  fulfills_goal: [goal.sel.self-awareness-practice]
  reinforces_habit: [habit.daily-evening-reflection]
```

Drop this file in your vault directory (`INGESTION_PATH`) and run the sync. SKUEL creates the task and wires all connections in one pass.

**Common YAML connections for tasks:**

| `connections` field | What it creates | Weight |
|--------------------|----------------|--------|
| `applies_knowledge` | `APPLIES_KNOWLEDGE → PathStep/Ku` | 0.05 substance per completion |
| `fulfills_goal` | `FULFILLS_GOAL → Goal` | Contributes to goal progress |
| `reinforces_habit` | `REINFORCES_HABIT → Habit` | Links to an existing habit |
| `depends_on` | `DEPENDS_ON → Task` | Blocks this task until the other is done |

### 3. Obsidian Daily Note

If you write your daily tasks in Obsidian using the obsidian-tasks plugin, SKUEL can read them directly. Write a checkbox line in your daily or weekly note:

```markdown
- [ ] Daily reflection — 5 minutes of emotional noticing
- [ ] Review SEL PathStep and identify one Ku I want to practice this week
```

When you sync the note to SKUEL (`POST /api/vault/sync`), SKUEL:
1. Reads the checkbox lines
2. Creates Task entities from them (with `EXTRACT_ACTIVITIES` pipeline)
3. Injects a `🆔 sk_<6>` ID into each line so SKUEL can track it across syncs

After injection, your note looks like:

```markdown
- [ ] Daily reflection — 5 minutes of emotional noticing 🆔 sk_a1b2c3
- [ ] Review SEL PathStep and identify one Ku I want to practice this week 🆔 sk_d4e5f6
```

The `🆔` suffix is the durable join key — SKUEL uses it to match the line to the Task even after you edit the title or move the note.

See [Part 2 of the Voice Journaling and Obsidian Guide](/docs/guides/VOICE_JOURNALING_AND_OBSIDIAN_GUIDE.md) for full setup instructions.

### 4. Auto-Spawned from a PathStep Engagement

When a PathStep has TaskTemplates attached (added by the curriculum admin), clicking **Start learning** on the PathStep detail page automatically creates tasks for you:

1. Navigate to a PathStep at `/explore/ps/{uid}`
2. Click **Start learning** (the action bar at the bottom)
3. SKUEL spawns one Task per TaskTemplate, anchored to the date you engaged
4. The spawned tasks appear immediately in the **Tasks** section at the bottom of the PathStep detail page
5. They also appear in your task list at `/tasks`

Spawned tasks carry the due dates and scheduling offsets the curriculum author set. For example, a TaskTemplate with `due_offset: {days: 7}` spawns a task due 7 days after you clicked "Start learning."

See the [PathStep detail page](/explore) and the [engagement workflow](#pathstep-engagement-workflow) section below for more detail.

---

## Organizing with Sub-Tasks

Any task can have sub-tasks. Sub-tasks give you a lightweight breakdown of larger work without needing a separate project management tool.

### Creating Sub-Tasks

**From the UI:** Open any task at `/tasks/detail?uid=...`. The **Sub-tasks** panel appears below the main task detail. Click **Add sub-task**, type a title, and press Enter or click the button. The sub-task is created immediately and appears in the list.

**From YAML:** Set the `parent_uid` field on the child task:

```yaml
type: Task
uid: task.sel.reflection-day-1
title: Day 1 Reflection
parent_uid: task.sel.daily-reflection-week-1    # Makes this a sub-task
```

**From TaskTemplates:** Curriculum authors can create a template hierarchy using `parent_template_uid` — when the parent task spawns from a PathStep engagement, the sub-task templates spawn alongside it.

### Sub-Task Behavior

- Sub-tasks appear in the **Sub-tasks** section on the parent task's detail page
- Sub-tasks also appear in your main task list at `/tasks` (they're full Task entities)
- Completing a sub-task does not automatically complete the parent — that decision is yours
- Sub-tasks can have their own sub-tasks (nested hierarchy, unlimited depth)

---

## Tracking and Status

### Status Lifecycle

Tasks move through a defined lifecycle:

```
draft → active → paused → completed
             ↓
           blocked → active
             ↓
           cancelled / failed
```

| Status | Meaning |
|--------|---------|
| `draft` | Created but not started — the default |
| `active` | Work in progress |
| `paused` | Temporarily on hold |
| `blocked` | Can't proceed until something else is done |
| `completed` | Done ✓ |
| `cancelled` | Dropped deliberately |
| `failed` | Attempted but not completed |

Change status from the task detail page using the status button, or from the task list card.

### Task List at `/tasks`

Your task list at **[/tasks](/tasks)** shows all your tasks with filter controls:

- **Status filter**: Active, All, Completed, etc.
- **Priority filter**: All, Critical, High, Medium, Low
- **Sort**: Priority (default), Due Date, Recently Updated

The stats bar at the top shows your task summary: total, active, completed this week, and overdue.

### Knowledge Substance

Every time you complete a task that has an `applies_knowledge` connection, SKUEL increments the substance score for that knowledge concept. Substance measures how much a concept is *lived*, not just *learned*. The task channel contributes up to 0.25 to a knowledge concept's substance score (0.05 per completion, across all tasks using that knowledge).

See [Knowledge Substance Philosophy](/docs/architecture/knowledge_substance_philosophy.md) for the full scoring model.

---

## PathStep Engagement Workflow

When a PathStep has TaskTemplates, the engagement workflow ties tasks directly to your learning:

1. **Find a PathStep** at `/explore` or through a Learning Path
2. **Read the content** — the PathStep becomes `learning` state
3. **Click "Start learning"** — if the PathStep has TaskTemplates, SKUEL calls `POST /api/ps/{uid}/engage`
4. **Tasks spawn** — one per template, scheduled relative to today
5. **Work the tasks** — they appear both in `/tasks` and in the Tasks section on the PathStep detail page
6. **Complete the tasks** — as you complete them, the engagement auto-completes (or you manually complete it)

The spawned tasks carry the `source_path_step_uid` property and a `SPAWNED_FROM` edge to their template — so SKUEL always knows which learning content a task originated from.

**What "Start learning" does vs. what it doesn't:**

- If the PathStep **has** TaskTemplates: clicks "Start learning" → engages the PS → spawns tasks
- If the PathStep **doesn't** have TaskTemplates: clicking "Start learning" → toggles read-progress only (no tasks spawn)

The action bar adapts automatically — you don't need to know which case applies.

---

## Obsidian Round-Trip

If you complete a task in SKUEL and then sync your vault, SKUEL writes the completion back to your Obsidian note:

**In Obsidian before:** `- [ ] Daily reflection 🆔 sk_a1b2c3`

**After SKUEL marks it done and you sync:** `- [x] Daily reflection 🆔 sk_a1b2c3 ✅ 2026-06-25`

The `✅ YYYY-MM-DD` token is written by SKUEL so the obsidian-tasks plugin recognizes the completion date.

**If you complete it in Obsidian first** (by checking the box), the next sync reads the `[x]` and marks the SKUEL Task as completed.

**Field authority** — who owns what:

| Field | Edited in | Syncs to |
|-------|-----------|---------|
| Title | Obsidian | → SKUEL (vault wins) |
| Checkbox done | Either | Both (bidirectional) |
| Due date (📅) | Obsidian | → SKUEL |
| Priority (🔺⏫) | Obsidian | → SKUEL |
| Tags (#hashtag) | Obsidian | → SKUEL (becomes `Task.tags`) |
| Goal link, habit link | SKUEL | SKUEL only (not in Obsidian) |
| Knowledge connections | SKUEL | SKUEL only |
| ZPD scores | SKUEL | SKUEL only |

**First-run notice:** The first time you sync, SKUEL will explain that it needs to inject `🆔 sk_<6>` IDs into your task lines. Approve once; subsequent syncs proceed silently.

**How to trigger sync:** `POST /api/vault/sync` via the "Update from my vault" button (UI location TBD — check `/settings` for the vault sync controls).

---

## Tips

**Link tasks to knowledge.** A task without a `applies_knowledge` connection is just a to-do item. Connect it to a PathStep or Ku and it becomes a substance contribution.

**Use goals to group.** If you have 8 tasks all working toward the same outcome, link them all to a shared Goal. The goal's progress view shows all contributing tasks.

**Sub-tasks for estimation.** Break down a large task into sub-tasks that each take ≤2 hours. This gives you a natural progress indicator and makes the work feel tractable.

**Let PathStep engagement drive task creation.** If you're working through a structured curriculum, don't create tasks manually — engage the PathSteps instead. The TaskTemplates already encode the right sequence and timing.

**Don't over-tag.** A few precise tags are more useful than many vague ones. Tags are most valuable for filtering and search; your graph connections do the deeper linking.

---

## Related Guides

- [Voice Journaling and Obsidian Guide](/docs/guides/VOICE_JOURNALING_AND_OBSIDIAN_GUIDE.md) — writing tasks in daily notes, periodic notes setup
- [YAML Authoring Guide](/docs/guides/YAML_AUTHORING_GUIDE.md) — full YAML field reference, connections system
- [Curriculum Developer Guide](/docs/guides/CURRICULUM_DEVELOPER_GUIDE.md) — how TaskTemplates get attached to PathSteps
- [Knowledge Substance Philosophy](/docs/architecture/knowledge_substance_philosophy.md) — how task completions contribute to substance scores
- [ADR-070: Bidirectional VaultBridge](/docs/decisions/ADR-070-bidirectional-vault-bridge.md) — Obsidian round-trip design decisions
