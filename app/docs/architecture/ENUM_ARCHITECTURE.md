# Enum Architecture
*Last updated: 2026-07-19*

> **Core Principle:** "Enums define behavior, services consume it"

SKUEL has **94 enum classes** across **19 files** in `core/models/enums/`. Enums are not just value holders — they carry display logic, scoring, search, validation, and transition rules. This document maps the enum landscape, explains the two most important enums (EntityType and EntityStatus), catalogs per-domain enums, and documents the recurring dynamic patterns.

---

## File Map

Every enum lives in exactly one file. The `__init__.py` re-exports all public enums so downstream code imports from `core.models.enums`.

| File | Purpose | Key Enums |
|------|---------|-----------|
| `entity_enums.py` | Core identity, lifecycle, domain classification | EntityType, EntityStatus, ContentOrigin, Domain, NonKuDomain, ContentScope |
| `activity_enums.py` | Priority, Confidence, calendar types, dual-track assessment | Priority, Confidence, ActivityType, 5 assessment levels |
| `goal_enums.py` | Goal classification | GoalType, GoalTimeframe, MeasurementType, HabitEssentiality |
| `habit_enums.py` | Habit classification and completion | HabitPolarity, HabitCategory, HabitDifficulty, CompletionStatus |
| `askesis_enums.py` | Askesis query complexity and integration | QueryComplexity, IntegrationSuccess |
| `choice_enums.py` | Decision types | ChoiceType |
| `principle_enums.py` | Principle classification and alignment | PrincipleCategory, PrincipleSource, PrincipleStrength, AlignmentLevel, TriggerType |
| `pipeline.py` | User entry processing dispatch + report provenance (ADR-054, supersede ProcessorType) | Pipeline, ReportSource |
| `user_entry_enums.py` | User entry (submissions/journal) processing and scheduling | SubmissionModality, ExerciseScope, EnrichmentMode, ScheduleType, ProgressDepth |
| `curriculum_enums.py` | Learning path and step types | LpType, StepDifficulty |
| `lifepath_enums.py` | Vision theme classification | ThemeCategory |
| `scheduling_enums.py` | Time, recurrence, energy | RecurrencePattern, TimeOfDay, EnergyLevel |
| `learning_enums.py` | Education, knowledge, mastery, assessment, feedback | MasteryImpact, AssessmentOutcome, FeedbackCategory, LearningLevel, EducationalLevel, MasteryStatus, ContentType, SELCategory |
| `metadata_enums.py` | Relationships, search, system config | RelationshipType (59 values), Intent, Visibility, SystemConstants |
| `user_enums.py` | User roles, health scoring, and journal config | UserRole, ContextHealthScore, JournalTier, JournalMode |
| `transcription_enums.py` | Transcription processing | TranscriptionStatus |
| `interaction_enums.py` | Learning-loop interaction records | InteractionType, InteractionResult |
| `relationship_enums.py` | Knowledge-relationship qualifiers | ProficiencyLevel, KnowledgeRelevance |
| `neo_labels.py` | Neo4j node labels | NeoLabel (62 labels) |

**Import convention:**
```python
from core.models.enums import EntityType, EntityStatus, Priority
```

---

## The Two Core Enums

### EntityType — What Is It? (25 values)

EntityType is the type discriminator for every entity in SKUEL. It lives on the `entity_type` field of every Entity and determines valid statuses, default status, content origin, ownership rules, and Neo4j labels.

**Nine groups:**

| Group | EntityTypes | Ownership | Neo4j Labels |
|-------|-------------|-----------|--------------|
| **Knowledge** (atomic curriculum) | KU, RESOURCE | Admin-created, no user_uid | :Entity:Ku, :Entity:Resource |
| **Curriculum Structure** | PATH_STEP, LEARNING_PATH, EXERCISE | Admin-created, no user_uid | :Entity:PathStep, :Entity:LearningPath, :Entity:Exercise |
| **Forms** | FORM_TEMPLATE, FORM_SUBMISSION | Template: admin-created; Submission: user-owned | :Entity:FormTemplate, :Entity:FormSubmission |
| **UserEntry** | USER_ENTRY | User-owned | :Entity:UserEntry |
| **Reports** | ENTRY_REPORT, ACTIVITY_REPORT | User-owned | :Entity:EntryReport, :Entity:ActivityReport |
| **Activity** (user-owned) | TASK, GOAL, HABIT, EVENT, CHOICE, PRINCIPLE | User-owned | :Entity:Task, :Entity:Goal, etc. |
| **Activity Templates** (PS-owned, spawn instances on engagement) | TASK_TEMPLATE, GOAL_TEMPLATE, HABIT_TEMPLATE, EVENT_TEMPLATE, CHOICE_TEMPLATE, PRINCIPLE_TEMPLATE | Curriculum-authored, no user_uid | :Entity:TaskTemplate, etc. |
| **Learning-loop record** | INTERACTION | User-owned (system-written) | :Entity:Interaction |
| **Hybrid/Destination** | REVISED_EXERCISE, LIFE_PATH | User-owned | :Entity:RevisedExercise, :Entity:LifePath |

**Content Origin tiers** (derived from EntityType via `.content_origin()`):

| Tier | ContentOrigin | EntityTypes |
|------|---------------|-------------|
| A | CURATED | Resource, FormTemplate |
| B | CURRICULUM | KU, PathStep, LearningPath, Exercise, all 6 Activity Templates |
| C | USER_CREATED | All 6 Activity types + UserEntry, LifePath, FormSubmission, RevisedExercise, Interaction |
| D | REPORT | ActivityReport, EntryReport |

**Key methods:**

| Method | Returns | Purpose |
|--------|---------|---------|
| `is_activity()` | bool | Is it one of the 6 user activity domains? |
| `is_activity_template()` | bool | Is it one of the 6 PS-owned Activity Template types? |
| `instance_type()` | EntityType | Template → spawned instance type (e.g. TASK_TEMPLATE → TASK); raises ValueError if not a template |
| `template_type()` | EntityType | Instance → template type (e.g. TASK → TASK_TEMPLATE); raises ValueError if not an activity |
| `is_knowledge()` | bool | Is it Ku or PathStep (atomic/composed knowledge)? |
| `is_applied_knowledge()` | bool | Is it Exercise or RevisedExercise (instruction/revision templates, subordinate to PathStep)? |
| `is_curriculum_structure()` | bool | Is it LearningPath (organisational structure only — NOT Exercise)? |
| `is_content_processing()` | bool | Is it in the processing chain (UserEntry, etc.)? |
| `is_user_owned()` | bool | Does it require a user_uid? |
| `valid_statuses()` | frozenset[EntityStatus] | Which statuses are valid for this type? |
| `default_status()` | EntityStatus | What status does a new entity get? |
| `content_origin()` | ContentOrigin | Which content tier (A-D)? |
| `from_string(text)` | EntityType \| None | Parse with alias support ("ps" → PATH_STEP, "lp" → LEARNING_PATH, "ku" → KU, "book"/"film"/"talk" → RESOURCE) |

### Canonical Values vs Aliases — the Emission Rule

The enum defines ONE canonical vocabulary and one alias layer, with a strict direction of flow:

- **Canonical values** (`"path_step"`, `"learning_path"`, ...) are what the enum serializes to. Neo4j stores them in the `entity_type` property; search results carry them in `_domain` stamps; facet counts key on them.
- **Aliases** (`"ps"`, `"step"`, `"lp"`, `"knowledge"`, ...) exist for humans. They are registered in one map (`entity_enums.py`) and resolved by one function, `EntityType.from_string()`.

**The rule: aliases are input-only.** A human may type `ps` in a DSL line, a hand-edited URL, or vault YAML — `from_string()` resolves it once at the boundary. After that, the system speaks canonical values on every machine channel: payloads, stamps, query params it emits, and `<select>` option values (visible labels stay human — "Path Steps"). Emitting an alias on a machine channel creates a second dialect that some later comparison has to translate — the search breakdown chips needed exactly such a shim (`_DOMAIN_TO_TYPE_OPTION`, since deleted) before the Type dropdown switched to canonical wire values.

**Carve-out — route segments are naming, not entity_type values.** URL path segments (`/explore/ps/{uid}`, `/api/lp/{uid}/children`, plural `/api/tasks/...`) and code identifiers (`services.ps`) are route design, like a variable name. They may be short. The constraint on them is the inverse: never compare a route-segment token against an `entity_type` value without going through `from_string()` — a segment token is not an EntityType and must not pretend to be one.

**Litmus test:** if a value ends up compared against an `entity_type` field, a `_domain` stamp, or parsed into `EntityType` — it must be canonical. If it only selects a route or a service, it is a name.

### EntityStatus — Where Is It? (14 values)

EntityStatus tracks lifecycle across all entity types. Not every status applies to every type — `valid_statuses()` constrains which statuses each EntityType can use.

**Status categories:**

| Category | Statuses | Meaning |
|----------|----------|---------|
| **Pending** | DRAFT, SUBMITTED, QUEUED, SCHEDULED | Not yet active |
| **Active** | PROCESSING, ACTIVE | Work in progress |
| **Paused** | PAUSED, BLOCKED, POSTPONED | Temporarily stopped |
| **Terminal** | COMPLETED, FAILED, CANCELLED, ARCHIVED | No further progression |
| **Special** | REVISION_REQUESTED | Completed but sent back |

**Two lifecycle patterns:**

```
Content Processing:
  DRAFT → SUBMITTED → QUEUED → PROCESSING → COMPLETED / FAILED
                 ↑                               |          |
                 |                        REVISION_REQUESTED |
                 |                          ↓ DRAFT    ↓ COMPLETED (teacher approves)
                 +───────── reprocessing path ───────────────+

Activity:
  DRAFT → SCHEDULED → ACTIVE → PAUSED → COMPLETED
              |           |       |
              |           +→ BLOCKED → ACTIVE
              |           |
              +→ POSTPONED    +→ CANCELLED / FAILED
```

**Reprocessing path:** COMPLETED → SUBMITTED and FAILED → SUBMITTED are valid transitions
for content-processing entities (UserEntry). Used by
`SubmissionsProcessingService.reprocess_submission()` to retry or re-evaluate submissions.
Non-submission entity types can't use this path — they don't have SUBMITTED in their
`valid_statuses()`.

**Transition enforcement — two paths:**

1. **Processing pipeline:** `SubmissionsService.update_submission_status()` validates every
   status change via `can_transition_to(target, entity_type)` before persisting. Invalid
   transitions return `Errors.validation()` with the from/to/entity_type. This is the
   chokepoint for all processing pipeline status changes (QUEUED, PROCESSING, COMPLETED, FAILED).

2. **Teacher review:** `TeacherReviewService` methods enforce transitions atomically in Cypher
   via `WHERE submission.status IN $allowed_from_statuses` guards on `create_report_node()`
   and `approve_and_get_linked_kus()`. This is race-safe — no gap between read and write.
   Allowed transitions: PROCESSING→COMPLETED (submit_report), COMPLETED→REVISION_REQUESTED
   (request_revision), REVISION_REQUESTED→COMPLETED (approve_report).

**Valid statuses per EntityType (summary):**

| EntityType | Valid Statuses | Default |
|------------|---------------|---------|
| Ku, Resource | DRAFT, COMPLETED, ARCHIVED | COMPLETED (vault-ingested content arrives complete) |
| EntryReport | DRAFT, COMPLETED, ARCHIVED | DRAFT |
| PathStep, LearningPath, Exercise, Choice | DRAFT, ACTIVE, COMPLETED, ARCHIVED | DRAFT |
| UserEntry | DRAFT, SUBMITTED, QUEUED, PROCESSING, COMPLETED, FAILED, REVISION_REQUESTED, ARCHIVED | DRAFT |
| ActivityReport | COMPLETED (generated artifact — written post-generation, always complete) | COMPLETED |
| Task | DRAFT, SCHEDULED, ACTIVE, PAUSED, BLOCKED, COMPLETED, CANCELLED, POSTPONED, FAILED | DRAFT |
| Goal | DRAFT, ACTIVE, PAUSED, COMPLETED, CANCELLED, FAILED, ARCHIVED | DRAFT |
| Habit | ACTIVE, PAUSED, COMPLETED, CANCELLED, ARCHIVED | ACTIVE |
| Event | SCHEDULED, ACTIVE, COMPLETED, CANCELLED | SCHEDULED |
| Principle | ACTIVE, PAUSED, ARCHIVED | ACTIVE |
| LifePath | ACTIVE, ARCHIVED | ACTIVE |
| Interaction | ACTIVE, ARCHIVED (immutable event record — outcome lives on `result_status`) | ACTIVE |
| Activity Templates (all 6) | DRAFT, ACTIVE, ARCHIVED (publish-and-engage — instances complete, templates don't) | DRAFT |
| FormTemplate | DRAFT, ACTIVE, COMPLETED, ARCHIVED | DRAFT |
| FormSubmission | DRAFT, COMPLETED, ARCHIVED | COMPLETED |

**Key methods:**

| Method | Returns | Purpose |
|--------|---------|---------|
| `is_terminal()` | bool | COMPLETED, FAILED, CANCELLED, or ARCHIVED? |
| `is_active()` | bool | SUBMITTED, QUEUED, PROCESSING, ACTIVE, or SCHEDULED? |
| `is_pending()` | bool | DRAFT, SUBMITTED, QUEUED, or SCHEDULED? |
| `can_transition_to(target, entity_type)` | bool | Is this transition valid (optionally type-aware)? Enforced by `update_submission_status()` |
| `get_color()` | str | Hex color for UI (e.g., ACTIVE="#06B6D4" cyan, BLOCKED="#DC2626" red) |
| `from_search_text(text)` | list[EntityStatus] | Find statuses matching search terms |

### Two Layers of Status Checks

Status checks live at two levels, each with a distinct purpose:

**Layer 1 — `EntityStatus` enum methods** operate on the status value itself. Use these when you have a status value (e.g., from a query filter or transition check) and need to classify it without an entity instance:

```python
status = EntityStatus.COMPLETED
status.is_terminal()    # True — COMPLETED, FAILED, CANCELLED, ARCHIVED
status.is_active()      # False
status.is_pending()     # False
status.can_transition_to(EntityStatus.ARCHIVED)  # True
```

**Layer 2 — `Entity` model properties** operate on the entity instance. Use these in service/route code when you have an entity and need to branch on its current state:

```python
task: Task = ...
task.is_completed    # @property — checks status == EntityStatus.COMPLETED
task.is_draft        # @property — checks status == EntityStatus.DRAFT
task.is_processing   # @property — checks status == EntityStatus.PROCESSING
task.is_failed       # @property — checks status == EntityStatus.FAILED
task.is_archived     # @property — checks status == EntityStatus.ARCHIVED
task.is_shareable()  # method — True only when COMPLETED (quality control)
```

**When to use which:**

| Situation | Use | Example |
|-----------|-----|---------|
| Checking an entity's current state | Entity properties | `if task.is_completed:` |
| Classifying a status value (no entity) | Enum methods | `if status.is_terminal():` |
| Validating a state transition | Enum methods | `status.can_transition_to(target, entity_type)` |
| Filtering/querying by status category | Enum methods | `[s for s in statuses if s.is_active()]` |

Entity properties are defined on the `Entity` base class (`core/models/entity.py`), so they are available on all 25 entity types. They are simple one-liner `@property` methods — no configuration or overrides needed because all types share the single `EntityStatus` enum.

### How They Interact

EntityType and EntityStatus cross-reference each other:

```python
# EntityType constrains valid statuses
EntityType.TASK.valid_statuses()
# → frozenset({DRAFT, SCHEDULED, ACTIVE, PAUSED, BLOCKED, COMPLETED, CANCELLED, POSTPONED, FAILED})

# EntityType provides default status
EntityType.HABIT.default_status()   # → EntityStatus.ACTIVE
EntityType.EVENT.default_status()   # → EntityStatus.SCHEDULED

# EntityStatus checks type-aware transitions
EntityStatus.ACTIVE.can_transition_to(EntityStatus.BLOCKED, entity_type=EntityType.TASK)   # → True
EntityStatus.ACTIVE.can_transition_to(EntityStatus.BLOCKED, entity_type=EntityType.EVENT)  # → False
```

This is why EntityType and EntityStatus live in the same file (`entity_enums.py`) — they form a tightly coupled validation system.

---

## Model Integration

Enums wire into the model layer through a class hierarchy. Each level inherits enum fields and adds domain-specific ones. Every model forces its `entity_type` in `__post_init__()`, which drives status validation, default status, and Neo4j labels.

**For the full picture** — class hierarchy, per-model enum fields, three-tier flow, directory layout, and sub-entities — see [Model Architecture](MODEL_ARCHITECTURE.md).

**Quick reference — enum fields by model tier:**

| Base Class | Enum Fields | Models |
|------------|-------------|--------|
| Entity | entity_type, status, visibility | *(all 25 entity types)* |
| UserOwnedEntity | *(inherits above)* | Task, Goal, Habit, Event, Choice, Principle, Submission types, LifePath |
| Curriculum *(base class)* | + complexity, learning_level, sel_category | PathStep, LearningPath, Exercise |

Domain-specific enum fields: Goal (+3), Habit (+3), Principle (+4), Choice (+1), Submission (+1), LifePath (+1), PathStep (+1), LearningPath (+1), Exercise (+1).

---

## Domain Enum Map

### Cross-Domain (used by multiple domains)

| Enum | File | Values | Used By |
|------|------|--------|---------|
| Priority | activity_enums.py | LOW, MEDIUM, HIGH, CRITICAL | All UserOwnedEntity nodes (Tasks, Goals, Habits, Events, Choices, Principles, Submissions, LifePath) |
| Confidence | activity_enums.py | UNCERTAIN, LOW, MEDIUM, HIGH, CERTAIN | Curriculum entities (KU, PS, LP); lateral relationship edges (all 9 domains) |
| ActivityType | activity_enums.py | TASK, HABIT, EVENT, LEARNING, MILESTONE, ... (12) | Calendar, scheduling |
| EngagementState | activity_enums.py | ENGAGED, OWNED | All 6 Activity Domain instances spawned from a PathStep template; `None` = standalone (not curriculum-spawned) |
| RecurrencePattern | scheduling_enums.py | NONE, DAILY, WEEKLY, MONTHLY, ... (9+) | Habits, events, reports |
| TimeOfDay | scheduling_enums.py | EARLY_MORNING, MORNING, ... ANYTIME (7) | Scheduling services |
| EnergyLevel | scheduling_enums.py | LOW, MEDIUM, HIGH, VARIABLE | Task/habit scheduling |

### Per-Domain Enums

**Goals** (`goal_enums.py`):

| Enum | Values | Purpose |
|------|--------|---------|
| GoalType | OUTCOME, PROCESS, LEARNING, PROJECT, MILESTONE, MASTERY | What kind of goal |
| GoalTimeframe | DAILY, WEEKLY, MONTHLY, QUARTERLY, YEARLY, MULTI_YEAR | Expected duration |
| MeasurementType | BINARY, PERCENTAGE, NUMERIC, MILESTONE, HABIT_BASED, ... (8) | How progress is measured |
| HabitEssentiality | ESSENTIAL, CRITICAL, SUPPORTING, OPTIONAL | Habit importance to goal (Atomic Habits) |

**Habits** (`habit_enums.py`):

| Enum | Values | Purpose |
|------|--------|---------|
| HabitPolarity | BUILD, BREAK, NEUTRAL | Direction of change |
| HabitCategory | HEALTH, FITNESS, MINDFULNESS, LEARNING, ... (9) | Classification |
| HabitDifficulty | TRIVIAL, EASY, MODERATE, CHALLENGING, HARD | Maintenance difficulty |
| CompletionStatus | DONE, PARTIAL, SKIPPED, MISSED, PAUSED | Daily completion tracking |

CompletionStatus has dynamic methods: `counts_as_success()` (DONE and PARTIAL count), `get_emoji()`.

**Choices** (`choice_enums.py`):

| Enum | Values | Purpose |
|------|--------|---------|
| ChoiceType | BINARY, MULTIPLE, RANKING, ALLOCATION, STRATEGIC, OPERATIONAL | Decision type |

**Principles** (`principle_enums.py`):

| Enum | Values | Purpose |
|------|--------|---------|
| PrincipleCategory | SPIRITUAL, ETHICAL, RELATIONAL, PERSONAL, ... (8) | Life domain |
| PrincipleSource | PHILOSOPHICAL, RELIGIOUS, CULTURAL, PERSONAL, ... (7) | Origin/tradition |
| PrincipleStrength | CORE, STRONG, MODERATE, DEVELOPING, EXPLORING | How deeply held |
| AlignmentLevel | FLOURISHING (1.0), ALIGNED (0.85), ... UNKNOWN (0.0) — 8 values | Alignment scoring |
| TriggerType | GOAL, HABIT, EVENT, CHOICE, MANUAL | What activates a principle |

AlignmentLevel has `to_score()` / `from_score()` methods for the dual-track assessment pattern, and `get_color()` for UI rendering (green/yellow/red).

**Submissions + Reports** (`pipeline.py` for `Pipeline`/`ReportSource`; `user_entry_enums.py` for the rest):

| Enum | Values | Purpose |
|------|--------|---------|
| Pipeline | NONE, TRANSCRIBE, TRANSCRIBE_AND_STRUCTURE, LLM_SUMMARY, EXTRACT_ACTIVITIES, TEACHER_REVIEW | User entry processing dispatch. Replaces `ProcessorType`. |
| ReportSource | HUMAN, LLM, HYBRID, AUTOMATIC | Provenance of a report. Replaces `ProcessorType`. |
| SubmissionModality | FILE_UPLOAD, STRUCTURED_FORM | Submission format: file upload vs inline form. Set on `Exercise.expected_modality` (auto-derived from `form_schema`) and `UserEntry.modality` (set at creation). Orthogonal to `Pipeline` (what processes) — modality is *how* the submission was created. |
| ExerciseScope | PERSONAL, ASSIGNED, ASSESSMENT, CURRICULUM | Exercise scope (user's own / teacher-assigned / formal test / content-vault-authored). Enforced at Pydantic boundary (`ExerciseCreateRequest.scope`) and all comparison sites — zero raw string comparisons remain. |
| EnrichmentMode | ACTIVITY_TRACKING, IDEA_ARTICULATION, CRITICAL_THINKING | Journal LLM processing strategy. Used on `Exercise.enrichment_mode` and `UserEntry.enrichment_mode`. Maps to prompt templates via `InstructionResolver._MODE_TEMPLATE_MAP`. |
| ScheduleType | WEEKLY, BIWEEKLY, MONTHLY | Progress report frequency |
| ProgressDepth | SUMMARY, STANDARD, DETAILED | Report detail level |

**Curriculum** (`curriculum_enums.py`):

| Enum | Values | Purpose |
|------|--------|---------|
| LpType | STRUCTURED, ADAPTIVE, EXPLORATORY, REMEDIAL, ACCELERATED | Learning path behavior |
| StepDifficulty | TRIVIAL, EASY, MODERATE, CHALLENGING, ADVANCED | Step difficulty |

**LifePath** (`lifepath_enums.py`):

| Enum | Values | Purpose |
|------|--------|---------|
| ThemeCategory | PERSONAL_GROWTH, CAREER, HEALTH, RELATIONSHIPS, ... (10) | Vision theme classification |

### Infrastructure Enums

**Learning** (`learning_enums.py`) — 12 enums for education/knowledge tracking:
- `MasteryImpact` (MINOR, MODERATE, MAJOR, CERTIFICATION — controls mastery score advancement per Exercise, with `get_ai_score()`, `get_teacher_score()`, `get_label()`, `get_description()`, `sort_order()`, `from_value()`)
- `AssessmentOutcome` (APPROVED, NEEDS_REVISION, AI_EVALUATED — self-describing report decisions)
- `FeedbackCategory` (ACCURACY, COMPLETENESS, DEPTH, CLARITY, APPLICATION, METHODOLOGY — classifies learning gap type on RevisedExercise.feedback_points, with `get_label()`, `get_color()`, `get_description()`)
- `LearningLevel` (BEGINNER → EXPERT, with `to_numeric()`, `can_handle()`, `sort_order()`, `from_value()`)
- `EducationalLevel` (ELEMENTARY → LIFELONG, with `get_age_range()`, `to_numeric()`)
- `MasteryStatus` (NOT_STARTED → MASTERED, 7-level progression, with `sort_order()`, `rank()`, `from_value()`)
- `KnowledgeStatus` (DRAFT → UNDER_REVIEW, with `to_activity_status()`)
- `ContentType` (CONCEPT, PRACTICE, THEORY, ... 12 values for faceted search)
- `SELCategory` (5 SEL framework categories)
- `KuComplexity` (BASIC, MEDIUM, ADVANCED, with `sort_order()`, `from_value()`)

**User** (`user_enums.py`):
- `UserRole` — 4-tier hierarchy: REGISTERED < MEMBER < TEACHER < ADMIN. Has `has_permission()` for hierarchy-aware checks. Use `UserRole.from_string()` for Neo4j-sourced values — zero raw string comparisons remain.
- `ContextHealthScore` — POOR (0.25), FAIR (0.50), GOOD (0.75), EXCELLENT (1.0). UI display methods.
- `JournalTier` — STANDARD (single-response workflow) / FOUNDER (DNWF three-stage). Orthogonal to UserRole.
- `JournalMode` — SCRIBE (Stage 1, faithful record) / THOUGHT_PARTNER (Stage 2, patterns + challenge) / WHAT_IS_RELATED (Stage 3, graph connections). Selects DNWF function, not tone. Default: THOUGHT_PARTNER. Use `JournalMode.from_string()` for form-submitted values.

**Metadata** (`metadata_enums.py`) — System-wide configuration:
- `RelationshipType` (59 values — all entity relationship types)
- `Intent` (23 values — user intent classification)
- `Visibility` (PRIVATE, SHARED, TEAM, PUBLIC)
- `SystemConstants` (class with thresholds: MASTERY_THRESHOLD=0.8, etc.)
- Plus: ResponseTone, Personality, GuidanceMode, MessageRole, ConversationState, CacheStrategy, TrendDirection, HealthStatus, SeverityLevel, ErrorSeverity

**Transcription** (`transcription_enums.py`):
- `TranscriptionStatus` — PENDING, PROCESSING, COMPLETED, FAILED. Has `is_terminal()` and `can_retry()`.

**Interaction** (`interaction_enums.py`):
- `InteractionType` (4 values) — what kind of learning-loop event an Interaction records; `InteractionResult` (5 values) — the outcome stamped on the record (its `result_status` field — Interaction's EntityStatus never transitions).

**Relationship properties** (`relationship_enums.py`):
- `ProficiencyLevel` (4 values) — proficiency on knowledge/skill relationships; `KnowledgeRelevance` (3 values) — how a principle or goal relates to a knowledge unit.

**Neo4j Labels** (`neo_labels.py`):
- `NeoLabel` — 62 labels mapping to Neo4j node types. `from_entity_type()` bridges EntityType → Neo4j label. `is_valid()` validates label strings.

**Vocabulary enforcement (SKUEL030 / CYP011, since 2026-07-19):** `NeoLabel` and
`RelationshipName` are not merely *available* below the boundary — they are *enforced*
there. Every label and relationship type written in `adapters/persistence/**` Cypher
(Python string literals via SKUEL030, standalone `.cypher` files via CYP011) must be a
registered member. Neo4j validates neither, so an unregistered name matches zero rows
silently rather than erroring; the linter is the only thing that catches it.

This is a *vocabulary* check, not an interpolation-style check — a plain `[:OWNS]` literal
below the boundary is fine, and SKUEL013's enum-interpolation requirement stops at the
boundary. The linters read the enum members by AST-parsing these two files, so the check
cannot drift from the declaration site. See
[linter_rules.md § SKUEL030](../patterns/linter_rules.md) and the open findings in
[CYPHER_VOCABULARY_FINDINGS.md](../patterns/CYPHER_VOCABULARY_FINDINGS.md).

**Contract view (step 5, since 2026-07-19):** the enforced vocabulary plus its registry
metadata is emitted as one reviewable YAML artifact —
[`docs/reference/GRAPH_CONTRACT.yaml`](../reference/GRAPH_CONTRACT.yaml), generated by
`scripts/generate_graph_contract.py`. The enums are the completeness spine (all 182
relationship types + 62 labels appear, so the view can never imply an unconfigured name
doesn't exist); `relationship_registry.py` is the sole metadata source (direction, target
label, ordering, ingestion mapping, lateral semantics); SKUEL030-baselined names appear
only under `findings:`, marked as known silent-zero bugs — never as vocabulary.
`contract: null` records the mechanical fact that the generic relationship machinery has
no config for a name, not a judgment that the edge is unmodelled — registry membership is
conditional by design (see the maintenance note in `relationship_names.py`), and the
`meta.coverage` counts make registry growth (e.g. the semantic-relationship-layer roadmap)
diffable over time. Each configured label also names its semantic-layer `semantic_types`
(the precise `SemanticRelationshipType` predicates its `find_by_semantic_filter` defaults
to), and a `semantic_edge_properties:` section declares the typed base edge-property vocabulary
a semantic edge may carry — sourced from `RelationshipMetadata.to_neo4j_properties()` plus
`semantic_type`, so Phase 4's confidence-weighted traversal has a declared surface to key
on (roadmap Phase 2). The set is not hard-closed: an `open_extension` marker flags
`RelationshipMetadata.properties` (a free-form map merged verbatim, unused by any caller
today) so the typed list is never read as exhaustive. The artifact is checked in; a unit drift test
(`tests/unit/scripts/test_generate_graph_contract.py`) regenerates and byte-compares it,
so a registry or enum change that lands without rerunning the generator fails CI.

---

## Dynamic Enum Patterns

SKUEL enums carry behavior through six recurring patterns:

### 1. Search-Aware Enums

Enums that support natural language search via `get_search_synonyms()` and `from_search_text()`:

```python
# Find statuses matching user search
EntityStatus.from_search_text("in progress")  # → [EntityStatus.ACTIVE]
EntityStatus.from_search_text("done")          # → [EntityStatus.COMPLETED]

# Find priorities
Priority.from_search_text("urgent")  # → [Priority.HIGH, Priority.CRITICAL]
```

**Enums with search support:** EntityStatus, Priority, Domain, LearningLevel, ContentType

### 2. Numeric Scoring

Enums that convert to/from float scores (0.0–1.0) via `to_score()` / `from_score()`:

```python
AlignmentLevel.FLOURISHING.to_score()    # → 1.0
AlignmentLevel.from_score(0.72)           # → AlignmentLevel.MOSTLY_ALIGNED
AlignmentLevel.from_score(0.72).get_color()  # → "green"

ProductivityLevel.PRODUCTIVE.to_score()   # → 0.8
ConsistencyLevel.from_score(0.35)         # → ConsistencyLevel.INCONSISTENT
```

**Enums with scoring:** AlignmentLevel, ProductivityLevel, ProgressLevel, ConsistencyLevel, EngagementLevel, DecisionQualityLevel, ContextHealthScore

### 3. UI Display

Enums that provide colors and icons for rendering:

```python
Priority.HIGH.get_color()                 # → "#F59E0B" (amber)
EntityStatus.ACTIVE.get_color()           # → "#06B6D4" (cyan)
AlignmentLevel.FLOURISHING.get_color()    # → "green"
AlignmentLevel.EXPLORING.get_color()      # → "yellow"
AlignmentLevel.MISALIGNED.get_color()     # → "red"
ActivityType.TASK.get_icon()              # → "📝"
CompletionStatus.DONE.get_emoji()         # → "✅"
TrendDirection.INCREASING.get_icon()      # → "📈"
```

**Enums with display methods:** Priority, EntityStatus, AlignmentLevel, ActivityType, CompletionStatus, EducationalLevel, ContentType, ContextHealthScore, TrendDirection, HealthStatus, SeverityLevel, SELCategory

### 4. Status Validation

EntityType and EntityStatus form a validation system:

```python
# What statuses can a Task have?
EntityType.TASK.valid_statuses()
# → {DRAFT, SCHEDULED, ACTIVE, PAUSED, BLOCKED, COMPLETED, CANCELLED, POSTPONED, FAILED}

# Can an active task become blocked?
EntityStatus.ACTIVE.can_transition_to(EntityStatus.BLOCKED, entity_type=EntityType.TASK)  # → True

# Can a principle be "blocked"?
EntityStatus.ACTIVE.can_transition_to(EntityStatus.BLOCKED, entity_type=EntityType.PRINCIPLE)  # → False
```

### 5. Role Hierarchy

UserRole uses numeric levels for permission checking:

```python
UserRole.MEMBER.has_permission(UserRole.REGISTERED)  # → True (1 >= 0)
UserRole.MEMBER.has_permission(UserRole.ADMIN)        # → False (1 < 3)
UserRole.TEACHER.can_create_curriculum()              # → True
```

### 6. Cross-Enum Conversion

Some enums bridge between systems:

```python
# Knowledge status → Entity status
KnowledgeStatus.PUBLISHED.to_activity_status()  # → EntityStatus.COMPLETED

# Priority → numeric for sorting
Priority.HIGH.to_numeric()                        # → 3

# Recurrence → RRULE
RecurrencePattern.WEEKLY.to_rrule_base()          # → "FREQ=WEEKLY"
```

---

## Dual-Track Assessment

Six self-rating level enums (ADR-030) compare user self-perception with system measurement. Each has exactly 5 levels with `to_score()` / `from_score()`:

| Enum | Domain | Measures | System Counterpart |
|------|--------|----------|-------------------|
| ProductivityLevel | Tasks | "How productive do I feel?" | Completion rate |
| ProgressLevel | Goals | "How is my progress?" | Milestone completion % |
| ConsistencyLevel | Habits | "How consistent am I?" | Streak data |
| EngagementLevel | Events | "How engaged was I?" | Attendance records |
| DecisionQualityLevel | Choices | "How good are my decisions?" | Outcome tracking |
| MasteryLevel | Knowledge (Ku) | "How well have I mastered this?" | Substance score (`calculate_user_substance`) |

(Principles use `AlignmentLevel`, which lives with the other principle enums.) `MasteryLevel`
(mastered/proficient/familiar/aware/novice) is **distinct from `MasteryImpact`** — the latter is a
contribution-weighting enum, not a self-rating.

**`DualTrackDimension`** (`productivity`/`engagement`/`decision_quality`) is the storage/aggregation
**key** for the three *user-level* dimensions (Tasks/Events/Choices), which assess the user across all
their entities of a kind and persist on the `:User` node (`User.dual_track_checkins`, keyed by this
enum's value). The per-entity dimensions key by entity UID; the Knowledge dimension keys by Ku UID
(`User.knowledge_checkins`).

Used with `DualTrackResult[L]` (generic dataclass in `core/models/shared/dual_track.py`) which captures both user_level and system_level, computes perception_gap, and generates insights.

---

---

## Customization Dials

Priority and Confidence are SKUEL's two first-class customization dials — the most fundamental
way users and admins express dimensional weight across the graph.

| Dial | Enum | Who Sets It | Where |
|------|------|------------|-------|
| Priority | Priority | User | All UserOwnedEntity nodes (Activity, Submissions, LifePath) |
| Confidence | Confidence | Admin/User | Curriculum nodes (KU, PS, LP); all lateral relationship edges |

They are orthogonal: Priority says "how important", Confidence says "how certain".
Both flow into the intelligence layer (planning) and graph visualization (vis.js):

- **Priority → Planning:** CRITICAL items override the top of `DailyWorkPlan` in `daily_planning.py` (cap: 3)
- **Confidence → Vis.js:** Edge line style (solid/dashed/dotted) and opacity in `renderNetwork()`

```python
# Priority
Priority.HIGH.to_numeric()                   # → 3
Priority.HIGH.get_color()                    # → "#F59E0B" (amber)
Priority.from_search_text("urgent")          # → [Priority.HIGH, Priority.CRITICAL]

# Confidence
Confidence.HIGH.to_numeric()                 # → 0.9
Confidence.CERTAIN.get_color()               # → "#6D28D9" (purple)
Confidence.from_numeric(0.6)                 # → Confidence.MEDIUM
Confidence.from_search_text("unsure")        # → [Confidence.UNCERTAIN, Confidence.LOW]
```

**See:** `/docs/architecture/PRIORITY_CONFIDENCE_ARCHITECTURE.md`

---

## Enum-YAML Ontological Bridge

> **Core Insight:** "Enums define what is valid. YAML templates express content using that vocabulary."

Enums and YAML templates are two halves of the same system. Enums define SKUEL's vocabulary — the valid values for every constrained field. YAML templates are the authoring surface where content authors use that vocabulary to create entities. The type safety chain ensures no invalid value survives from authoring to storage.

### The Trace: YAML Field to Neo4j Property

```
YAML author writes: priority: medium
        ↓
    detector.py: type field → EntityType enum
        ↓
    preparer.py: normalize UIDs, inject entity_type property
        ↓
    Pydantic request model: validates "medium" → Priority.MEDIUM
        ↓
    Frozen dataclass: Priority.MEDIUM stored as typed field
        ↓
    Neo4j: property stored as "medium" (StrEnum string value)
```

### Enum-Governed YAML Fields

These YAML fields are constrained by Python enums. Using an invalid value fails Pydantic validation during ingestion.

| YAML Field | Enum Class | Applies To | Example Values |
|------------|------------|-----------|----------------|
| `type` | `EntityType` | All entities | `Task`, `Habit`, `Ku`, `PathStep` |
| `priority` | `Priority` | All activities | `low`, `medium`, `high`, `critical` |
| `status` | `EntityStatus` | All entities | `draft`, `active`, `completed` |
| `polarity` | `HabitPolarity` | Habit | `build`, `break`, `neutral` |
| `category` (habit) | `HabitCategory` | Habit | `health`, `fitness`, `learning` |
| `difficulty` | `HabitDifficulty` | Habit | `trivial`, `easy`, `moderate`, `challenging`, `hard` |
| `goal_type` | `GoalType` | Goal | `outcome`, `process`, `learning`, `mastery` |
| `timeframe` | `GoalTimeframe` | Goal | `daily`, `weekly`, `quarterly`, `yearly` |
| `measurement_type` | `MeasurementType` | Goal | `binary`, `percentage`, `numeric` |
| `choice_type` | `ChoiceType` | Choice | `binary`, `multiple`, `ranking`, `strategic` |
| `category` (principle) | `PrincipleCategory` | Principle | `spiritual`, `ethical`, `personal` |
| `source` (principle) | `PrincipleSource` | Principle | `philosophical`, `religious`, `personal` |
| `strength` | `PrincipleStrength` | Principle | `core`, `strong`, `moderate`, `developing` |
| `recurrence_pattern` | `RecurrencePattern` | Habit, Event | `daily`, `weekly`, `monthly` |
| `sel_category` | `SELCategory` | Ku, PathStep | `self_awareness`, `self_management` |
| `complexity` | `KuComplexity` | PathStep | `basic`, `medium`, `advanced` |

### Annotated Example

From the `mindfulness_101` bundle — enum-governed fields marked with `# ← enum`:

```yaml
type: Habit                    # ← EntityType.HABIT
uid: habit:daily-2min-breath
title: Daily 2-Minute Breath
priority: medium               # ← Priority.MEDIUM
polarity: build                # ← HabitPolarity.BUILD
category: mindfulness          # ← HabitCategory.MINDFULNESS
difficulty: easy               # ← HabitDifficulty.EASY
recurrence_pattern: daily      # ← RecurrencePattern.DAILY
connections:
  reinforces_knowledge:
    - l:mindfulness:breath-awareness-basics
```

Every value after the colon is validated against the corresponding enum. A typo like `polarity: built` produces a clear Pydantic validation error at ingestion time — not a silent bad value in Neo4j.

**See:** [YAML Authoring Guide](/docs/guides/YAML_AUTHORING_GUIDE.md) (authoring reference), [Schema Templates](/yaml_templates/_schemas/) (complete field reference per entity type)

---

## See Also

- [Constants Usage Guide](/docs/patterns/constants_usage_guide.md) — Named constants vs enums
- [Domain Patterns Catalog](/docs/patterns/DOMAIN_PATTERNS_CATALOG.md) — How enums integrate with the three-tier type system
- [YAML Authoring Guide](/docs/guides/YAML_AUTHORING_GUIDE.md) — Content authoring with enum-governed fields
- Source: `core/models/enums/` (17 files, ~3,400 lines)
