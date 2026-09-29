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

> **One user-authored type (ADR-054).** Student work is a single `UserEntry(UserOwnedEntity)`
> entity type discriminated by the `Pipeline` enum (`NONE`, `TRANSCRIBE`,
> `TRANSCRIBE_AND_STRUCTURE`, `LLM_SUMMARY`, `EXTRACT_ACTIVITIES`, `TEACHER_REVIEW`,
> `REFERENCE`, `KNOWLEDGE`). The revision count lives on the edge:
> `(UserEntry)-[:FULFILLS_EXERCISE {revision}]->(Exercise)`. Reports record who produced them
> in `processor_type: ReportSource` (`HUMAN`, `LLM`, `HYBRID`, `AUTOMATIC`).
> `Pipeline.EXTRACT_ACTIVITIES` (ADR-069) is an explicit processing branch over UserEntry
> content with `EXTRACTED_FROM` provenance. The UserEntry services live in
> `core/services/user_entry/`; there is no `submissions/` package. Where this skill says
> "submission", it means a turn-in `UserEntry`.
>
> **Journals are outside the loop's entities.** The journal doors run on `JournalService`
> (`core/services/journal/`, the [journals skill](../journals/SKILL.md)): typed text opens a
> discussion (`POST /journals/start`), and files/audio (`POST /journals/upload`) run the DNWF
> path, which writes to `je_out/` and creates **no** `UserEntry` (ADR-073). Don't reintroduce
> graph persistence for private journal uploads. `Pipeline.TRANSCRIBE_AND_STRUCTURE` (a source
> entry transformed into a structured one via `(structured)-[:TRANSFORMS]->(source)`) is legacy,
> preserved for existing `UserEntry` nodes.

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
║  JOURNALS (outside the loop — JournalService, zero-persistence)          ║
║  ────────────────────────────────────────────────────────────────────    ║
║  /journals/upload → Deepgram → DNWF stages → je_out/ (no UserEntry)      ║
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
property are both named **`entity_type`**.

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

**What it is:** Atomic knowledge — a lightweight ontology/reference node, shared across all
users. Ku is the *why* — the knowledge the loop exists to transmit. It is not a phase of the
iterative cycle; it is the substance the cycle is built around. PathStep composes Kus into the
content a learner reads (`(PathStep)-[:USES_KU]->(Ku)`).

**EntityType:** `EntityType.KU`
**Model:** `core/models/ku/ku.py` — `Ku(Entity)` frozen dataclass (not `Curriculum`)
**DTO:** `core/models/ku/ku_dto.py`
**UID format:** `ku.{ns}.{slug}` authored (content vault); `ku_{slug}_{random}` generated (`KuService.create_ku`)
**Neo4j label:** `:Entity:Ku`

**Ku-specific fields** (read the full set off `dataclasses.fields(Ku)`):
```python
aliases: tuple[str, ...]             # Alternative names
nous: tuple[str, ...]                # NOUS topic membership — the category vocabulary
nous_subtopic: tuple[str, ...]       # Sub-topic within a NOUS topic
sel_category: SELCategory | None     # CASEL competency
publication_state: PublicationState  # a draft is withheld from learner-facing reads
```

**Access:** `ContentScope.SHARED` — all users read. No CRUD API: Kus come from content-vault
ingestion or `KuService.create_ku` (EXTRACT_ACTIVITIES).

**Services:**
```python
services.ku                       # KuService facade (4 sub-services)
services.ku.core                  # KuCoreService — create_ku
services.ku.search                # search(), get_by_status(), get_by_category()
services.ku.relationships         # UnifiedRelationshipService (KU_CONFIG)
services.ku.intelligence          # get_with_context(), get_usage_summary(), calculate_user_substance()
```

**Graph pattern:**
```cypher
(ps:Entity:PathStep)-[:USES_KU]->(ku:Entity:Ku)      // PathStep composes Kus
(ku)-[:ORGANIZES {order: 1}]->(child:Entity)         // MOC: any Entity can organize others
(exercise)-[:REQUIRES_KNOWLEDGE]->(ku)               // Exercise links to required Ku
(user:User)-[:MASTERED {mastery_score}]->(ku)        // mastery, propagated from approved reports
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
button on `/gradebook/{uid}`).

**Teacher transition:** students auto-join the default teacher group
(`group_default_{admin_uid}`, oldest HUMAN admin — `@skuel.local` service
accounts excluded) on PathStep enrollment. A `teacher_review` turn-in whose audience is `teachers`
resolves to the exercise's assigned groups the submitter belongs to; a
CURRICULUM-scope exercise is never assigned, so it falls back to the submitter's
default group (`AudienceResolver._expand_teachers` in
`core/services/user_entry/audience_resolver.py`). The write is a feedback request
(`SUBMITTED_TO_GROUP`, ADR-088 §2), not a share, and it lands in `/teaching/queue`.

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

| Service | Test File |
|---------|-----------|
| `TeacherReviewService` | `tests/unit/services/test_teacher_review_service.py` |
| `UserEntryService` | `tests/unit/services/test_user_entry_service.py` |

**TeacherReviewService tests cover:** access control (`_verify_teacher_has_group_access` — the entry must be `SUBMITTED_TO_GROUP` an active group the teacher owns, ADR-088 §2), review queue filtering, report submission + event publishing, revision requests, approval with mastery updates, dashboard stats, group management, exercise/student views.

**UserEntryService tests cover:** the consolidated `UserEntry` write path (ADR-054) — `create_entry`, exercise linking, pipeline dispatch, and ownership/access checks across the file-upload and structured-form entry modes.

---

## Key Source Files

| File | Phase | Purpose |
|------|-------|---------|
| `core/models/ku/ku.py` | substrate | Ku frozen dataclass |
| `core/models/exercises/exercise.py` | 1 | Exercise frozen dataclass |
| `core/models/exercises/revised_exercise.py` | 4 | RevisedExercise frozen dataclass |
| `core/services/revised_exercises/revised_exercise_service.py` | 4 | RevisedExercise CRUD + chain queries |
| `adapters/inbound/revised_exercises_api.py` | 4 | RevisedExercise API routes (teacher + student-facing) |
| `adapters/inbound/revised_exercises_ui.py` | 4 | RevisedExercise detail + hub preview (GradeBook shell) |
| `adapters/inbound/entry_reports_ui.py` | 3 | EntryReport UI routes (list + detail page) |
| `ui/learning_loop/revised_exercise.py` | 4 | RevisedExercise renderers (detail, card, list views) |
| `ui/learning_loop/report.py` | 3 | EntryReport renderers (detail page with outcome/processor badges) |
| `ui/patterns/modal.py` | support | AlpineModal — standardized Alpine.js modal wrapper |
| `core/ports/curriculum_protocols.py` | 4 | `RevisedExerciseOperations` protocol |
| `core/models/user_entry/user_entry.py` | 2 | UserEntry frozen dataclass (`UserOwnedEntity`) |
| `core/models/report/entry_report.py` | 3 | EntryReport model |
| `core/models/report/activity_report.py` | parallel | ActivityReport model |
| `core/services/user_entry/user_entry_service.py` | 2 | UserEntry facade (BaseService) — shared `create_entry` write path, exercise linking |
| `core/services/user_entry/user_entry_processing_service.py` | 2 | Pipeline processing — transcription, LLM summary/structure, activity extraction |
| `core/services/report/entry_report_service.py` | 3 | AI report generation (via UnifiedLLMCaller) |
| `core/services/llm_caller.py` | 3 | Unified LLM routing (OpenAI/Anthropic by model prefix) |
| `core/services/output/instruction_resolver.py` | 2 | Instruction resolution (custom > exercise > mode > default) |
| `core/services/transcription/batch_transcription_service.py` | 2 | Batch audio → txt (Tier 1, config via `config/deepgram.toml`) |
| `config/deepgram.toml` | 2 | Deepgram options — model, utterances, intelligence, vocabulary |
| `core/config/deepgram_config.py` | 2 | Config loader for `config/deepgram.toml` |
| `core/services/report/progress_report_generator.py` | parallel | ActivityReport generation |
| `core/services/report/activity_report_service.py` | parallel | Admin human report; all write paths converge here |
| `core/services/report/teacher_review_service.py` | 3+4 | Teacher review workflow (review queue, revision, approval) |
| `core/ports/user_entry_protocols.py` | 2 | UserEntry protocols — backend port (`UserEntryOperations`) + CRUD/lifecycle/assessment/report-query/content sub-protocols |
| `core/ports/report_protocols.py` | 3 | All report protocols incl. `TeacherReviewOperations`, `ReviewQueueOperations`, `ReportRelationshipOperations` — typed returns (`ReviewRequestResult`, `PendingReviewItem`, `GroupMemberProgress`) |
| `core/ports/group_protocols.py` | support | `GroupOperations` only (group CRUD + membership) |
| `core/services/sharing/unified_sharing_service.py` | support | Entity-agnostic sharing |
| `adapters/persistence/neo4j/backends/` | all | Domain-specific Cypher (clustered files: activity, curriculum, exercise, user_entry, sharing, forms, collab, misc, …) |
| `adapters/inbound/user_entry_ui.py` | 2+3 | The Submit page (`/submissions/submit`), gradebook detail (`/gradebook/{uid}`), feedback display |
| `adapters/inbound/user_entry_api.py` | 2 | UserEntry API (`POST /api/user-entries/upload` file-upload door) |
| `adapters/inbound/teaching_ui.py` | 3+4 | Students (default page), review queue (`/teaching/queue`), student detail with KU tab, groups |
| `adapters/inbound/teaching_forms_ui.py` | — | Forms visibility: template list, per-template submissions, submission detail (teacher role) |
| `adapters/inbound/teaching_api.py` | 3+4 | Teacher API (review queue, revision, approve, students, groups) |
| `adapters/inbound/exchange_ui.py` | 2–4 | `/exchange` thread view — one (student, exercise) exchange chronologically (renderer: `ui/learning_loop/exchange_thread.py`) |
| `ui/patterns/report_item.py` | 3 | Shared report-item rendering (`render_report_item`; teaching review UI) |
| `core/prompts/templates/activity_feedback.md` | parallel | LLM prompt template (via PROMPT_REGISTRY) |

---

## Code Walkthrough

The end-to-end sequential walkthroughs — the Curriculum Track (artifact-based) and the Activity Track (aggregate-based) — live in **[reference.md](reference.md#code-walkthrough)**.

---

## Anti-Patterns

### Don't create a feedback model that inherits UserEntry when it has no file fields

```python
# WRONG — ActivityReport does not have file uploads
class ActivityReport(UserEntry):  # No! UserEntry has file_path, file_size, etc.

# CORRECT — ActivityReport inherits UserOwnedEntity directly
class ActivityReport(UserOwnedEntity):  # No file fields — it's about patterns, not artifacts
```

### Don't put cross-domain Cypher on a single domain backend

```python
# WRONG — ProgressReportGenerator needs Tasks + Goals + Habits + ...
class ReportBackend(UniversalNeo4jBackend):
    async def get_all_activity_completions(self):
        # Can't do this from one domain backend

# CORRECT — cross-domain aggregation uses UserContext.build_rich() (the MEGA-QUERY)
class ProgressReportGenerator:
    def __init__(self, executor: QueryExecutor, activity_report_service: ActivityReportService,
                 context_builder: UserContextBuilder, ...):
        # context_builder.build_rich(user_uid, window=...) — the MEGA-QUERY with the
        # activity window on its six activity sections; entities_rich covers all Activity Domains
        # annotation, cooldown and habit-completion reads go through report_backend
        # (ActivityReportGeneratorBackendOperations) — no Cypher in the service
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

- [LEARNING_LOOP_ARCHITECTURE.md](/docs/architecture/LEARNING_LOOP_ARCHITECTURE.md) — entry-point overview: two tracks, four phases, how the MEGA-QUERY feeds the loop
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
