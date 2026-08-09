---
name: learning-loop
description: >
  Expert guide for SKUEL's Learning Loop — the core purpose of the app.
  Use when building or reviewing any feature involving PathStep, Exercise, Submission, Report,
  RevisedExercise, or Interaction. TRIGGER when: working on submissions, exercises, report generation,
  activity reports, revised exercises, teacher review, AI assessment, Interaction records, or when designing a new
  feature and asking "where does this fit?". This skill provides the development lens: every
  new feature must either strengthen a loop phase or improve the transition between phases.
  Features that serve no loop purpose are candidates for deletion per SKUEL's One Path Forward
  philosophy.
allowed-tools: Read, Grep, Glob
---

# The Learning Loop

> "Knowledge is learned by doing, evaluated by responding, and refined by reflecting."

> **Core axiom: PathStep is knowledge. Exercise is applied knowledge.**
> PathStep and Exercise are NOT peers in the curriculum hierarchy. Exercise is subordinate
> to PathStep — the instruction template that operationalises PathStep content into concrete
> practice. `(PathStep)-[:HAS_EXERCISE]->(Exercise)`. Exercise.path_step_uid is a
> hierarchy-membership property (same pattern as Goal.fulfills_goal_uid), not a scoring
> field. `EntityType.EXERCISE.is_applied_knowledge()` is `True`.

> **ADR-054 update (2026-04-17).** `ExerciseSubmission`, `JeInput`, and `JeOutput` were
> collapsed into a single `UserEntry(UserOwnedEntity)` entity type discriminated by the
> `Pipeline` enum (`NONE`, `TEACHER_REVIEW`, `TRANSCRIBE`, `LLM_SUMMARY`,
> `TRANSCRIBE_AND_STRUCTURE`, and since ADR-069 `EXTRACT_ACTIVITIES`).
> Revision count moved onto the edge:
> `(UserEntry)-[:FULFILLS_EXERCISE {revision}]->(Exercise)`. Reports use a new
> `ReportSource` enum (`HUMAN`, `LLM`, `HYBRID`, `AUTOMATIC`) in place of `ProcessorType`. The
> journal track is now a *pipeline*, not a domain: audio uploads create a source
> `UserEntry` with `pipeline=TRANSCRIBE_AND_STRUCTURE`, which is then transformed into a
> structured second `UserEntry` via `(structured)-[:TRANSFORMS]->(source)`. Activity
> extraction from journals (DSL auto-creating Tasks/Goals) was **dropped** —
> and later returned on one path forward as `Pipeline.EXTRACT_ACTIVITIES`
> (ADR-069, 2026-06): an explicit processing branch over UserEntry content
> with `EXTRACTED_FROM` provenance, NOT a resurrection of the retired
> submission-metadata flow.
> Services live in `core/services/user_entry/`; the legacy `core/services/submissions/`
> and `core/services/journal/` packages were deleted (SKUEL deletes, it does not
> shelve). Historical references to
> `ExerciseSubmission`, `JeInput`, `JeOutput`, `ProcessorType`,
> `SubmissionsBackend`, `submission_protocols.py`, and `process_exercise_submission()`
> in this file now point to their `UserEntry` / `UserEntryBackend` /
> `user_entry_protocols.py` / `UserEntryProcessingService` counterparts.

The Learning Loop is the **gravitational center of SKUEL**. Every feature either feeds
this loop, supports its infrastructure, or should be questioned. Understanding the loop
is the prerequisite for all architectural decisions.

**The loop, in its narrowest form:**

```
Exercise → UserEntry → EntryReport → RevisedExercise → repeat
```

These four entity types ARE the learning loop. Everything else is substrate (Ku, PathStep),
infrastructure (Interaction, sharing, groups), or parallel reporting (ActivityReport).
The cycle repeats until the teacher approves or the student reaches mastery.

---

## The Loop at a Glance

```
╔══════════════════════════════════════════════════════════════════════════╗
║                         THE LEARNING LOOP                               ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  SUBSTRATE                                                               ║
║  ────────────────────────────────────────────────────────────────────    ║
║  [Ku] — the knowledge to be transmitted                                  ║
║  [PathStep] — the loop anchor (PERSONAL exercises live here)             ║
║                                                                          ║
║  THE LOOP (iterates until mastered)                                      ║
║  ────────────────────────────────────────────────────────────────────    ║
║  [Exercise] → [UserEntry] → [EntryReport]                             ║
║   Phase 1      Phase 2        Phase 3                                    ║
║   directive    student's work teacher/AI response                        ║
║                                    ↓                                     ║
║                             [RevisedExercise]  (optional)                ║
║                              Phase 4                                     ║
║                              targeted revision                           ║
║                                    ↓                                     ║
║                             [UserEntry v2, revision=2] → ...             ║
║                  ↑__________________________________________↓            ║
║                                                                          ║
║  PARALLEL REPORTING (sibling system — same feedback philosophy,          ║
║  structurally separate)                                                  ║
║  ────────────────────────────────────────────────────────────────────    ║
║  [Tasks + Goals + Habits + Events + Choices + Principles]                ║
║                    ↓ (over time window)                                   ║
║             [ActivityReport] ←── AI or Admin                            ║
║                                                                          ║
║  JOURNAL TRACK (self-directed pipeline on UserEntry)                     ║
║  ────────────────────────────────────────────────────────────────────    ║
║  [UserEntry(source, pipeline=TRANSCRIBE_AND_STRUCTURE)] → Deepgram       ║
║    → LLM → [UserEntry(structured)] -[:TRANSFORMS]-> source               ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

**The loop and its parallel.** ActivityReport closes a feedback loop over *lived activity*
(Tasks, Goals, Habits across a time window). It shares the same pedagogical purpose —
student does work, system responds — but it is **structurally separate**: different
services (`ProgressReportGenerator`, `ActivityReportService`), different routes, and
explicitly excluded from `LearningLoopEventHandlerService` and `LearningLoopQueryService`.

**Mastery impact scoring:** Each Exercise declares a `mastery_impact: MasteryImpact`
field (MINOR, MODERATE, MAJOR, CERTIFICATION) that controls how aggressively
completing it advances the student's mastery. Two score methods:
`get_ai_score()` (0.4–0.8) for AI-evaluated submissions, `get_teacher_score()`
(0.6–0.95) for teacher-approved submissions. Default is MODERATE (AI=0.6,
Teacher=0.8). See: `core/models/enums/learning_enums.py`.

**Learning progress event chain:** When `mark_mastered()` is called on a KU, the
system automatically propagates progress upward: KU mastery → PathStep progress →
LearningPath progress. See
[LEARNING_PROGRESS_EVENT_CHAIN.md](/docs/architecture/LEARNING_PROGRESS_EVENT_CHAIN.md).

**Learning loop intelligence:** The learning loop has two sibling services in
`core/services/user_entry/`:

- **Write side** — `LearningLoopEventHandlerService` (event-driven, fire-and-forget).
- **Read side** — `LearningLoopQueryService` (Cypher queries that traverse
  `Interaction`/`Exercise`/`Report` edges). New learning-loop reads land here,
  not on the generic `BaseService` search path that `UserEntryService` inherits
  (`:UserEntry`-label-scoped text/date/category search — recency, CONTAINS,
  stats). The graph-shaped loop reads belong in `LearningLoopQueryService`; the
  inherited path is already domain-scoped by the `:UserEntry` label.

`LearningLoopEventHandlerService` listens to
`UserEntryCreated`, `ReportSubmitted`, and `UserEntryApproved` to track submission
iterations (how many attempts per exercise), teacher feedback turnaround (EMA on
User node), and mastery velocity (quick vs persistent learner). Persists insights
to `InsightStore`. File: `core/services/user_entry/learning_loop_handler.py`.

---

## Field Naming Convention: `entity_type` vs `EntityType`

The Python enum is named `EntityType`. The Python model field and Neo4j node
property are both named **`entity_type`** (renamed from `ku_type` in March 2026).

```python
# Python model field:
ku = Ku(entity_type=EntityType.KU, ...)
report = EntryReport(entity_type=EntityType.ENTRY_REPORT, ...)
activity_report = ActivityReport(entity_type=EntityType.ACTIVITY_REPORT, ...)

# Neo4j property:
MATCH (n:Entity {entity_type: 'entry_report'})
MATCH (n:Entity {entity_type: 'ku'})
```

---

## Loop Substrate: Ku — The Knowledge Transmitted

**What it is:** Atomic curriculum content. A single "brick" of knowledge, admin-created
and shared across all users. Ku is the *why* — the knowledge the loop exists to
transmit. It is not a phase of the iterative cycle; it is the substance the cycle
is built around.

**EntityType:** `EntityType.KU`
**Model:** `core/models/ku/ku.py` — `Ku(Curriculum)` frozen dataclass
**DTO:** `core/models/ku/ku_dto.py`
**UID format:** `ku_{slug}_{random}`
**Neo4j label:** `:Entity:Ku`

**Key fields:**
```python
title: str                        # The knowledge unit's name
content: str                      # Substance — what to learn
domain: str                       # Which knowledge domain
complexity: KuComplexity          # BASIC / INTERMEDIATE / ADVANCED / EXPERT
learning_level: LearningLevel     # K-12 / UNDERGRAD / GRAD / PROFESSIONAL
status: EntityStatus              # DRAFT → ACTIVE → ARCHIVED
```

**Access:** `ContentScope.SHARED` — admins create, all users read. No ownership check.

**Services:**
```python
services.ku                       # KuService facade (8 sub-services)
services.ku.core                  # CRUD — create, update, delete
services.ku.search                # search(), get_by_status(), get_by_category()
services.ku.organization          # ORGANIZES relationships (MOC pattern)
services.ku.intelligence          # get_ku_with_context(), readiness scoring
```

**Graph pattern:**
```cypher
(admin:User)-[:OWNS]->(ku:Entity:Ku {uid, title, content, complexity})
(ku)-[:ORGANIZES {order: 1}]->(child_ku:Entity:Ku)  // MOC: any Ku can organize others
(exercise)-[:REQUIRES_KNOWLEDGE]->(ku)               // Exercise links to required Ku
```

**Substrate role:** Ku is the *why* — the knowledge the loop exists to transmit. Every
Exercise is grounded in one or more Ku nodes. When a student completes an Exercise,
they are demonstrating engagement with specific Ku content.

---

## Phase-by-Phase Reference

The full mechanics of each loop phase live in **[reference.md](reference.md)**:

- **Phase 1 — Exercise** (the directive): fields, scopes, submission modes, PathStep anchor, worksheet download, graph patterns.
- **Phase 2 — UserEntry** (the student's work): processing pipeline, status transitions, modality vs pipeline, backend Cypher.
- **The Interaction Contract** — curriculum context captured at submission time (ADR-051).
- **Phase 3 — EntryReport** (the response): teacher vs AI sources, revision cycle, status guards.
- **Parallel Reporting — ActivityReport** (structurally separate sibling system).
- **Phase 4 — RevisedExercise** (the targeted revision) + why it is object-language (naming rationale).
- **The Binding Graph Relationships**, **Service Architecture Summary**, and **API Routes Per Phase**.

**Who triggers Phase 3:** a teacher (review queue), or the submission OWNER
self-serving an AI review — `POST /api/exercises/report` (owner-or-teacher
guard + per-user ADR-043 FULL-tier gate; surfaced as the "Request AI feedback"
button on `/gradebook/{uid}`). Ruled 2026-07-03 (systems review R1); shipped
PR #497 + care arc.

**Teacher transition:** students auto-join the default teacher group
(`group_default_{admin_uid}`, oldest HUMAN admin — `@skuel.local` service
accounts excluded) on PathStep enrollment, and `teacher_review` submissions
against CURRICULUM-scope exercises auto-share to the submitter's default group
(fallback in `core/services/user_entry/audience_resolver.py`), landing in
`/teaching/queue`.

---

## The Development Lens

**Every feature decision should pass through this filter:**

### Questions to ask before building or extending

1. **Which phase does this touch?**
   - Ku/PathStep (knowledge substrate / loop anchor) → pre-loop substrate
   - Exercise (directive/template) → Phase 1
   - Submission processing → Phase 2
   - Feedback generation or display → Phase 3
   - RevisedExercise (targeted revision) → Phase 4
   - ActivityReport (aggregate feedback) → parallel reporting infrastructure
   - Supporting infrastructure (sharing, groups, scheduling) → loop support

2. **Does it strengthen a phase or improve a transition?**
   - Strengthens a phase: Better AI feedback, richer Ku content, cleaner submission UI
   - Improves a transition: Faster Ku→Exercise linking, auto-share on submission, annotation tools

3. **If it touches none of the four phases, why does it exist?**
   - Is it genuinely cross-cutting infrastructure (auth, search, calendar)?
   - Or is it isolated logic that accumulated without serving the loop?
   - Per One Path Forward: isolated logic with no loop connection is a deletion candidate.

### Green flags — features that feed the loop

- Adds a new pathway for feedback to reach the student (Phase 3)
- Improves the quality or speed of submission processing (Phase 2)
- Enriches Ku content with semantic relationships (substrate)
- Makes Exercise creation easier for teachers (Phase 1)
- Strengthens the Activity Track (better `ActivityReport` insights)

### Red flags — features to question

- New data model with no `FULFILLS_EXERCISE`, `REPORT_FOR`, or equivalent loop relationship
- A service that reads from multiple domains but writes to none of them (pure read aggregation)
- A UI route that displays data from the loop but adds no new interaction or progression
- Standalone admin tooling with no student-facing outcome

### The Activity Track test

The Activity Track (Tasks/Goals/Habits/Events/Choices/Principles + KU mastery/LP
progress/PS progress → ActivityReport) is as central as the Curriculum Track.
When building Activity Domain or Curriculum features, ask:

- Does this completion data flow into `ProgressReportGenerator`?
- Does this activity pattern become visible in `ActivityReport`?
- Can an admin see this behavior in the activity review snapshot?
- Can the user annotate or reflect on the AI's synthesis of this data?

If the answer to all four is "no", the feature may be accumulating activity data
that never closes the loop.

---

## ReportSource Taxonomy

`ReportSource` discriminates who produced a report entity.

**See:** [REPORT_ARCHITECTURE.md](/docs/architecture/REPORT_ARCHITECTURE.md#reportsource-taxonomy) for the canonical table.

**Import:** `from core.models.enums.pipeline import ReportSource`

---

## Test Coverage

| Service | Test File | Tests | Coverage |
|---------|-----------|-------|----------|
| `TeacherReviewService` | `tests/unit/services/test_teacher_review_service.py` | 60 | 76% (157/207 lines) |
| `UserEntryService` | `tests/unit/services/test_user_entry_service.py` | 41 | 69% (146/211 lines) |
| `AssessmentService` | `tests/unit/test_assessment_service.py` | 2 | 100% (23/23 lines) |

**TeacherReviewService tests cover:** access control (`_verify_teacher_has_group_access` — requires teacher and student share an active group), review queue filtering, report submission + event publishing, revision requests, approval with mastery updates, dashboard stats, group management, exercise/student views.

**UserEntryService tests cover:** the consolidated `UserEntry` write path (ADR-054) — `create_entry`, exercise linking, pipeline dispatch, and ownership/access checks across the file-upload and structured-form entry modes.

---

## Key Source Files

| File | Phase | Purpose |
|------|-------|---------|
| `core/models/ku/ku.py` | 1 | Ku frozen dataclass |
| `core/models/exercises/exercise.py` | 2 | Exercise frozen dataclass |
| `core/models/exercises/revised_exercise.py` | 5 | RevisedExercise frozen dataclass |
| `core/services/revised_exercises/revised_exercise_service.py` | 5 | RevisedExercise CRUD + chain queries |
| `adapters/inbound/revised_exercises_api.py` | 5 | RevisedExercise API routes (teacher + student-facing) |
| `adapters/inbound/revised_exercises_ui.py` | 5 | RevisedExercise detail + hub preview (GradeBook shell) |
| `adapters/inbound/entry_reports_ui.py` | 4 | EntryReport UI routes (list + detail page) |
| `ui/learning_loop/revised_exercise.py` | 5 | RevisedExercise renderers (detail, card, list views) |
| `ui/learning_loop/report.py` | 4 | EntryReport renderers (detail page with outcome/processor badges) |
| `ui/patterns/modal.py` | support | AlpineModal — standardized Alpine.js modal wrapper |
| `core/ports/curriculum_protocols.py` | 5 | `RevisedExerciseOperations` protocol |
| `core/models/user_entry/user_entry.py` | 3 | UserEntry frozen dataclass (`UserOwnedEntity`) |
| `core/models/report/entry_report.py` | 4 | EntryReport model |
| `core/models/report/activity_report.py` | 4 | ActivityReport model |
| `core/services/user_entry/user_entry_service.py` | 3+4 | UserEntry facade (BaseService) — shared `create_entry` write path, exercise linking |
| `core/services/user_entry/user_entry_processing_service.py` | 3 | Pipeline processing — transcription, LLM summary/structure (the former journal track, now a `Pipeline`) |
| `core/services/user_entry/assessment_service.py` | 4 | Teacher assessment CRUD, authority verification |
| `core/services/report/entry_report_service.py` | 4 | AI report generation (via UnifiedLLMCaller) |
| `core/services/llm_caller.py` | 3+4 | Unified LLM routing (OpenAI/Anthropic by model prefix) |
| `core/services/output/instruction_resolver.py` | 3 | Instruction resolution (custom > exercise > mode > default) |
| `core/services/transcription/batch_transcription_service.py` | 3 | Batch audio → txt (Tier 1, config via `config/deepgram.toml`) |
| `core/services/transcription/batch_processing_service.py` | 3 | Batch txt → md (Tier 2) |
| `config/deepgram.toml` | 3 | Deepgram options — model, utterances, intelligence, vocabulary |
| `core/config/deepgram_config.py` | 3 | Config loader for `config/deepgram.toml` |
| `core/services/report/progress_report_generator.py` | 4 | ActivityReport generation |
| `core/services/report/activity_report_service.py` | 4 | Admin human report; all write paths converge here |
| `core/services/report/teacher_review_service.py` | 4 | Teacher review workflow (review queue, revision, approval) |
| `core/services/background/progress_report_worker.py` | 4 | Scheduled activity report background worker |
| `core/ports/user_entry_protocols.py` | 3 | UserEntry protocols — backend port (`UserEntryOperations`) + CRUD/lifecycle/assessment/report-query/content sub-protocols |
| `core/ports/report_protocols.py` | 7 | All report protocols incl. `TeacherReviewOperations`, `ReviewQueueOperations`, `ReportRelationshipOperations` — typed returns (`ReviewRequestResult`, `PendingReviewItem`, `GroupMemberProgress`) |
| `core/ports/group_protocols.py` | support | `GroupOperations` only (group CRUD + membership) |
| `core/services/sharing/unified_sharing_service.py` | 3 | Entity-agnostic sharing |
| `adapters/persistence/neo4j/backends/` | all | Domain-specific Cypher (9 cluster files) |
| `adapters/inbound/user_entry_ui.py` | 2+3+4 | Student submit form (`/submissions/exercise`), gradebook detail (`/gradebook/{uid}`), feedback display |
| `adapters/inbound/user_entry_api.py` | 2+3 | UserEntry API (`POST /api/user-entries/upload` file-upload door) |
| `adapters/inbound/teaching_ui.py` | 4 | Students (default page), review queue (`/teaching/queue`), student detail with KU tab, groups |
| `adapters/inbound/teaching_forms_ui.py` | — | Forms visibility: template list, per-template submissions, submission detail (teacher role) |
| `adapters/inbound/teaching_api.py` | 4 | Teacher API (review queue, revision, approve, students, groups) |
| `adapters/inbound/exchange_ui.py` | 2+4 | `/exchange` thread view — one (student, exercise) exchange chronologically (renderer: `ui/learning_loop/exchange_thread.py`) |
| `ui/patterns/feedback_item.py` | 4 | Shared feedback rendering (used by teaching + submissions UI) |
| `core/prompts/templates/activity_feedback.md` | 4 | LLM prompt template (via PROMPT_REGISTRY) |

---

## Code Walkthrough

The end-to-end sequential walkthroughs — the Curriculum Track (artifact-based) and the Activity Track (aggregate-based) — live in **[reference.md](reference.md#code-walkthrough)**.

---

## Anti-Patterns

### Don't create a feedback model that inherits Submission when it has no file fields

```python
# WRONG — ActivityReport does not have file uploads
class ActivityReport(Submission):  # No! Submission has file_path, file_size, etc.

# CORRECT — ActivityReport inherits UserOwnedEntity directly
class ActivityReport(UserOwnedEntity):  # No file fields — it's about patterns, not artifacts
```

### Don't put cross-domain Cypher on a single domain backend

```python
# WRONG — ProgressReportGenerator needs Tasks + Goals + Habits + ...
class ReportBackend(UniversalNeo4jBackend):
    async def get_all_activity_completions(self):
        # Can't do this from one domain backend

# CORRECT — cross-domain aggregation uses UserContext.build_rich() (MEGA_QUERY)
class ProgressReportGenerator:
    def __init__(self, context_builder: UserContextBuilder, executor: QueryExecutor, ...):
        # context_builder.build_rich(user_uid, window=...) — MEGA_QUERY with 6-domain
        # activity window CALL{} blocks; entities_rich covers all Activity Domains
        # executor — raw Cypher for annotation lookup only
```

### Don't confuse Exercise scope

```python
# WRONG — PERSONAL exercises don't target groups
exercise = Exercise(scope=ExerciseScope.PERSONAL, group_uid="group_123")  # Nonsense

# CORRECT — scope determines whether group_uid is valid
if exercise.scope == ExerciseScope.ASSIGNED:
    assert exercise.group_uid is not None
```

### Don't let ReportSource drift

```python
# WRONG — new report source creates a new EntityType
class AdminSummary(UserOwnedEntity):  # New entity for admin-written reports?
    admin_notes: str

# CORRECT — new report sources are new ReportSource values on existing entities
# ActivityReport with processor_type=ReportSource.HUMAN covers all admin-written activity reports
```

---

## Deep Dive Resources

- [LEARNING_LOOP_ARCHITECTURE.md](/docs/architecture/LEARNING_LOOP_ARCHITECTURE.md) — entry-point overview: two tracks, four phases, how MEGA_QUERY feeds the loop
- [REPORT_ARCHITECTURE.md](/docs/architecture/REPORT_ARCHITECTURE.md) — canonical report reference
- [REPORT_ARCHITECTURE.md](/docs/architecture/REPORT_ARCHITECTURE.md) — canonical report reference — all services, APIs, graph patterns, ReportSource taxonomy, Exercise pipeline
- [ADR-038: Content Sharing Model](/docs/decisions/ADR-038-content-sharing-model.md)
- [ADR-040: Teacher Exercise Workflow](/docs/decisions/ADR-040-teacher-exercise-workflow.md)
- [SHARING_PATTERNS.md](/docs/patterns/SHARING_PATTERNS.md)
- [ENTITY_TYPE_ARCHITECTURE.md](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md)
- [AUDIO_TRANSCRIPTION_ARCHITECTURE.md](/docs/architecture/AUDIO_TRANSCRIPTION_ARCHITECTURE.md) — Deepgram config, batch pipeline, utterance formatting
- [DEEPGRAM_CONFIG.md](/docs/configuration/DEEPGRAM_CONFIG.md) — transcription option reference (`config/deepgram.toml`)

---

## The System Layers

The learning loop is Layer 1 of a 5-layer system:

```
┌────────────────────────────────────────────┐
│  5. Semantics (coherence)                  │
├────────────────────────────────────────────┤
│  4. Knowledge Graph (structural memory)    │
├────────────────────────────────────────────┤
│  3. Saved Interactions (compounding)       │
├────────────────────────────────────────────┤
│  2. ZPD + UserContext (intelligence)       │
├────────────────────────────────────────────┤
│  1. Learning Loop (base) ◄──── THIS SKILL  │
└────────────────────────────────────────────┘
```

The loop generates graph relationships (Layer 4) as the learner works. ZPD (Layer 2) reads
the graph to assess readiness and generates three action types: **unblock** (blocking gaps),
**learn** (proximal zone), **reinforce** (thin evidence). Saved interactions (Layer 3) —
journals, conversations, annotations — compound the signal quality over time. Each loop
iteration makes the next one smarter.

**See:** [zpd skill](../zpd/SKILL.md), [user-context-intelligence skill](../user-context-intelligence/SKILL.md)

---

## Related Skills

- **[zpd](../zpd/SKILL.md)** — Intelligence layer that makes the loop adaptive (Layer 2)
- **[curriculum-domains](../curriculum-domains/SKILL.md)** — Ku, PS, LP architecture (loop substrate)
- **[activity-domains](../activity-domains/SKILL.md)** — Activity Track entry points (parallel reporting via ActivityReport)
- **[user-context-intelligence](../user-context-intelligence/SKILL.md)** — Cross-domain synthesis that feeds ActivityReport
- **[result-pattern](../result-pattern/SKILL.md)** — All services return `Result[T]`
- **[neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md)** — Graph query patterns
- **[pydantic](../pydantic/SKILL.md)** — Request models for submission and feedback routes
- **[prompt-templates](../prompt-templates/SKILL.md)** — `activity_feedback.md` template and PROMPT_REGISTRY
