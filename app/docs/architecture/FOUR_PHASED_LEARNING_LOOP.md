---
title: Four-Phased Learning Loop
updated: 2026-03-02
status: current
category: architecture
related:
- FEEDBACK_ARCHITECTURE.md
- SUBMISSION_FEEDBACK_LOOP.md
- LEARNING_EXPERIENCE_ARCHITECTURE.md
- FOURTEEN_DOMAIN_ARCHITECTURE.md
---

# The Four-Phased Learning Loop

> "Knowledge is learned by doing, evaluated by responding, and refined by reflecting."

The Four-Phased Learning Loop is the **core purpose of SKUEL**. Every feature in the
codebase either feeds this loop, supports its infrastructure, or should be questioned.

This document is the entry point. It names the loop, states its two tracks, defines each
phase, and cross-references detailed documentation. It does not duplicate what those docs
already say.

---

## The Loop

```
╔══════════════════════════════════════════════════════════════╗
║              FOUR-PHASED LEARNING LOOP                       ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  CURRICULUM TRACK (artifact-based)                           ║
║  ─────────────────────────────────────────────────────────   ║
║  [Ku] ──→ [Exercise] ──→ [Submission/Journal] ──→ [Feedback] ║
║   ↑             ↓              ↑↓                     ↓      ║
║  admin       teacher        student               teacher/AI  ║
║  creates     assigns     uploads/revises          assesses    ║
║                              └──── revision cycle ────┘      ║
║                                                              ║
║  ACTIVITY TRACK (aggregate-based)                            ║
║  ─────────────────────────────────────────────────────────   ║
║  [Tasks + Goals + Habits + Events + Choices + Principles]    ║
║       + [KU mastery + LP progress + LS progress]             ║
║                    ↓ (over time window)                      ║
║             [Activity Report] ←── AI or Admin               ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

---

## Two Tracks

**The loop has two entry points.** Both close the loop: work is done, the system responds.

| Track | Entry Point | Feedback Entity | Who Responds |
|-------|------------|-----------------|--------------|
| **Curriculum** | Student uploads a file against an Exercise | `SUBMISSION_FEEDBACK` | Teacher or AI (via Exercise instructions) |
| **Activity** | User's lived practice over a time window | `ACTIVITY_REPORT` | AI (scheduled or on-demand) or Admin |

Activity Domains are **equal** entry points — not secondary. A user's Tasks, Goals, Habits,
Events, Choices, and Principles receive the same feedback infrastructure as curriculum work.
The mechanism differs, but the loop closes either way.

---

## Phase 1: Ku — The Knowledge Unit

**What:** Atomic curriculum content. A single "brick" of knowledge, admin-created and
shared across all users. Every Exercise is grounded in one or more Ku nodes.

**EntityType:** `EntityType.KU`
**Loop role:** The *why* — the knowledge the loop exists to transmit.

**See:** [LEARNING_EXPERIENCE_ARCHITECTURE.md](/docs/architecture/LEARNING_EXPERIENCE_ARCHITECTURE.md)
— KU mastery, substance scoring, and knowledge progress tracking.

---

## Phase 2: Exercise — The Assignment

**What:** The teacher's directive. Instructions for what students should produce, with an
LLM prompt embedded for AI-assisted feedback. Two scopes: `PERSONAL` (self-directed) and
`ASSIGNED` (classroom with a Group target and due date).

**EntityType:** `EntityType.EXERCISE`
**Loop role:** The *how* — operationalizes Ku into a concrete task. The `instructions`
field serves double duty: directive for the student AND prompt for the AI when generating
`SUBMISSION_FEEDBACK`.

**See:** [SUBMISSION_FEEDBACK_LOOP.md](/docs/architecture/SUBMISSION_FEEDBACK_LOOP.md)
— Exercise pipeline and teacher workflow.

---

## Phase 3: Submission — The Student's Work

**What:** The student's artifact. An uploaded file (audio, text, image) that is processed
into `processed_content` — the evaluable form. Two leaf types: `SUBMISSION` (student
uploads) and `JOURNAL` (admin uploads for AI-only processing).

**EntityType:** `EntityType.SUBMISSION` or `EntityType.JOURNAL`
**Loop role:** The *evidence* — the student's demonstration of engagement with Ku.
Without it, the Curriculum Track has no student voice.

**See:** [SUBMISSION_FEEDBACK_LOOP.md](/docs/architecture/SUBMISSION_FEEDBACK_LOOP.md)
— full pipeline from upload to sharing and teacher review queue.

---

## Phase 4: Feedback — The Response

**What:** The evaluation. Two structurally distinct entities cover the two tracks.
Both say "here is what your work means."

### 4a. SUBMISSION_FEEDBACK — Response to an Artifact

**What:** Evaluation of a specific `SUBMISSION` or `JOURNAL`. One artifact in, one
`SubmissionFeedback` node out. Two sources: teacher writes (`HUMAN`) or AI evaluates
via the Exercise's `instructions` field (`LLM`).

**EntityType:** `EntityType.SUBMISSION_FEEDBACK`
**Structural position:** Leaf domain — fits the standard 4-layer architecture cleanly
(`FeedbackOperations` protocol → `SubmissionsBackend` → `FeedbackService` / `SubmissionsCoreService`).

### 4b. ACTIVITY_REPORT — Response to Activity Patterns

**What:** Response to a user's aggregate activity over a time window. Not tied to a
specific artifact — it responds to *patterns*. Three sources: scheduled system (`AUTOMATIC`),
on-demand AI (`LLM`), or admin-written (`HUMAN`).

**EntityType:** `EntityType.ACTIVITY_REPORT`
**Structural position:** Cross-domain aggregator — sits above the domain backends by design.
Reads across all 6 Activity Domains **and** the Curriculum track (KU mastery, LP progress,
LS progress) in a single MEGA_QUERY round-trip.

**See:** [FEEDBACK_ARCHITECTURE.md](/docs/architecture/FEEDBACK_ARCHITECTURE.md)
— canonical taxonomy, all services, API routes, ProcessorType table, graph patterns.

---

## How UserContext Feeds the Loop

The Activity Track's data source is `UserContext.build_rich()` — the MEGA_QUERY extended
with six activity-window CALL{} blocks (one per Activity Domain) plus curriculum state.

```
                       MEGA_QUERY
                           │
                  build_rich(window="30d")
                           │
            ┌──────────────┼──────────────────────┐
            │              │                      │
  context.entities_rich    │    context.knowledge_units_rich
  (6 Activity Domains)     │    context.enrolled_paths_rich
                           │    context.active_learning_steps_rich
                           │
              ProgressFeedbackGenerator.generate()
                           │
                ActivityReport (LLM or AUTOMATIC)
```

**Architectural history:** `ActivityDataReader` was built as a separate query layer to
gather activity data for the loop. It was deleted in March 2026 after recognizing that
`UserContext.build_rich()` (MEGA_QUERY) already fulfills this role with a single Neo4j
round-trip and a richer result (it also includes curriculum state).

**One Path Forward:** The loop's data layer is `UserContextBuilder.build_rich()`. There
is no separate activity query layer. Both `ProgressFeedbackGenerator` and
`ActivityReportService` inject `context_builder: UserContextBuilder`.

---

## The ProcessorType Discriminator

`ProcessorType` distinguishes who produced a feedback entity — not a separate entity type.
New feedback sources add `ProcessorType` values; they do not create new EntityTypes.

| ProcessorType | Who | Applies To |
|---|---|---|
| `HUMAN` | Teacher | `SUBMISSION_FEEDBACK` |
| `HUMAN` | Admin | `ACTIVITY_REPORT` |
| `LLM` | AI via Exercise instructions | `SUBMISSION_FEEDBACK` |
| `LLM` | AI on-demand | `ACTIVITY_REPORT` |
| `AUTOMATIC` | Scheduled system | `ACTIVITY_REPORT` |

**Import:** `from core.models.enums.entity_enums import ProcessorType`

---

## See Also

| Document | What It Covers |
|----------|---------------|
| [FEEDBACK_ARCHITECTURE.md](/docs/architecture/FEEDBACK_ARCHITECTURE.md) | Canonical feedback reference — all services, APIs, graph patterns, ProcessorType taxonomy |
| [SUBMISSION_FEEDBACK_LOOP.md](/docs/architecture/SUBMISSION_FEEDBACK_LOOP.md) | Curriculum Track pipeline — Exercise → Submission → teacher review |
| [LEARNING_EXPERIENCE_ARCHITECTURE.md](/docs/architecture/LEARNING_EXPERIENCE_ARCHITECTURE.md) | Phase 1 depth — KU mastery, substance scoring, knowledge progress |
| [FOURTEEN_DOMAIN_ARCHITECTURE.md](/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md) | How the loop fits the 14-domain architecture |
| [ADR-038: Content Sharing](/docs/decisions/ADR-038-content-sharing-model.md) | Three-level visibility model for submissions |
| [ADR-040: Teacher Assignment Workflow](/docs/decisions/ADR-040-teacher-assignment-workflow.md) | ASSIGNED exercise, auto-sharing, teacher review queue |
| `.claude/skills/learning-loop/SKILL.md` | Developer guide — implementation details, service architecture, anti-patterns |
