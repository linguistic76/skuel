---
title: Four-Phase Learning Loop
updated: 2026-04-18
status: current
category: architecture
related:
- REPORT_ARCHITECTURE.md
- ENTITY_TYPE_ARCHITECTURE.md
related_skills: [learning-loop]
---

# The Four-Phase Learning Loop

> "Knowledge is learned by doing, evaluated by responding, and refined by reflecting."

The Four-Phase Learning Loop is the **core purpose of SKUEL**. Every feature in the
codebase either feeds this loop, supports its infrastructure, or should be questioned.

Learning is not consuming content. Learning is what happens when knowledge changes how you
act, decide, and live. SKUEL models this through four phases: **how you practise**
(Exercise), **what you produce** (UserEntry), **what the system says back**
(EntryReport), and **how the teacher guides revision** (RevisedExercise). PathStep
is the *curriculum anchor* — the knowledge the loop exists to transmit — linked via
`(PathStep)-[:HAS_EXERCISE]->(Exercise)` (denormalized as `Exercise.path_step_uid` for
PERSONAL scope). It sits outside the cycle as context, not as a phase.

Every layer is a frozen Python dataclass. Every connection is a Neo4j graph relationship.
Every measurement flows from real user behaviour, not self-reported progress.

---

## The Loop

```
╔══════════════════════════════════════════════════════════════════════════╗
║                     FOUR-PHASE LEARNING LOOP                             ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  CURRICULUM TRACK (artifact-based)                                       ║
║                                                                          ║
║  (anchor)                                                                ║
║  [PathStep] ──HAS_EXERCISE──▶ [Exercise] ──▶ [UserEntry] ──▶ [EntryReport]
║   admin                       teacher       student            teacher/AI║
║   creates                     assigns       produces           responds  ║
║                                                                 │        ║
║                                                                 ▼        ║
║                                                        [RevisedExercise] ║
║                                                         teacher creates  ║
║                                                        targeted revision ║
║                                                                 │        ║
║                                                                 ▼        ║
║                                              [UserEntry v2] ──▶ ...      ║
║                                                                          ║
║   Phases: 1 Exercise → 2 UserEntry → 3 EntryReport → 4 RevisedExercise║
║   PathStep is the curriculum anchor, not a phase.                        ║
║                                                                          ║
║  ACTIVITY TRACK (aggregate-based)                                        ║
║  ────────────────────────────────────────────────────────────────────    ║
║  [Tasks + Goals + Habits + Events + Choices + Principles]                ║
║       + [KU mastery + LP progress + PS progress]                         ║
║                    ↓ (over time window)                                  ║
║             [ActivityReport] ←── AI or Admin                             ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

## Two Tracks

**The loop has two entry points.** Both close the loop: work is done, the system responds.

| Track | Entry Point | Report Entity | Who Responds |
|-------|------------|-----------------|--------------|
| **Curriculum** | Student uploads a file against an Exercise | `ENTRY_REPORT` | Teacher or AI (via Exercise instructions); the AI report is triggered by the submission owner (self-serve, `POST /api/exercises/report`, ADR-043 tier-gated) or a teacher |
| **Activity** | User's lived practice over a time window | `ACTIVITY_REPORT` | AI (scheduled or on-demand) or Admin |

Activity Domains are **equal** entry points — not secondary. A user's Tasks, Goals, Habits,
Events, Choices, and Principles receive the same feedback infrastructure as curriculum work.
The mechanism differs, but the loop closes either way.

> **"Submission" — conceptual vs structural.** This document uses "submission" in two
> senses that must not be conflated. The **conceptual submission** in the Activity Track is
> the user's lived practice across all six Activity Domains over a time window — it is
> implicit, never uploaded, and produces an `ACTIVITY_REPORT`. The **structural submission**
> (`EntityType.USER_ENTRY`) is a file a student explicitly uploads against an Exercise in the
> Curriculum Track and produces an `ENTRY_REPORT`. `ActivityReport` inherits
> `UserOwnedEntity` directly — it has no file fields. `UserEntry` carries file fields and a
> `pipeline` discriminator (ADR-054). When reading code that touches both tracks, keep this
> distinction in mind: the loop closes differently in each track even though the pedagogical
> concept is the same.

---

## Curriculum Anchor: PathStep — The Teaching Composition

> **PathStep is knowledge. Exercise is applied knowledge. This hierarchy is fundamental
> to SKUEL: the loop exists to transmit what PathStep carries, and Exercise is the
> instrument of transmission.**

PathStep and Exercise are not peers. Exercise is subordinate to PathStep — the same
structural relationship as sub-goal under parent goal. See
[CURRICULUM_GROUPING_PATTERNS.md](/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md)
for the full hierarchy.

**What:** THE curriculum content entity — composes atomic Kus into coherent narrative and
sits within LearningPaths. Admin-created and shared across all users. PathStep-anchored
Exercises link via `(PathStep)-[:HAS_EXERCISE]->(Exercise)` (anchored PERSONAL exercises
also denormalize `Exercise.path_step_uid`; CURRICULUM exercises anchor via `exercise_uids:`
in PathStep YAML; unanchored PERSONAL templates are free-standing in the user's library).
PathSteps compose atomic Kus via `(PathStep)-[:USES_KU]->(Ku)`.

**Historical note:** The former `Lesson` entity type was merged into `PathStep` in April 2026.
PathStep is now the single curriculum content entity; there is no separate Lesson layer.

**EntityType:** `EntityType.PATH_STEP`
**Loop role:** The *why* — the knowledge the loop exists to transmit. PathStep is the
curriculum anchor, not a phase of the loop; it supplies context the four phases cycle against.
**See:** [ASKESIS_PEDAGOGICAL_ARCHITECTURE.md](/docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md) — Askesis scaffolds PathStep discovery via ZPD-aware Socratic dialogue.
**See:** [PATHSTEP_CONTENT_ARCHITECTURE.md](/docs/architecture/PATHSTEP_CONTENT_ARCHITECTURE.md) — body content storage via `HAS_CONTENT`.

### PathStep ↔ Exercise Storage Design

The connection between PathStep and Exercise is stored in two forms simultaneously — one for
each lookup direction. Understanding why both exist (and why PathStep has no `exercise_uid`
property) is important for anyone working in this area.

**From PathStep → Exercise: the graph edge**

```
(PathStep)-[:HAS_EXERCISE]->(Exercise)
```

This is the authoritative link. In Neo4j, following a direct relationship edge is a constant-time
pointer lookup — it is not a table scan. Asking "which exercises belong to this PathStep?"
traverses `HAS_EXERCISE` outgoing edges. No property on PathStep is needed because the edge
*is* the fast lookup.

PathStep also has no `exercise_uid` property (singular) because the relationship is
one-to-many: a single PathStep can anchor multiple Exercises. A scalar property would break
with the second exercise; the graph edge handles any cardinality naturally.

**From Exercise → PathStep: the denormalized property**

```
Exercise.path_step_uid  (stored on the Exercise node itself)
```

This covers the reverse direction without traversal. Asking "which PathStep does this Exercise
belong to?" reads `path_step_uid` directly off the Exercise node — no graph hop required.
This property is only present for anchored `ExerciseScope.PERSONAL` exercises — the anchor is
optional, and unanchored personal templates (the /submit save-template flow) carry neither the
property nor the edge.

**The dual-write**

When an anchored PERSONAL Exercise is created, `ExerciseService.create()` writes both forms in
one operation:

1. The `path_step_uid` property is stored on the Exercise node (forward: Exercise → PathStep)
2. The `HAS_EXERCISE` edge is created from PathStep to Exercise (forward: PathStep → Exercise)

Both are written at creation time. Neither is derived lazily at read time. If either write
fails, the creation fails. The result is that both lookup directions are always available
without extra queries.

| Question | Storage used | Mechanism |
|---|---|---|
| Which exercises does this PathStep have? | `HAS_EXERCISE` edge | Graph traversal (constant-time pointer) |
| Which PathStep does this Exercise belong to? | `Exercise.path_step_uid` | Direct node property (no traversal) |

**Contrast with Activity Domain DERIVED fields**

Activity Domain models use a different pattern for cross-domain UID fields. For example,
`Task.reinforces_habit_uid` and `Habit.supports_goal_uid` are marked `# DERIVED FROM EDGE`
— they are populated by an enrich step at read time and never stored as node properties.
The Exercise/PathStep dual-write is a deliberate divergence from this pattern: an anchored
PERSONAL exercise is 1:1 with its PathStep and is queried from both directions in the learning
loop, so the cost of materialising the reverse pointer at write time is worth the simpler reads.

### Layer 1: What You Can Learn

**File:** `core/models/pathways/path_step.py`

A PathStep is a frozen dataclass — immutable once created, like a published textbook
page:

```
PathStep (frozen dataclass, inherits Curriculum → Entity)
├── Identity:    uid, title, description, domain
├── SEL Lens:    sel_category (SELCategory | None) — optional filter, not inherent
├── Difficulty:  learning_level, estimated_time_minutes, difficulty_rating (0.0-1.0)
├── Quality:     quality_score, complexity, semantic_links
└── Substance:   times_applied_in_tasks, times_practiced_in_events, ...
```

**Atomic Kus:** PathSteps compose atomic `Ku` entities (`EntityType.KU`, extends `Entity`
directly — lightweight ontology nodes in `core/models/ku/ku.py`). The substance and mastery
tracking described below applies to PathSteps; atomic Kus are reference nodes.

#### SEL Navigation Lens

A PathStep *may* carry an `sel_category` — a classification into the Social Emotional Learning
framework. SEL is a navigation lens over KUs, not an inherent property of every piece of
knowledge. `sel_category` is typed as `SELCategory | None` with a default of `None`; no
silent default is injected.

| SELCategory | Human Meaning |
|---|---|
| `SELF_AWARENESS` | Understanding your emotions, values, strengths |
| `SELF_MANAGEMENT` | Managing emotions and achieving goals |
| `SOCIAL_AWARENESS` | Understanding and empathising with others |
| `RELATIONSHIP_SKILLS` | Building healthy relationships |
| `RESPONSIBLE_DECISION_MAKING` | Making ethical, constructive choices |

The `SELCategory` enum lives in `core/models/enums/learning_enums.py`. It carries
presentation logic: `get_icon()`, `get_color()`, `get_description()`.

The `PsAdaptiveService` uses `sel_category` as a filter — `find_by(sel_category=category.value)` —
to surface PathSteps grouped by SEL competency. PathSteps without a meaningful classification
simply won't appear in category-filtered views: not all knowledge fits neatly into an SEL lens.

#### How PathSteps Are Born: Markdown to Graph

PathSteps originate as Markdown files with YAML frontmatter in the Obsidian vault
(default `/home/mike/0bsidian/0vault/`, configurable via `INGESTION_PATH`). The ingestion
pipeline (`core/services/ingestion/`) parses the frontmatter, including the optional
`sel_category` field.

Once in Neo4j, PathSteps connect through graph relationships:

```cypher
(p1:PathStep)-[:REQUIRES_KNOWLEDGE]->(p2:PathStep)  // Prerequisites
(p1:PathStep)-[:ENABLES_KNOWLEDGE]->(p2:PathStep)   // What mastering this unlocks
(moc:Entity)-[:ORGANIZES]->(p:PathStep)              // MOC grouping (non-linear)
(p:PathStep)-[:USES_KU]->(ku:Ku)                     // Composes atomic Kus
(lp:LearningPath)-[:HAS_STEP]->(p:PathStep)          // Ordered within a path
```

### Layer 2: How You're Learning It — Mastery Tracking

**File:** `core/models/pathways/mastery.py`

When a user interacts with a PathStep, pedagogical relationships (`VIEWED`, `IN_PROGRESS`,
`MASTERED`, `BOOKMARKED`, `MARKED_AS_READ`) are created between `:User` and `:PathStep`. The
`Mastery` dataclass models what that relationship means:

```
Mastery (frozen dataclass)
├── Identity:    uid, user_uid, knowledge_uid
├── Mastery:     mastery_level (MasteryLevel), mastery_score (0.0-1.0)
├── Confidence:  confidence_score (0.0-1.0)
├── Velocity:    learning_velocity (LearningVelocity), time_to_mastery_hours
├── Evidence:    mastery_evidence, last_reviewed, last_practiced
└── Preferences: preferred_learning_method (ContentPreference)
```

`MasteryLevel` tracks a seven-stage progression that mirrors how humans actually learn:

```
UNAWARE → INTRODUCED → FAMILIAR → PROFICIENT → ADVANCED → EXPERT → MASTERED
```

The `PsMasteryService` (`core/services/ps/ps_mastery_service.py`) manages pedagogical
progression: `VIEWED` → `IN_PROGRESS` → `MASTERED`. KU mastery publishes `KnowledgeMastered`,
which triggers the learning progress event chain — see
[LEARNING_PROGRESS_EVENT_CHAIN.md](/docs/architecture/LEARNING_PROGRESS_EVENT_CHAIN.md).

`LearningVelocity` tracks how fast a user learns in different domains — not as a judgment
but as data for personalisation. A user who learns yoga slowly but Python quickly gets
different time estimates for each.

`LearningPreference` captures what works for a specific person: preferred content types,
session duration, whether they learn better with examples, top-down vs bottom-up approach.
This profile evolves from actual learning patterns, not questionnaires.

### Layer 3: Whether It's Changing Your Life — Substance Scoring

**File:** `core/models/pathways/path_step.py`

The `substance_score()` method on the `PathStep` dataclass measures how knowledge is **lived**,
not just consumed:

| Application Type | Weight | Max | What It Measures |
|---|---|---|---|
| Habits | 0.10/each | 0.30 | Lifestyle integration — knowledge becomes behaviour |
| Journals | 0.07/each | 0.20 | Metacognition — user reflects on what they learned |
| Choices | 0.07/each | 0.15 | Decision wisdom — knowledge informs real decisions |
| Events | 0.05/each | 0.25 | Practice — dedicated time applying knowledge |
| Tasks | 0.05/each | 0.25 | Application — knowledge used in real projects |

Substance decays over time using exponential decay with a 30-day half-life (`_decay_weight()`).
Knowledge never fully disappears (floor at 0.2), but it fades without practice — exactly like
human memory.

The substance fields on the `PathStep` model (`times_applied_in_tasks`,
`times_practiced_in_events`, etc.) are updated via the event-driven architecture. When a user
completes a task that references a PathStep, `PsService` handles the
`knowledge.applied_in_task` event and atomically increments the counter in Neo4j.

### The Adaptive Service: Connecting the Layers

**File:** `core/services/ps/ps_adaptive_service.py`

`PsAdaptiveService` answers the question: **"What should this person learn next?"**

**Personalised curriculum delivery** (`get_personalized_curriculum`):

```
1. Load user's learning intelligence (masteries, paths, velocity)
2. Query all PathSteps in the requested SEL category
3. Filter by readiness:
   - Not already mastered
   - Prerequisites met (via REQUIRES_KNOWLEDGE graph traversal)
   - Appropriate for user's current level
4. Rank by learning value:
   - Enables many future PathSteps (×10) — high leverage
   - Matches preferred difficulty (×20) — flow state
   - Fits available time (×15) — practical
   - Foundational / no prerequisites (×5) — unblocked
   - Quick win (×10) — momentum
5. Return top N recommendations
```

**`CurriculumProgress`** (`core/models/pathways/learning_progress.py`) — a frozen snapshot of
a user's progress through one SEL category, tracking path-step-level completion.

`determine_level()` maps completion to `LearningLevel`:
0–24% → BEGINNER · 25–49% → INTERMEDIATE · 50–74% → ADVANCED · 75–100% → EXPERT

`needs_attention()` returns `True` if a user started a category but hasn't touched it in
7+ days — a signal for the UI.

**`LearningJourney`** (`core/models/pathways/learning_progress.py`) — progress across all
five SEL categories:

```
LearningJourney
├── user_uid
├── category_progress: dict[SELCategory, CurriculumProgress]
└── overall_completion: float (0-100)
```

`get_next_recommended_category()` implements pedagogical ordering:
1. Self-Awareness first (foundation of all SEL)
2. Self-Management second (builds on self-awareness)
3. Whichever category has least progress (balanced growth)

`is_well_rounded()` checks if no category is more than 30% behind the average — the system
values breadth alongside depth.

### UI: Making Learning Visible

The PathStep detail page (`/explore/ps/{uid}`) is the primary surface. A flat index at
`/path-steps` lists enrolment-aware PathSteps (Start / In Progress / Mastered). Adaptive
curriculum recommendations and SEL journey views are composed through
`ui/patterns/curriculum_adaptive.py` and the explore sidebar graph.

**Routes:**

| Route | Purpose |
|---|---|
| `GET /explore/ps/{uid}` | PathStep detail page — learning loop anchor |
| `GET /path-steps` | Flat PathStep index |
| `GET /path-steps/get?uid=` | PathStep reading page |
| `GET /api/path-steps/*` | PathStep API (CRUD + intelligence) |

---

## Phase 1: Exercise — The Assignment

**What:** The teacher's directive. Instructions for what students should produce, with an
LLM prompt embedded for AI-assisted feedback. Two scopes: `PERSONAL` (self-directed) and
`ASSIGNED` (classroom with a Group target and due date).

**EntityType:** `EntityType.EXERCISE`
**Loop role:** The *how* — operationalises PathStep content into a concrete task. The `instructions`
field serves double duty: directive for the student AND prompt for the AI when generating
`ENTRY_REPORT`.

**See:** [REPORT_ARCHITECTURE.md](/docs/architecture/REPORT_ARCHITECTURE.md) —
Exercise pipeline and teacher workflow.

---

## Phase 2: UserEntry — The Student's Work

**What:** The student's artifact. Two submission modes typed by `SubmissionModality`:
file upload (`FILE_UPLOAD` — audio, text, image processed into `processed_content`) or
structured form (`STRUCTURED_FORM` — inline form responses stored as JSON). The Exercise's
`expected_modality` field determines which path the UI presents. Post-ADR-054, `UserEntry`
is the unified user-authored content type, discriminated by its `pipeline` field for how the
content should be processed.

**EntityType:** `EntityType.USER_ENTRY`
**Loop role:** The *evidence* — the student's demonstration of engagement with PathStep content.
Without it, the Curriculum Track has no student voice.

**Derivation chain fields (set at creation, no graph query needed):**
- `parent_entity_uid` — the `fulfills_exercise_uid` passed at submission time (may be an Exercise or RevisedExercise UID). Set from `UserEntryCreateRequest.fulfills_exercise_uid` (via `create_entry`) / `submit_form()`. Useful as a Python-layer lookup; the graph edges are the authoritative source.
- `revision_number` — which attempt this is (1 = first; auto-computed by `process_exercise_submission()` as `prior_FULFILLS_EXERCISE_count + 1` counted against the **root Exercise** UID). Written to DB alongside the auto-generated canonical title.

Both fields make the Python model self-describing without a round-trip to the graph. Note: `FULFILLS_EXERCISE` always points to the root Exercise (see below); `parent_entity_uid` may point to a RevisedExercise UID for revision submissions.

**See:** [REPORT_ARCHITECTURE.md](/docs/architecture/REPORT_ARCHITECTURE.md) —
full pipeline from upload to sharing and teacher review queue.

### Phase 2.5: Interaction — The Situated Audit Record

Every UserEntry immediately spawns an **Interaction** node — a first-class
Neo4j entity capturing *where in the curriculum* the student was when they submitted.

**EntityType:** `EntityType.INTERACTION` (22nd entity type)
**UID prefix:** `ia_`
**Key fields:** `context_path_step_uid`, `context_learning_path_uid`, `target_uid` (exercise),
`source_entity_uid` (back-pointer to UserEntry), `result_status` (forward-only:
PENDING → SHARED_WITH_TEACHER → REPORT_GENERATED → COMPLETED, or FAILED pre-report —
transitions driven by the report pipeline via `interaction_result_handler`, ADR-051 Phase 2)

**Graph relationships:**
```cypher
(interaction)-[:RECORDS]->(submission)           // back-pointer to source artifact
(interaction)-[:INTERACTION_DURING]->(pathstep)  // curriculum position
(interaction)-[:INTERACTION_WITHIN]->(lp)        // path enrollment
```

**How context is captured deterministically:** Students navigate PathStep → Exercise → Submit
via the UI. The PathStep UID flows as `from_ps={ps_uid}` through the URL chain and is
embedded as a hidden form field. The upload handler passes it as `explicit_ps_uid` to
`_get_learning_context()`, which uses it directly rather than guessing from UserContext.
This means Interaction records have reliable, auditable situated context.

**Auto-created, best-effort:** Failure never blocks the submission. No UI affordance needed.

**Deferred work:** ZPD and Askesis will query
`(u:User)-[:OWNS]->(i:Interaction)-[:INTERACTION_DURING]->(ps:PathStep)` to reason
about *where in the curriculum* evidence was generated — not just what the student submitted.

**See:** `docs/decisions/ADR-051-user-interaction-contract.md`

---

## Phase 3: EntryReport — The Response

**What:** The evaluation. Two structurally distinct entities cover the two tracks.
Both say "here is what your work means."

### 3a. ENTRY_REPORT — Response to an Artifact

**What:** Evaluation of a specific `UserEntry`. One artifact in, one
`EntryReport` node out. Two sources: teacher writes (`HUMAN`) or AI evaluates
via the Exercise's `instructions` field (`LLM`). The LLM report is triggered
by the submission OWNER (self-serve — `POST /api/exercises/report`, per-user
ADR-043 FULL-tier gate) or by a teacher.

**EntityType:** `EntityType.ENTRY_REPORT`
**Self-describing outcome:** Each report records its `assessment_outcome` (`AssessmentOutcome` enum):
`APPROVED` (teacher approved, mastery 0.8), `NEEDS_REVISION` (teacher requests resubmission),
or `AI_EVALUATED` (LLM feedback, mastery 0.6, awaiting teacher review).

**Structural position:** Leaf domain. Reads flow through `EntryReportBackend`
(typed `get` + `list_for_submission` — `subject_uid` is projected from the
`REPORT_FOR` edge, not stored as a node property). Writes flow through
`UserEntryBackend.create_report_node`. Both are reached via `EntryReportService`,
the single service entry point (`EntryReportOperations` / `EntryReportBackendOperations`
protocols in `core/ports/report_protocols.py`).

### 3b. ACTIVITY_REPORT — Response to Activity Patterns

**What:** Response to a user's aggregate activity over a time window. Not tied to a
specific artifact — it responds to *patterns*. Three sources: scheduled system (`AUTOMATIC`),
on-demand AI (`LLM`), or admin-written (`HUMAN`).

**EntityType:** `EntityType.ACTIVITY_REPORT`
**Structural position:** Cross-domain aggregator — sits above the domain backends by design.
Reads across all 6 Activity Domains **and** the Curriculum track (KU mastery, LP progress,
PS progress) in a single MEGA_QUERY round-trip.

**See:** [REPORT_ARCHITECTURE.md](/docs/architecture/REPORT_ARCHITECTURE.md) —
canonical taxonomy, all services, API routes, ReportSource table, graph patterns.

---

## Phase 4: RevisedExercise — The Targeted Revision

**What:** A teacher-created revision of an Exercise that addresses specific gaps identified
in `EntryReport`. The teacher creates targeted, revised instructions for a specific
student. The student then submits against the RevisedExercise, receives new feedback, and the
cycle continues indefinitely. This forces a **reflection step** between feedback and
resubmission, making revision pedagogically explicit.

```
Exercise v1 → UserEntry v1 → EntryReport v1
                                   ↓
                             RevisedExercise v2 → UserEntry v2 → EntryReport v2
                                   ↓
                             RevisedExercise v3 → ...
```

**EntityType:** `EntityType.REVISED_EXERCISE`
**Model:** `core/models/exercises/revised_exercise.py` — `RevisedExercise(UserOwnedEntity)` frozen dataclass
**Loop role:** The *refinement* — bridges feedback back into a new exercise, closing the
revision cycle explicitly rather than implicitly.

**Key design:**
- Inherits `UserOwnedEntity` (NOT Curriculum) — needs `user_uid` but not 21 Curriculum fields
- `ContentOrigin.USER_CREATED` — teacher-authored content targeted at a specific student, not shared curriculum
- Teacher-owned, student-targeted (student visibility via `student_uid` field)
- `revision_number` auto-determined from existing chain length
- `feedback_points` carries typed `FeedbackPoint` objects (`FeedbackCategory` + free-text detail) — enables pattern tracking across submissions
- `expected_modality` and `submission_uid` auto-resolved by service on creation from the original Exercise and authority check
- `parent_entity_uid` set to `report_uid` at `create()` time — the EntryReport is the direct derivation parent. Mirror of the `RESPONDS_TO_REPORT` graph edge; makes the chain Python-model-readable without a graph query.

**Graph relationships:**
```cypher
(teacher:User)-[:OWNS]->(re:Entity:RevisedExercise {
    original_exercise_uid: '...',
    report_uid: '...',              // domain-specific field
    parent_entity_uid: '...',       // = report_uid — derivation chain mirror
    submission_uid: '...',
    student_uid: '...',
    revision_number: 2
})
(re)-[:RESPONDS_TO_REPORT]->(feedback:Entity:EntryReport)
(re)-[:REVISES_EXERCISE]->(exercise:Entity:Exercise)
(student:User)-[:SHARES_WITH {role: 'student'}]->(re)     // auto-created on creation
(submission:Entity:UserEntry)-[:FULFILLS_EXERCISE]->(exercise)    // root anchor — always
(submission:Entity:UserEntry)-[:FULFILLS_REVISED_EXERCISE]->(re)  // revision pointer
```

**Services:**
```python
services.revised_exercises              # RevisedExerciseService (standalone CRUD)
services.teacher_review                 # TeacherReviewService.request_revision_with_exercise()
# ^ Atomic path: creates EntryReport + RevisedExercise in one Neo4j transaction
#   via UserEntryBackend.create_report_and_revised_exercise()
```

**API routes (teacher, CRUDRouteFactory):** `POST /api/revised-exercises/create`,
`GET /api/revised-exercises/get?uid=`, `GET /api/revised-exercises/list`,
`POST /api/revised-exercises/update?uid=`, `POST /api/revised-exercises/delete?uid=`.
**API routes (teacher, domain-specific):** `GET /api/revised-exercises/for-student?student_uid=`,
`GET /api/revised-exercises/chain?exercise_uid=`.
**API routes (student):** `GET /api/revised-exercises/my-revisions` (list targeting current user),
`GET /api/revised-exercises/view?uid=` (view if student or owning teacher).
**Event:** `RevisedExerciseCreated` (`revised_exercise.created`) — published on creation.

**Access control:** `create()` (overrides `CrudOperationsMixin.create`) verifies the `student_uid`
owns the submission linked to the report (OWNS-based, per ADR-040). Teacher identity is
role-gated at the route level (`@require_role(UserRole.TEACHER)`).

**Student discovery:** On creation, a `SHARES_WITH {role: 'student'}` relationship is auto-created
from the student to the RevisedExercise (same pattern as ADR-040 assignment auto-sharing). This means:
- Revisions appear in the student's "Shared With Me" inbox
- MEGA-QUERY picks them up as `pending_revised_exercises` on UserContext
- `get_ready_to_work_on_today()` surfaces them at Priority 2.3
`/api/revised-exercises/for-student` scopes results to revisions owned by the requesting teacher.

---

## Naming

Every node in the chain `Exercise → UserEntry → EntryReport → RevisedExercise → UserEntry → ...` is a noun — object-language, not process-language. Variation *inside* each node lives on enum fields, never on parallel types:

- **`UserEntry`** carries `pipeline: Pipeline` (`NONE`, `TEACHER_REVIEW`, `TRANSCRIBE`, `LLM_SUMMARY`, `TRANSCRIBE_AND_STRUCTURE`, `EXTRACT_ACTIVITIES`, `JOURNAL`, `REFERENCE`) — ADR-054 collapsed `ExerciseSubmission` / `JeInput` / `JeOutput` into this one type.
- **`EntryReport`** carries `report_source: ReportSource` (`HUMAN`, `LLM`, `AUTOMATIC`) and `assessment_outcome: AssessmentOutcome` (`APPROVED`, `NEEDS_REVISION`, `AI_EVALUATED`) — a single report type covers both initial and revision cycles.
- **`RevisedExercise`** is a distinct EntityType because its hierarchy (`UserOwnedEntity` vs. `Curriculum`), ownership (teacher-owned vs. shared), `ContentOrigin` tier (`USER_CREATED` vs. `CURRICULUM`), and feedback typing (`FeedbackPoint[]` vs. plain `instructions`) all diverge from `Exercise`. "Revised" is a past-participle reading as "a kind of exercise" — not a verb phrase. The verb lives on the edge `(RevisedExercise)-[:REVISES_EXERCISE]->(Exercise)`.

**See:** [ENTITY_TYPE_ARCHITECTURE.md § Naming Convention](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md#naming-convention) for the rule, the two-part test, and additional worked examples.

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
                           │    context.active_path_steps_rich
                           │
              ProgressReportGenerator.generate()
                           │
                ActivityReport (LLM or AUTOMATIC)
```

**One Path Forward:** The loop's data layer is `UserContextBuilder.build_rich()`. There
is no separate activity query layer. Both `ProgressReportGenerator` and
`ActivityReportService` inject `context_builder: UserContextBuilder`.

---

## The ReportSource Discriminator

`ReportSource` distinguishes who produced a report entity — not a separate entity type.
New report sources add `ReportSource` values; they do not create new EntityTypes.

**See:** [REPORT_ARCHITECTURE.md](/docs/architecture/REPORT_ARCHITECTURE.md#reportsource-taxonomy) for the canonical ReportSource table.

**Import:** `from core.models.enums.pipeline import ReportSource`

---

## UI Surface — The PathStep as Learning Loop Anchor

The PathStep detail page (`/explore/ps/{uid}`) is the primary place where students
experience the full learning loop. For authenticated users, three HTMX fragment
endpoints lazy-load into the page:

| Section | Endpoint | What It Shows |
|---|---|---|
| **Exercises** | `GET /learning-loop/ps/{ps_uid}/exercises` | Exercises linked via `HAS_EXERCISE`, with status pills (Not Submitted / Submitted / Feedback Available / Revision Requested) and contextual action links |
| **My Submissions & Feedback** | `GET /learning-loop/ps/{ps_uid}/submissions-and-feedback` | User's submissions discovered via `Interaction -[:INTERACTION_DURING]-> PathStep`, with status badges, outcome badges (Approved / Revision Requested), and links to view submission or feedback |
| **Embedded Forms** | `GET /learning-loop/ps/{ps_uid}/forms` | FormTemplates embedded in this PathStep, with inline submit (`POST /learning-loop/ps/{ps_uid}/forms/{template_uid}/submit`) |

Routes wired in `adapters/inbound/learning_loop_routes.py` (`create_learning_loop_fragment_routes`). Fragment renderers in
`ui/learning_loop/` (shared with Library exercises tab). The `from_ps` parameter
threads through exercise links so the submit form knows which PathStep the student
navigated from, enabling deterministic Interaction context recording.

**Secondary indexes:** Library (`/library/exercises`) and GradeBook (`/gradebook`)
provide cross-PathStep views of the same data. They remain as supplementary access
points, not the primary learning loop surface.

Unauthenticated visitors see simple exercise links (title + time estimate) without
status pills or submission/feedback sections.

---

## Key Files Reference

| Purpose | File |
|---|---|
| Learning loop UI renderers | `ui/learning_loop/` (`exercise_status.py`, `submissions_section.py`, `feedback_section.py`) |
| PS learning loop fragment routes | `adapters/inbound/explore_ui.py` (`create_explore_ui_routes`) |
| UserEntry UI orchestration (GradeBook sub-factories) | `adapters/inbound/user_entry_routes.py` (`create_user_entry_routes`) |
| PathStep domain model | `core/models/pathways/path_step.py` |
| Mastery + intelligence models | `core/models/pathways/mastery.py` |
| Curriculum progress + journey models | `core/models/pathways/learning_progress.py` |
| SELCategory + LearningLevel enums | `core/models/enums/learning_enums.py` |
| Adaptive curriculum service | `core/services/ps/ps_adaptive_service.py` |
| PathStep mastery service (MASTERED transitions) | `core/services/ps/ps_mastery_service.py` |
| PathStep facade (wires sub-services) | `core/services/ps_service.py` |
| Learning experience UI components | `ui/patterns/curriculum_adaptive.py` |
| PathStep API routes | `adapters/inbound/path_steps_api.py` |
| Ingestion pipeline | `core/services/ingestion/` |
| Substance philosophy | `docs/architecture/knowledge_substance_philosophy.md` |
| Curriculum grouping patterns (KU / PS / LP) | `docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` |
| RevisedExercise domain model | `core/models/exercises/revised_exercise.py` |
| RevisedExercise service | `core/services/revised_exercises/revised_exercise_service.py` |
| RevisedExercise API routes | `adapters/inbound/revised_exercises_api.py` |

---

## The System Layers

The learning loop is Layer 1 of a 5-layer system. Each layer builds on the ones below:

| Layer | Purpose | Relationship to Loop |
|-------|---------|---------------------|
| 5. Semantics | Embeddings, vector search, meaning | Connects concepts by meaning |
| 4. Knowledge Graph | Neo4j relationships encode everything | The loop generates graph relationships |
| 3. Saved Interactions | Conversations, journals, annotations | Each loop iteration compounds signals |
| 2. ZPD + UserContext | "Where are you?" + "What's next?" | Intelligence makes the loop adaptive |
| **1. Learning Loop** | **Exercise → UserEntry → EntryReport → RevisedExercise** (PathStep anchors, outside the cycle) | **The base — everything serves this** |

See: `docs/user-guides/zpd.md`, `docs/user-guides/learning-loop.md`

---

## See Also

| Document | What It Covers |
|----------|---------------|
| [REPORT_ARCHITECTURE.md](/docs/architecture/REPORT_ARCHITECTURE.md) | Canonical report reference — all services, APIs, graph patterns, ReportSource taxonomy |
| [ENTITY_TYPE_ARCHITECTURE.md](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md) | How the loop fits the Entity Type Architecture |
| [ADR-038: Content Sharing](/docs/decisions/ADR-038-content-sharing-model.md) | Three-level visibility model for submissions |
| [ADR-040: Teacher Exercise Workflow](/docs/decisions/ADR-040-teacher-exercise-workflow.md) | ASSIGNED exercise, auto-sharing, teacher review queue |
| `.claude/skills/learning-loop/SKILL.md` | Developer guide — implementation details, service architecture, anti-patterns |
| `.claude/skills/zpd/SKILL.md` | ZPD intelligence layer — readiness scoring, compound evidence, recommended actions |
