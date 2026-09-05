---
title: Voice Journaling and Obsidian Guide
updated: 2026-09-05
status: current
category: guides
tags: [obsidian, journaling, voice, vaultbridge, activity-domains, daily-workflow, user-guide]
related_docs:
  - /docs/decisions/ADR-070-bidirectional-vault-bridge.md
  - /docs/dsl/DSL_USAGE_GUIDE.md
  - /docs/patterns/UNIFIED_INGESTION_GUIDE.md
  - /docs/guides/YAML_AUTHORING_GUIDE.md
---

# Voice Journaling and Obsidian Guide

A practical guide to using SKUEL as your daily writing and voice journaling environment, with Obsidian as the authoring surface.

---

## What This Guide Covers

SKUEL supports three ways of capturing your daily life:

| Mode | What you do | What SKUEL does |
|------|-------------|-----------------|
| **Voice journaling** | Record audio on any device, upload to SKUEL | Transcribes, structures, and stores your entry |
| **Written journaling** | Author daily or weekly notes in Obsidian | Reads the note, extracts tasks and habits, and keeps both apps in sync |
| **Structured activities** | Write short YAML files for goals, habits, tasks, etc. | Creates activity items in your graph and connects them to your learning |

Obsidian is the recommended authoring environment for all three modes. Your vault is the place where your thoughts originate — SKUEL is the structured backbone that connects them.

---

## Part 1 — Voice Journaling

### Recording your voice memo

Record on whatever device is most natural: your phone's native voice recorder, a desktop mic, Whisper, or any other tool. SKUEL accepts:

- **Audio:** `.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.webm`
- **Video** (audio is extracted)
- **Text:** `.txt`, `.md`, or pasted text
- **PDF and document files**

You can upload up to 20 files at once in a single session.

### Uploading at /journals

The page has two modes, toggled at the top:

**Upload Files** — pick one or more files from your device:
1. Go to **[/journals](/journals)**
2. Optionally give the entry a title and connect it to a learning exercise
3. Select your audio file(s) and click **Submit to AI**

**Upload Folder** — batch-transcribe an entire directory server-side (same UX as the admin batch-transcribe console):
1. Switch to the **Upload Folder** tab
2. The input directory defaults to `/home/mike/0bsidian/skuel/transcribe_in`; the output directory defaults to `transcribe_out`
3. Click **Preview Files** to see what will be processed without transcribing
4. Click **Transcribe All** to run Deepgram — `.txt` files are written to the output directory

SKUEL transcribes the audio (via Deepgram), structures the content, and saves it as a journal entry. You'll see a status indicator as it processes. For most voice memos, transcription completes in seconds.

### Browsing and responding at /journals/browse

All your journal entries live at **[/journals/browse](/journals/browse)**.

Each card shows the transcription, the date, and a **Get AI response** button. Clicking it sends the entry to an AI coach that writes a reflective response — acknowledging patterns, asking a follow-up question, or surfacing a connection to something you've been studying. The response appears in your journal and is stored in SKUEL for future reference.

---

## Part 2 — Written Journaling with Obsidian

### The key idea: your note becomes a SKUEL entry

When you write in Obsidian using the provided templates, each note carries a small block of YAML at the top (called *frontmatter*). That frontmatter tells SKUEL what kind of entry it is and how to process it:

```
---
type: user_entry
pipeline: extract_activities
---
```

The `pipeline: extract_activities` instruction tells SKUEL: *scan this note for any task or habit lines and create real activity items from them*. Those lines use a simple annotation syntax (described in [Part 3](#part-3--writing-activities-in-your-notes)) that turns plain English into structured data.

### Setting up Periodic Notes in Obsidian

SKUEL's templates are designed for the **Periodic Notes** Obsidian plugin (by Liam Cain), which automatically creates new notes from your templates on the right cadence.

**Plugin install:** In Obsidian, go to `Settings → Community Plugins → Browse`, search for *Periodic Notes*, and install it.

**Configure each period** to point to the corresponding template:

| Period | Template file | Suggested folder |
|--------|--------------|-----------------|
| Daily | `templates/t_daily.md` | `daily/` |
| Weekly | `templates/t_weekly.md` | `weekly/` |
| Monthly | `templates/t_monthly.md` | `monthly/` |
| Quarterly | `templates/t_quarterly.md` | `quarterly/` |
| Yearly | `templates/t_yearly.md` | `yearly/` |

Open each period via the Command Palette (`Cmd/Ctrl+P → Open daily note`, etc.) and Periodic Notes will fill in the date tokens automatically.

---

### The Daily Template (`t_daily.md`)

```markdown
---
type: user_entry
pipeline: extract_activities
title: 2026-06-24
date: 2026-06-24
tags:
  - daily
metadata:
  entry_kind: daily
---

# 📅 2026-06-24

## Focus

## Tasks

- [ ] 

## Notes

## End of Day

- What went well?
- One adjustment for tomorrow.
```

**How to use it:**

- **Focus** — one sentence: what is this day about? This anchors your attention before the to-do list.
- **Tasks** — write your day's checkboxes here. Add `@context(task)` to any line you want SKUEL to track as a real task (see [Part 3](#part-3--writing-activities-in-your-notes)).
- **Notes** — free prose. Meeting notes, ideas, observations. No special syntax needed.
- **End of Day** — a brief retrospective. Answering these two questions takes two minutes and makes a surprising difference over time.

When this note is synced to SKUEL (via the vault sync button at [/submissions/sync](/submissions/sync)), the checkbox lines with `@context()` tags become Task activity items in your graph. The entire note is also stored as a journal entry so you can search and review it later.

---

### The Weekly Template (`t_weekly.md`)

```markdown
---
type: user_entry
pipeline: extract_activities
title: Week 2026-W26
week_of: 2026-W26
tags:
  - weekly
metadata:
  entry_kind: weekly
---

# 📅 Week 2026-W26

## Weekly Focus

Theme or intention for this week.

## Goals & Tasks

- [ ] 

## Notes

## Weekly Review

- What mattered most?
- One adjustment for next week.
```

**How to use it:**

Use the weekly note to set the rhythm for the week rather than individual days. The **Goals & Tasks** section is where you write the handful of things that would make this week feel complete. These lines can carry `@context(goal)` or `@context(task)` annotations just like the daily note.

The **Weekly Review** is designed to be filled in on Sunday evening. Two honest sentences here, consistently, will give you more self-knowledge than a hundred abandoned journaling apps.

---

### The Monthly Template (`t_monthly.md`)

The monthly note is a plain periodic note in the same shape as the daily and weekly ones. It is where you name the month's **big rocks** — the few things that would make the month count — and check that the commitments the month rests on carry a time.

```markdown
---
type: user_entry
pipeline: extract_activities
title: Month 2026-06
month_of: 2026-06
tags:
  - monthly
metadata:
  entry_kind: monthly
---

# 📅 Month 2026-06

## Monthly Focus

Theme, constraints, what you are watching.

## Big Rocks

- [ ] Set monthly focus @context(task) @when(2026-06-01)
- [ ] Mentor sync @context(event) @when(2026-06-10T10:00)
- [ ] Sprint — SKUEL.app chat alignment @context(task) @when(2026-06-12) @priority(1)

## Notes

## Monthly Review

- What moved?
- One adjustment for next month.
```

**How to use it:**

- **Big Rocks** — one checkbox line per big rock, with `@context(task)` and `@when(YYYY-MM-DD)` for the day it lands (add the clock time, `@when(YYYY-MM-DDThh:mm)`, when there is one; a fixed appointment is an `@context(event)`). These are the same annotations as the daily note (see [Part 3](#part-3--writing-activities-in-your-notes)): on sync each line becomes a Task with that due date, so the big rocks reach your calendar without being retyped.
- **Recurring commitments** — the morning meditation, the evening prep — are **Habits**, not lines in the monthly note. A habit's time lives on the Habit itself as a block of the day plus a duration: `preferred_time` (`morning`, `afternoon`, `evening`, `night`, …) and `duration_minutes`, set alongside the other fields of the habit's vault file (see [Part 4](#part-4--standalone-activity-yaml-files)) or in the **Schedule** section of the habit form in the app. Set it once and the calendar week view shows the habit on every day it recurs, reading its slot and length (`Morning · 20m`); the **Habit** swatch in the calendar legend shows or hides them.

The monthly template also includes a **Tasks plugin** query block that shows your upcoming p1 tasks for the next 30–45 days — a useful overview before starting the week.

**When to use it:** Open your monthly note at the start of each month, write the big rocks as tasks, and give any habit you mean to keep this month its time block. Then work from your daily notes day-to-day.

---

### The Quarterly and Yearly Templates (`t_quarterly.md`, `t_yearly.md`)

The two widest periods are plain periodic notes in the same shape as the others — the same frontmatter grammar, the same two line shapes that create entities. Only the period key differs: `quarter_of: 2026-Q3` and `year_of: 2026`.

```markdown
---
type: user_entry
pipeline: extract_activities
title: Quarter 2026-Q3
quarter_of: 2026-Q3
tags:
  - quarterly
metadata:
  entry_kind: quarterly
---

# 📅 Quarter 2026-Q3

## Quarterly Theme

The one thing this quarter is for.

## Big Rocks

- [ ] Close the deferred items that are genuinely in phase 📅 2026-09-30

## Constraints & Risks

What could take the quarter off course.

## Quarterly Review

- What moved?
- One adjustment for next quarter.
```

The yearly template is identical in shape, with `year_of: 2026`, `entry_kind: yearly`, and Milestones in place of Big Rocks.

**How to use them:**

- **Write the theme in prose.** Prose creates nothing — only checkbox lines and explicit `@context()` lines become entities (the parse contract, [Part 3](#part-3--writing-activities-in-your-notes)). A quarter's constraints and a year's standing commitments belong in prose precisely because they are thinking, not commitments the graph should track.
- **Keep the checkbox count low.** A quarter holds a handful of big rocks, not a backlog; the week and month notes are where work gets scheduled.
- **Reaching them in SKUEL:** the calendar has week and month views only, so the quarterly and yearly notes are reached through the **"Notes" picker** on the Week, Month and Today toolbars (one control, all five periods), or through the **period ladder** in any periodic note's sidebar — the "up" links that climb daily → weekly → monthly → quarterly → yearly.
- **Their planning panels are month-grouped.** Over three months or twelve, the panel sub-heads its rows by month so a long list stays navigable.

---

### The Quarterly Template (`t_quarterly.md`)

The quarterly template is intentionally minimal — a placeholder for higher-altitude thinking. Use it to write free prose about the quarter: themes, intentions, what you want to let go of. It doesn't participate in the `extract_activities` pipeline, so there's no special syntax to worry about.

---

## Part 3 — Writing Activities in Your Notes

### The @context() syntax

Any checkbox line in a note can become a SKUEL activity item. The key is the `@context()` tag:

```
- [ ] Call my accountant @context(task)
- [ ] Morning meditation @context(habit) @repeat(daily)
- [ ] Launch the new course @context(goal)
```

That's all that's required. SKUEL reads the `@context()` type and creates the right kind of item in your graph.

The six activity types map to how you already think about life:

| `@context()` | What it represents | Example |
|-------------|-------------------|---------|
| `task` | A one-off action you'll complete once | `- [ ] Schedule dentist appointment @context(task)` |
| `habit` | A repeated behavior you want to track | `- [ ] Morning pages @context(habit) @repeat(daily)` |
| `goal` | An outcome you're working toward | `- [ ] Reach 50 newsletter subscribers @context(goal)` |
| `event` | A scheduled occurrence | `- [ ] Workshop at Riverside School @context(event) @when(2026-07-15T14:00)` |
| `choice` | A decision worth recording | `- [ ] Choose to publish instead of polish @context(choice)` |
| `principle` | A value or rule that guides you | `- [ ] Small steps beat big bursts @context(principle)` |

### Optional tags

Add these to any line to give SKUEL more to work with:

| Tag | Meaning | Example |
|-----|---------|---------|
| `@when(YYYY-MM-DDThh:mm)` | Scheduled time | `@when(2026-07-01T09:00)` |
| `@repeat(daily)` | Recurrence | `@repeat(weekly:Mon,Wed,Fri)` |
| `@priority(N)` | Priority 1–5 (1 = highest) | `@priority(1)` |
| `@duration(Xm)` | How long it takes | `@duration(45m)` |
| `@energy(type)` | Energy type needed | `@energy(focus)` or `@energy(creative,social)` |

A fully annotated task line looks like this:

```
- [ ] Write the chapter on habits @context(task) @when(2026-07-02T09:00) @priority(1) @duration(90m) @energy(focus,creative)
```

You don't need all of these. Even `@context(task)` alone is enough for SKUEL to track it.

### A real daily note, filled in

```markdown
---
type: user_entry
pipeline: extract_activities
title: 2026-06-24
date: 2026-06-24
tags: [daily]
metadata:
  entry_kind: daily
---

# 📅 2026-06-24

## Focus

Ship the article draft and prep for Thursday's call.

## Tasks

- [ ] Finish and send article draft @context(task) @priority(1) @energy(focus) @duration(2h)
- [ ] Morning meditation @context(habit) @repeat(daily) @duration(20m) @energy(rest,spiritual)
- [ ] Prep notes for Thursday call @context(task) @priority(2) @duration(30m)
- [ ] Review weekly goals @context(habit) @repeat(weekly:Tue) @duration(10m)

## Notes

Had a good conversation with Sara about the course structure. She pointed out that
the onboarding section is too long — cut it by half.

## End of Day

- Finished the draft. Call prep not done — push to tomorrow.
- One adjustment: schedule focused writing blocks earlier in the day.
```

When you sync this note, SKUEL creates:
- Two Task items (article draft, call prep)
- Two Habit items (morning meditation, weekly review)
- A UserEntry for the whole note (including the prose notes and retrospective)

---

## Part 4 — Standalone Activity YAML Files

For activities that aren't part of a daily note — a goal you're setting for the quarter, a principle you want to live by, a habit you want to start tracking from today — write a standalone YAML file in your Obsidian vault. The vault sync at **[/submissions/sync](/submissions/sync)** will pick it up on the next sync.

### Quick examples for each type

**Task**
```yaml
type: Task
uid: task.write-chapter-3
title: Write Chapter 3 — Habits
status: active
priority: high
```

**Goal**
```yaml
type: Goal
uid: goal.finish-book-draft
title: Finish the book draft by August
goal_type: project
timeframe: quarterly
status: active
```

**Habit**
```yaml
type: Habit
uid: habit.morning-meditation
title: Morning Meditation (20 min)
polarity: build
category: mindfulness
difficulty: easy
recurrence_pattern: daily
status: active
```

**Event**
```yaml
type: Event
uid: event.riverside-workshop-2026-07-15
title: Workshop at Riverside School
status: scheduled
```

**Choice**
```yaml
type: Choice
uid: choice.publish-over-perfect
title: Publish now rather than wait for perfect
choice_type: binary
status: active
```

**Principle**
```yaml
type: Principle
uid: principle.small-steps
title: Small Steps Beat Big Bursts
category: personal
strength: core
status: active
```

### Connecting activities to knowledge

Once you have learning content in SKUEL (PathSteps and Knowledge Units), you can link your activities to it. This is how SKUEL measures how much you're *living* the knowledge, not just reading about it:

```yaml
type: Habit
uid: habit.morning-meditation
title: Morning Meditation (20 min)
polarity: build
category: mindfulness
status: active
connections:
  reinforces_knowledge:
    - ps.mindfulness.breath-awareness-basics
```

Each connection type carries a different weight. Habits that reinforce knowledge (you practice something every day) score highest; tasks and events that apply knowledge score slightly lower. The substance score on a knowledge item climbs as you actually live it.

See the [YAML Authoring Guide](YAML_AUTHORING_GUIDE.md) for a full reference of connection types, status values, and every enum-governed field.

---

## Part 5 — The VaultBridge: Keeping Obsidian and SKUEL in Sync

### What the VaultBridge does

The VaultBridge creates a live connection between your Obsidian vault and SKUEL. It works in both directions:

- **Obsidian → SKUEL:** Your periodic notes are read, journal entries are created, and activity lines with `@context()` tags are extracted into your graph.
- **SKUEL → Obsidian:** Tasks that already exist in SKUEL (created via the app, via YAML upload, or extracted from a previous note) are written into your daily notes with a permanent ID. Completion flows this direction only: complete the task in SKUEL and the next sync writes `[x]` + `✅ date` into your note — checking it off in Obsidian does not propagate back.

### Task IDs: the link between the two worlds

When SKUEL writes a task back into your Obsidian vault, it appends a short ID to the task line:

```
- [ ] Write Chapter 3 — Habits 🆔 sk_a7c2f1
```

The `🆔 sk_XXXXXX` token is the permanent join key. It's compatible with the **obsidian-tasks plugin**. SKUEL is responsible for minting these IDs — you don't need to type them yourself. Once the ID is there, SKUEL can always match that line to the right task, even if you edit the title or move the note.

### Completing a task: do it in SKUEL

Checkbox state is outbound-only. For a task line that carries a `🆔` (one SKUEL wrote out or has already extracted), checking the box in Obsidian does **not** update SKUEL — the sync deliberately skips lines it already tracks, so the check stays local to your note. Complete the task in SKUEL instead; the next sync marks the line done in your note with the obsidian-tasks done syntax:

```
- [x] Write Chapter 3 — Habits ✅ 2026-06-24 🆔 sk_a7c2f1
```

The `✅ YYYY-MM-DD` token is the completion date, written by SKUEL from the task's completion stamp. One exception runs inbound: a checkbox line you author *already checked*, before it has a `🆔`, is ingested on first sync as a completed task carrying the `✅` date.

### Running a sync at /submissions/sync

Go to **[/submissions/sync](/submissions/sync)** and click **Sync from Obsidian**.

SKUEL reads all the changed notes in your vault, processes them through the `extract_activities` pipeline, creates or updates your journal entries, and writes any new task IDs back into the vault files.

**First-run consent:** The first time you sync, SKUEL will ask for your permission before it writes anything back into your vault files. This is a one-time gate. Once you click "Allow and sync", subsequent syncs happen silently. You can see the consent prompt text on the sync page — it explains exactly what will be written and in what format.

### Field authority: who owns what

The VaultBridge follows a clear rule about which side is the source of truth for each field:

| Field | Who controls it |
|-------|----------------|
| Task title and description | Obsidian (you edit in your notes) |
| Checkbox status (done/not done) | SKUEL, both directions outbound — completing in SKUEL writes `[x]` + `✅` to your note, and re-opening it removes them again, restoring the line exactly as it was. It only takes back its OWN write: a box you tick yourself (no `✅` date) is left alone. A vault-side check or un-check of a 🆔 line is still not read back |
| Due dates, priority, tags | Obsidian |
| `🆔` ID | SKUEL (minted and written once) |
| History, relationships, ZPD scores | SKUEL only |

The Obsidian-owned rows apply when a line is **first extracted**. Once a line carries a `🆔`, later vault-side edits to it (title, dates, checkbox) are skipped by the sync — if you check off a 🆔 line in Obsidian, SKUEL's status is unaffected. Make changes in SKUEL — the sync writes checkbox state outbound in both directions: a completion adds `[x]` + `✅`, and re-opening the task takes them back off. A box you ticked yourself is never un-ticked for you.

---

## Part 6 — Your Daily Workflow: A Full Example

Here is what a complete day looks like using all three parts together.

---

### Morning

**8:00 am — Voice memo on your walk**

You're thinking out loud. Record two minutes on your phone about what you want to get done today and why one of those things feels difficult.

When you're back at your desk: go to **[/journals](/journals)**, upload the audio file, and let SKUEL transcribe it. You don't need to do anything with it right now — it's in the system. Come back later in the day (or the next morning) to read the transcription and optionally request an AI response.

---

**8:15 am — Open today's daily note in Obsidian**

The Periodic Notes plugin creates a fresh copy of `t_daily.md` with today's date. Write your focus line first — one sentence. Then move to the Tasks section and write your day:

```markdown
## Focus

Get the outline finished so the writing block tomorrow is unblocked.

## Tasks

- [ ] Write outline for Part 2 @context(task) @priority(1) @energy(focus) @duration(90m)
- [ ] Morning meditation @context(habit) @repeat(daily) @duration(20m)
- [ ] Reply to the three backlogged emails @context(task) @energy(light) @duration(20m)
- [ ] Weekly planning review @context(habit) @repeat(weekly:Tue) @duration(15m)
```

You don't need to open SKUEL at all during this step. Author in Obsidian, where you're comfortable.

---

### During the day

**Work from your Obsidian note.** Check off tasks as you complete them:

```
- [x] Write outline for Part 2 ✅ 2026-06-24
```

If you're using the obsidian-tasks plugin, it inserts the `✅ date` token automatically when you check the box.

---

### Evening

**6:00 pm — Sync**

Go to **[/submissions/sync](/submissions/sync)** and click **Sync from Obsidian**.

SKUEL reads today's daily note:
- Creates a journal entry for the whole note (Focus + Notes + End of Day prose)
- Extracts the Task and Habit lines into your activity graph
- Writes `🆔 sk_XXXXXX` IDs into any new task lines in your vault files
- Reads the `✅` completion markers and marks those tasks complete in SKUEL

The sync usually takes a few seconds.

---

**6:05 pm — Fill in the End of Day section**

Back in Obsidian:

```markdown
## End of Day

- Got the outline done — it's solid. Emails done too.
- One adjustment: the weekly review kept getting pushed. Block 30 min on the calendar.
```

This retrospective is stored in your journal entry. Over months, patterns become visible.

---

**Optional: check your journal entries**

Go to **[/journals/browse](/journals/browse)** to see today's transcription from the morning voice memo. If you want a reflective response, click **Get AI response**. The response might surface a connection between what you said this morning and a habit you've been building, or ask a clarifying question you hadn't thought to ask yourself.

---

### Occasionally: write a YAML file

When you're setting a new goal for the quarter, or want to define a principle that's been crystallizing, write a standalone YAML file in your vault. The next sync at **[/submissions/sync](/submissions/sync)** will bring it into SKUEL. This doesn't have to happen every day — it's the tool for the more deliberate, structured layer of your life.

---

## Quick Reference

| What you want to do | Where to go |
|--------------------|------------|
| Upload a voice memo or text journal | [/journals](/journals) |
| Browse journal entries and get AI responses | [/journals/browse](/journals/browse) |
| Sync Obsidian vault with SKUEL (primary data path) | [/submissions/sync](/submissions/sync) |
| Submit a completed exercise worksheet | [/submit](/submit) |

| Template | Cadence | Primary purpose |
|----------|---------|----------------|
| `t_daily.md` | Daily | Task capture, focus, retrospective |
| `t_weekly.md` | Weekly | Weekly intentions, goals, review |
| `t_monthly.md` | Monthly | Big rocks as tasks; commitments as Habits |
| `t_quarterly.md` | Quarterly | High-altitude reflection (free prose) |

| @context() type | Use for |
|----------------|---------|
| `task` | One-off completable actions |
| `habit` | Recurring behaviors to track |
| `goal` | Outcomes you're working toward |
| `event` | Calendar items with a specific time |
| `choice` | Decisions you're recording |
| `principle` | Values or rules you live by |

---

## Related Documentation

- [YAML Authoring Guide](YAML_AUTHORING_GUIDE.md) — full field reference for YAML activity files, connections system, and curriculum content
- [Activity DSL Usage Guide](../dsl/DSL_USAGE_GUIDE.md) — complete `@context()` syntax with advanced examples
- [ADR-070 — VaultBridge Architecture](../decisions/ADR-070-bidirectional-vault-bridge.md) — how the sync works under the hood
- [Unified Ingestion Guide](../patterns/UNIFIED_INGESTION_GUIDE.md) — how files are processed on the way into SKUEL
