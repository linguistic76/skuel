---
title: Five-Phased Learning Loop
updated: 2026-03-07
status: current
category: architecture
related:
- REPORT_ARCHITECTURE.md
- ENTITY_TYPE_ARCHITECTURE.md
---

# The Five-Phased Learning Loop

> "Knowledge is learned by doing, evaluated by responding, and refined by reflecting."

The Five-Phased Learning Loop is the **core purpose of SKUEL**. Every feature in the
codebase either feeds this loop, supports its infrastructure, or should be questioned.

Learning is not consuming content. Learning is what happens when knowledge changes how you
act, decide, and live. SKUEL models this through five phases: **what you can learn** (Article),
**how you practise it** (Exercise), **what you produce** (Submission), **what the
system says back** (Feedback), and **how the teacher guides revision** (RevisedExercise).
Every layer is a frozen Python dataclass. Every connection is a Neo4j graph relationship.
Every measurement flows from real user behaviour, not self-reported progress.

---

## The Loop

```
╔══════════════════════════════════════════════════════════════════════════╗
║                    FIVE-PHASED LEARNING LOOP                            ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  CURRICULUM TRACK (artifact-based)                                       ║
║  ────────────────────────────────────────────────────────────────────    ║
║  [Article] → [Exercise] → [Submission/Journal] → [Feedback]             ║
║   ↑             ↓              ↑↓                     ↓                  ║
║  admin       teacher        student               teacher/AI             ║
║  creates     assigns     uploads/revises          assesses               ║
║                                                      ↓                   ║
║                                              [RevisedExercise]           ║
║                                               teacher creates            ║
║                                              targeted revision           ║
║                                                      ↓                   ║
║                                              [Submission v2] → ...       ║
║                                                                          ║
║  ACTIVITY TRACK (aggregate-based)                                        ║
║  ────────────────────────────────────────────────────────────────────    ║
║  [Tasks + Goals + Habits + Events + Choices + Principles]                ║
║       + [KU mastery + LP progress + LS progress]                         ║
║                    ↓ (over time window)                                   ║
║             [Activity Report] ←── AI or Admin                            ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

## Two Tracks

**The loop has two entry points.** Both close the loop: work is done, the system responds.

| Track | Entry Point | Feedback Entity | Who Responds |
|-------|------------|-----------------|--------------|
| **Curriculum** | Student uploads a file against an Exercise | `SUBMISSION_REPORT` | Teacher or AI (via Exercise instructions) |
| **Activity** | User's lived practice over a time window | `ACTIVITY_REPORT` | AI (scheduled or on-demand) or Admin |

Activity Domains are **equal** entry points — not secondary. A user's Tasks, Goals, Habits,
Events, Choices, and Principles receive the same feedback infrastructure as curriculum work.
The mechanism differs, but the loop closes either way.

> **"Submission" — conceptual vs structural.** This document uses "Submission" in two
> senses that must not be conflated. The **conceptual submission** in the Activity Track is
> the user's lived practice across all six Activity Domains over a time window — it is
> implicit, never uploaded, and produces an `ACTIVITY_REPORT`. The **structural Submission**
> (`EntityType.SUBMISSION`) is a file a student explicitly uploads against an Exercise in the
> Curriculum Track and produces a `SUBMISSION_REPORT`. `ActivityReport` inherits
> `UserOwnedEntity` directly — it has no file fields. `Submission` inherits a file-aware
> base class. When reading code that touches both tracks, keep this distinction in mind:
> the loop closes differently in each track even though the pedagogical concept is the same.

---

## Phase 1: Article — The Teaching Composition

**What:** Essay-like curriculum content that composes atomic Kus into narrative. Admin-created
and shared across all users. Every Exercise is grounded in one or more Articles. Articles
compose atomic Kus via `(Article)-[:USES_KU]->(Ku)`.

**EntityType:** `EntityType.ARTICLE`
**Loop role:** The *why* — the knowledge the loop exists to transmit.
**See:** [ASKESIS_PEDAGOGICAL_ARCHITECTURE.md](/docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md) — Askesis scaffolds Phase 1 (Article discovery via ZPD-aware Socratic dialogue).

### Layer 1: What You Can Learn

**File:** `core/models/article/article.py`

An Article is a frozen dataclass — immutable once created, like a published textbook
page:

```
Article (frozen dataclass, inherits Curriculum → Entity)
├── Identity:    uid, title, content, domain
├── SEL Lens:    sel_category (SELCategory | None) — optional filter, not inherent
├── Difficulty:  learning_level, estimated_time_minutes, difficulty_rating (0.0-1.0)
├── Quality:     quality_score, complexity, semantic_links
└── Substance:   times_applied_in_tasks, times_practiced_in_events, ...
```

**Atomic Kus:** Articles compose atomic `Ku` entities (`EntityType.KU`, extends `Entity`
directly — lightweight ontology nodes in `core/models/ku/ku.py`). The substance and mastery
tracking described below applies to Articles; atomic Kus are reference nodes.

#### SEL Navigation Lens

An Article *may* carry an `sel_category` — a classification into the Social Emotional Learning
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
presentation logic: `get_icon()`, `get_color()`, `get_description()`. The `DOMAIN_SEL_MAPPING`
bridges activity domains into the SEL framework: principles map to self-awareness, habits to
self-management, choices to responsible decision-making.

The `ArticleAdaptiveService` uses `sel_category` as a filter — `find_by(sel_category=category.value)` —
to surface Articles grouped by SEL competency. Articles without a meaningful classification simply won't
appear in category-filtered views: not all knowledge fits neatly into an SEL lens.

#### How Articles Are Born: Markdown to Graph

Articles originate as Markdown files with YAML frontmatter in the Obsidian vault
(`/home/mike/0bsidian/skuel/docs/`). The ingestion pipeline (`core/services/ingestion/`)
parses the frontmatter, including the optional `sel_category` field.

Once in Neo4j, Articles connect through graph relationships:

```cypher
(a1:Article)-[:REQUIRES_KNOWLEDGE]->(a2:Article)       // Prerequisites
(a1:Article)-[:ENABLES_KNOWLEDGE]->(a2:Article)        // What mastering this unlocks
(moc:Article)-[:ORGANIZES]->(a:Article)                // MOC grouping (non-linear)
(a:Article)-[:USES_KU]->(ku:Ku)                        // Composes atomic Kus
(ls:LearningStep)-[:TRAINS_KU]->(ku:Ku)                // LS trains atomic Kus
```

### Layer 2: How You're Learning It — Mastery Tracking

**File:** `core/models/pathways/mastery.py`

When a user interacts with an Article, a `MASTERED` relationship is created between `:User` and
`:Article`. The `Mastery` dataclass models what that relationship means:

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

The `ArticleMasteryService` (`core/services/article/article_mastery_service.py`) manages
pedagogical progression: `VIEWED` → `IN_PROGRESS` → `MASTERED`. Each transition is a graph
relationship event.

`LearningVelocity` tracks how fast a user learns in different domains — not as a judgment
but as data for personalisation. A user who learns yoga slowly but Python quickly gets
different time estimates for each.

`LearningPreference` captures what works for a specific person: preferred content types,
session duration, whether they learn better with examples, top-down vs bottom-up approach.
This profile evolves from actual learning patterns, not questionnaires.

### Layer 3: Whether It's Changing Your Life — Substance Scoring

**File:** `core/models/article/article.py`

The `substance_score()` method on the `Article` dataclass measures how knowledge is **lived**,
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

The substance fields on the `Article` model (`times_applied_in_tasks`, `times_practiced_in_events`,
etc.) are updated via the event-driven architecture. When a user completes a task that
references an Article, the `ArticleService` handles the `knowledge.applied_in_task` event and atomically
increments the counter in Neo4j.

### The Adaptive Service: Connecting the Layers

**File:** `core/services/article/article_adaptive_service.py`

`ArticleAdaptiveService` answers the question: **"What should this person learn next?"**

**Personalised curriculum delivery** (`get_personalized_curriculum`):

```
1. Load user's learning intelligence (masteries, paths, velocity)
2. Query all Articles in the requested SEL category
3. Filter by readiness:
   - Not already mastered
   - Prerequisites met (via REQUIRES_KNOWLEDGE graph traversal)
   - Appropriate for user's current level
4. Rank by learning value:
   - Enables many future Articles (×10) — high leverage
   - Matches preferred difficulty (×20) — flow state
   - Fits available time (×15) — practical
   - Foundational / no prerequisites (×5) — unblocked
   - Quick win (×10) — momentum
5. Return top N recommendations
```

**`CurriculumProgress`** (`core/models/pathways/learning_progress.py`) — a frozen snapshot of
a user's progress through one SEL category:

```
KuCategoryProgress
├── user_uid, sel_category
├── articles_mastered, articles_in_progress, articles_available, total_articles
├── completion_percentage (0-100), current_level (LearningLevel)
└── started_at, last_activity, estimated_completion_date
```

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

**File:** `ui/patterns/curriculum_adaptive.py`

| Component | What It Shows |
|---|---|
| `SELCategoryCard(category, progress)` | One category's progress bar, count badges, "Continue Learning" link to `/articles?sel={category}` |
| `AdaptiveArticleCard(article, prerequisites_met)` | One recommended Article — time, difficulty, level badge, prerequisite status, link to `/articles/{uid}` |
| `SELJourneyOverview(journey)` | Master view — overall %, recommended focus alert, grid of five `SELCategoryCard` components |

**API routes** (`adapters/inbound/article_api.py`):

| Route | Purpose |
|---|---|
| `GET /api/articles/journey` | `LearningJourney` (JSON) |
| `GET /api/articles/curriculum/{category}` | `list[Article]` (JSON) |
| `GET /api/articles/journey-html` | `SELJourneyOverview` (HTMX fragment) |
| `GET /api/articles/curriculum-html/{category}` | Grid of `AdaptiveArticleCard` (HTMX fragment) |

The HTML routes enable HTMX partial updates — the journey overview loads once, and clicking
a category fetches that category's personalised curriculum as an HTML fragment.

---

## Phase 2: Exercise — The Assignment

**What:** The teacher's directive. Instructions for what students should produce, with an
LLM prompt embedded for AI-assisted feedback. Two scopes: `PERSONAL` (self-directed) and
`ASSIGNED` (classroom with a Group target and due date).

**EntityType:** `EntityType.EXERCISE`
**Loop role:** The *how* — operationalises Article content into a concrete task. The `instructions`
field serves double duty: directive for the student AND prompt for the AI when generating
`SUBMISSION_REPORT`.

**See:** [REPORT_ARCHITECTURE.md](/docs/architecture/REPORT_ARCHITECTURE.md) —
Exercise pipeline and teacher workflow.

---

## Phase 3: Submission — The Student's Work

**What:** The student's artifact. An uploaded file (audio, text, image) that is processed
into `processed_content` — the evaluable form. Two leaf types: `SUBMISSION` (student
uploads) and `JOURNAL` (admin uploads for AI-only processing).

**EntityType:** `EntityType.SUBMISSION` or `EntityType.JOURNAL`
**Loop role:** The *evidence* — the student's demonstration of engagement with Article content.
Without it, the Curriculum Track has no student voice.

**See:** [REPORT_ARCHITECTURE.md](/docs/architecture/REPORT_ARCHITECTURE.md) —
full pipeline from upload to sharing and teacher review queue.

---

## Phase 4: Feedback — The Response

**What:** The evaluation. Two structurally distinct entities cover the two tracks.
Both say "here is what your work means."

### 4a. SUBMISSION_REPORT — Response to an Artifact

**What:** Evaluation of a specific `SUBMISSION` or `JOURNAL`. One artifact in, one
`SubmissionReport` node out. Two sources: teacher writes (`HUMAN`) or AI evaluates
via the Exercise's `instructions` field (`LLM`).

**EntityType:** `EntityType.SUBMISSION_REPORT`
**Structural position:** Leaf domain — fits the standard 4-layer architecture cleanly
(`SubmissionReportOperations` protocol → `SubmissionsBackend` → `SubmissionReportService` / `SubmissionsCoreService`).

### 4b. ACTIVITY_REPORT — Response to Activity Patterns

**What:** Response to a user's aggregate activity over a time window. Not tied to a
specific artifact — it responds to *patterns*. Three sources: scheduled system (`AUTOMATIC`),
on-demand AI (`LLM`), or admin-written (`HUMAN`).

**EntityType:** `EntityType.ACTIVITY_REPORT`
**Structural position:** Cross-domain aggregator — sits above the domain backends by design.
Reads across all 6 Activity Domains **and** the Curriculum track (KU mastery, LP progress,
LS progress) in a single MEGA_QUERY round-trip.

**See:** [REPORT_ARCHITECTURE.md](/docs/architecture/REPORT_ARCHITECTURE.md) —
canonical taxonomy, all services, API routes, ProcessorType table, graph patterns.

---

## Phase 5: RevisedExercise — The Targeted Revision

**What:** A teacher-created revision of an Exercise that addresses specific gaps identified
in `SubmissionReport`. The teacher creates targeted, revised instructions for a specific
student. The student then submits against the RevisedExercise, receives new feedback, and the
cycle continues indefinitely. This forces a **reflection step** between feedback and
resubmission, making revision pedagogically explicit.

```
Article → Exercise v1 → Submission v1 → SubmissionReport v1
                                              ↓
                                        RevisedExercise v2 → Submission v2 → SubmissionReport v2
                                              ↓
                                        RevisedExercise v3 → ...
```

**EntityType:** `EntityType.REVISED_EXERCISE`
**Model:** `core/models/exercises/revised_exercise.py` — `RevisedExercise(UserOwnedEntity)` frozen dataclass
**Loop role:** The *refinement* — bridges feedback back into a new exercise, closing the
revision cycle explicitly rather than implicitly.

**Key design:**
- Inherits `UserOwnedEntity` (NOT Curriculum) — needs `user_uid` but not 21 Curriculum fields
- First entity type combining `ContentOrigin.CURRICULUM` with `requires_user_uid()=True`
- Teacher-owned, student-targeted (student visibility via `student_uid` field)
- `revision_number` auto-determined from existing chain length

**Graph relationships:**
```cypher
(teacher:User)-[:OWNS]->(re:Entity:RevisedExercise {
    original_exercise_uid: '...',
    feedback_uid: '...',
    student_uid: '...',
    revision_number: 2
})
(re)-[:RESPONDS_TO_REPORT]->(feedback:Entity:SubmissionReport)
(re)-[:REVISES_EXERCISE]->(exercise:Entity:Exercise)
(student:User)-[:SHARES_WITH {role: 'student'}]->(re)     // auto-created on creation
(submission:Entity:Submission)-[:FULFILLS_EXERCISE]->(re)  // reuses existing rel type
```

**Services:**
```python
services.revised_exercises              # RevisedExerciseService
```

**API routes (teacher):** `POST /api/revised-exercises/create`, `GET /api/revised-exercises/get`,
`GET /api/revised-exercises/list`, `GET /api/revised-exercises/for-student`,
`GET /api/revised-exercises/chain`, `POST /api/revised-exercises/update`,
`POST /api/revised-exercises/delete`.
**API routes (student):** `GET /api/revised-exercises/my-revisions` (list targeting current user),
`GET /api/revised-exercises/view?uid=` (view if student or owning teacher).
**Event:** `RevisedExerciseCreated` (`revised_exercise.created`) — published on creation.

**Access control:** `create_revised_exercise` verifies the teacher has `SHARES_WITH {role:'teacher'}`
on the submission linked to the feedback, and the `student_uid` owns that submission.

**Student discovery:** On creation, a `SHARES_WITH {role: 'student'}` relationship is auto-created
from the student to the RevisedExercise (same pattern as ADR-040 assignment auto-sharing). This means:
- Revisions appear in the student's "Shared With Me" inbox
- MEGA-QUERY picks them up as `pending_revised_exercises` on UserContext
- `get_ready_to_work_on_today()` surfaces them at Priority 2.3
`/api/revised-exercises/for-student` scopes results to revisions owned by the requesting teacher.

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
              ProgressReportGenerator.generate()
                           │
                ActivityReport (LLM or AUTOMATIC)
```

**One Path Forward:** The loop's data layer is `UserContextBuilder.build_rich()`. There
is no separate activity query layer. Both `ProgressReportGenerator` and
`ActivityReportService` inject `context_builder: UserContextBuilder`.

---

## The ProcessorType Discriminator

`ProcessorType` distinguishes who produced a feedback entity — not a separate entity type.
New feedback sources add `ProcessorType` values; they do not create new EntityTypes.

**See:** [REPORT_ARCHITECTURE.md](/docs/architecture/REPORT_ARCHITECTURE.md#processortype-taxonomy) for the canonical ProcessorType table.

**Import:** `from core.models.enums.entity_enums import ProcessorType`

---

## Key Files Reference

| Purpose | File |
|---|---|
| Article domain model | `core/models/article/article.py` |
| Mastery + intelligence models | `core/models/pathways/mastery.py` |
| Curriculum progress + journey models | `core/models/pathways/learning_progress.py` |
| SELCategory + LearningLevel enums | `core/models/enums/learning_enums.py` |
| Adaptive curriculum service | `core/services/article/article_adaptive_service.py` |
| Article mastery service (MASTERED transitions) | `core/services/article/article_mastery_service.py` |
| Article facade (wires sub-services) | `core/services/article_service.py` |
| Learning experience UI components | `ui/patterns/curriculum_adaptive.py` |
| Article API routes | `adapters/inbound/article_api.py` |
| Ingestion pipeline | `core/services/ingestion/` |
| Substance philosophy | `docs/architecture/knowledge_substance_philosophy.md` |
| Curriculum grouping patterns (KU / LS / LP) | `docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` |
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
| **1. Learning Loop** | **Article → Exercise → Submission → Report → RevisedExercise** | **The base — everything serves this** |

See: `docs/user-guides/zpd.md`, `docs/user-guides/learning-loop.md`

---

## See Also

| Document | What It Covers |
|----------|---------------|
| [REPORT_ARCHITECTURE.md](/docs/architecture/REPORT_ARCHITECTURE.md) | Canonical report reference — all services, APIs, graph patterns, ProcessorType taxonomy |
| [ENTITY_TYPE_ARCHITECTURE.md](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md) | How the loop fits the Entity Type Architecture |
| [ADR-038: Content Sharing](/docs/decisions/ADR-038-content-sharing-model.md) | Three-level visibility model for submissions |
| [ADR-040: Teacher Assignment Workflow](/docs/decisions/ADR-040-teacher-assignment-workflow.md) | ASSIGNED exercise, auto-sharing, teacher review queue |
| `.claude/skills/learning-loop/SKILL.md` | Developer guide — implementation details, service architecture, anti-patterns |
| `.claude/skills/zpd/SKILL.md` | ZPD intelligence layer — readiness scoring, compound evidence, recommended actions |
