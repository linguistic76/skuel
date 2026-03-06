# Enum Architecture
*Last updated: 2026-03-03*

> **Core Principle:** "Enums define behavior, services consume it"

SKUEL has **87 enum classes** across **17 files** in `core/models/enums/`. Enums are not just value holders — they carry display logic, scoring, search, validation, and transition rules. This document maps the enum landscape, explains the two most important enums (EntityType and EntityStatus), catalogs per-domain enums, and documents the recurring dynamic patterns.

---

## File Map

Every enum lives in exactly one file. The `__init__.py` re-exports all public enums so downstream code imports from `core.models.enums`.

| File | Purpose | Key Enums |
|------|---------|-----------|
| `entity_enums.py` | Core identity, lifecycle, domain classification | EntityType, EntityStatus, ContentOrigin, ProcessorType, Domain, NonKuDomain, ContentScope |
| `activity_enums.py` | Priority, Confidence, calendar types, dual-track assessment | Priority, Confidence, ActivityType, 5 assessment levels |
| `goal_enums.py` | Goal classification | GoalType, GoalTimeframe, MeasurementType, HabitEssentiality |
| `habit_enums.py` | Habit classification and completion | HabitPolarity, HabitCategory, HabitDifficulty, CompletionStatus |
| `choice_enums.py` | Decision types | ChoiceType |
| `principle_enums.py` | Principle classification and alignment | PrincipleCategory, PrincipleSource, PrincipleStrength, AlignmentLevel |
| `submissions_enums.py` | Submissions + Feedback processing and scheduling | ExerciseScope, FormattingStyle, AnalysisDepth, ScheduleType, ProgressDepth |
| `curriculum_enums.py` | Learning path and step types | LpType, StepDifficulty |
| `lifepath_enums.py` | Vision theme classification | ThemeCategory |
| `scheduling_enums.py` | Time, recurrence, energy | RecurrencePattern, TimeOfDay, EnergyLevel |
| `learning_enums.py` | Education, knowledge, mastery | LearningLevel, EducationalLevel, MasteryStatus, ContentType, SELCategory |
| `metadata_enums.py` | Relationships, search, system config | RelationshipType (48 values), Intent, Visibility, SystemConstants |
| `user_enums.py` | User roles and health scoring | UserRole, ContextHealthScore |
| `finance_enums.py` | Finance domain | ExpenseStatus, PaymentMethod, BudgetPeriod |
| `transcription_enums.py` | Transcription processing | TranscriptionStatus |
| `neo_labels.py` | Neo4j node labels | NeoLabel (32 labels) |

**Import convention:**
```python
from core.models.enums import EntityType, EntityStatus, Priority
```

---

## The Two Core Enums

### EntityType — What Is It? (16 values)

EntityType is the type discriminator for every entity in SKUEL. It lives on the `entity_type` field of every Entity and determines valid statuses, default status, content origin, ownership rules, and Neo4j labels.

**Five groups:**

| Group | EntityTypes | Ownership | Neo4j Labels |
|-------|-------------|-----------|--------------|
| **Knowledge** (atomic curriculum) | KU, RESOURCE | Admin-created, no user_uid | :Entity:Ku, :Entity:Resource |
| **Curriculum Structure** | LEARNING_STEP, LEARNING_PATH, EXERCISE | Admin-created, no user_uid | :Entity:LearningStep, :Entity:LearningPath, :Entity:Exercise |
| **Content Processing** | JOURNAL, SUBMISSION, SUBMISSION_FEEDBACK | User-owned | :Entity:Journal, :Entity:Submission, :Entity:SubmissionFeedback |
| **Activity Feedback** | ACTIVITY_REPORT | User-owned (no file fields) | :Entity:ActivityReport |
| **Activity** (user-owned) | TASK, GOAL, HABIT, EVENT, CHOICE, PRINCIPLE | User-owned | :Entity:Task, :Entity:Goal, etc. |
| **Destination** | LIFE_PATH | User-owned | :Entity:LifePath |

**Content Origin tiers** (derived from EntityType via `.content_origin()`):

| Tier | ContentOrigin | EntityTypes |
|------|---------------|-------------|
| A | CURATED | Resource |
| B | CURRICULUM | KU, LearningStep, LearningPath, Exercise |
| C | USER_CREATED | All 6 Activity types + Submission, Journal, LifePath |
| D | FEEDBACK | ActivityReport, SubmissionFeedback |

**Key methods:**

| Method | Returns | Purpose |
|--------|---------|---------|
| `is_activity()` | bool | Is it one of the 6 user activity domains? |
| `is_knowledge()` | bool | Is it shared curriculum (KU, Resource)? |
| `is_content_processing()` | bool | Is it in the processing chain (Journal, Submission, etc.)? |
| `is_user_owned()` | bool | Does it require a user_uid? |
| `valid_statuses()` | frozenset[EntityStatus] | Which statuses are valid for this type? |
| `default_status()` | EntityStatus | What status does a new entity get? |
| `content_origin()` | ContentOrigin | Which content tier (A-D)? |
| `from_string(text)` | EntityType \| None | Parse with alias support ("ku" -> KU, "moc" -> KU) |

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
                                                 |
                                          REVISION_REQUESTED → resubmit

Activity:
  DRAFT → SCHEDULED → ACTIVE → PAUSED → COMPLETED
              |           |       |
              |           +→ BLOCKED → ACTIVE
              |           |
              +→ POSTPONED    +→ CANCELLED / FAILED
```

**Valid statuses per EntityType (summary):**

| EntityType | Valid Statuses | Default |
|------------|---------------|---------|
| Ku, Resource, SubmissionFeedback | DRAFT, COMPLETED, ARCHIVED | COMPLETED |
| LearningStep, LearningPath, Exercise, Choice | DRAFT, ACTIVE, COMPLETED, ARCHIVED | DRAFT |
| Journal, Submission | DRAFT, SUBMITTED, QUEUED, PROCESSING, COMPLETED, FAILED, REVISION_REQUESTED, ARCHIVED | DRAFT |
| ActivityReport | COMPLETED (always — created already complete) | COMPLETED |
| Task | DRAFT, SCHEDULED, ACTIVE, PAUSED, BLOCKED, COMPLETED, CANCELLED, POSTPONED, FAILED | DRAFT |
| Goal | DRAFT, ACTIVE, PAUSED, COMPLETED, CANCELLED, FAILED, ARCHIVED | DRAFT |
| Habit | ACTIVE, PAUSED, COMPLETED, CANCELLED, ARCHIVED | ACTIVE |
| Event | SCHEDULED, ACTIVE, COMPLETED, CANCELLED | SCHEDULED |
| Principle | ACTIVE, PAUSED, ARCHIVED | ACTIVE |
| LifePath | ACTIVE, ARCHIVED | ACTIVE |

**Key methods:**

| Method | Returns | Purpose |
|--------|---------|---------|
| `is_terminal()` | bool | COMPLETED, FAILED, CANCELLED, or ARCHIVED? |
| `is_active()` | bool | SUBMITTED, QUEUED, PROCESSING, ACTIVE, or SCHEDULED? |
| `is_pending()` | bool | DRAFT, SUBMITTED, QUEUED, or SCHEDULED? |
| `can_transition_to(target, entity_type)` | bool | Is this transition valid (optionally type-aware)? |
| `get_color()` | str | Hex color for UI (e.g., ACTIVE="#06B6D4" cyan, BLOCKED="#DC2626" red) |
| `from_search_text(text)` | list[EntityStatus] | Find statuses matching search terms |

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

**For the full picture** — class hierarchy, per-model enum fields, three-tier flow, directory layout, sub-entities, and intelligence models — see [Model Architecture](MODEL_ARCHITECTURE.md).

**Quick reference — enum fields by model tier:**

| Base Class | Enum Fields | Models |
|------------|-------------|--------|
| Entity | entity_type, status, visibility | *(all 16 models)* |
| UserOwnedEntity | *(inherits above)* | Task, Goal, Habit, Event, Choice, Principle, Submission types, LifePath |
| Curriculum *(base class)* | + complexity, learning_level, sel_category | Ku, LearningStep, LearningPath, Exercise |

Domain-specific enum fields: Goal (+3), Habit (+3), Principle (+4), Choice (+1), Submission (+1), LifePath (+1), LearningStep (+1), LearningPath (+1), Exercise (+1).

---

## Domain Enum Map

### Cross-Domain (used by multiple domains)

| Enum | File | Values | Used By |
|------|------|--------|---------|
| Priority | activity_enums.py | LOW, MEDIUM, HIGH, CRITICAL | All UserOwnedEntity nodes (Tasks, Goals, Habits, Events, Choices, Principles, Submissions, LifePath) |
| Confidence | activity_enums.py | UNCERTAIN, LOW, MEDIUM, HIGH, CERTAIN | Curriculum entities (KU, LS, LP); lateral relationship edges (all 9 domains) |
| ActivityType | activity_enums.py | TASK, HABIT, EVENT, LEARNING, MILESTONE, ... (12) | Calendar, scheduling |
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

AlignmentLevel has `to_score()` / `from_score()` methods for the dual-track assessment pattern.

**Submissions + Feedback** (`submissions_enums.py`):

| Enum | Values | Purpose |
|------|--------|---------|
| ExerciseScope | PERSONAL, ASSIGNED | Exercise scope (user's own vs teacher-assigned) |
| FormattingStyle | STRUCTURED, NARRATIVE, BULLET_POINTS, CONVERSATIONAL, EXECUTIVE_SUMMARY | Transcript formatting |
| AnalysisDepth | BASIC, DETAILED, COMPREHENSIVE | LLM processing depth |
| ContextEnrichmentLevel | NONE, BASIC, STANDARD, DEEP | SKUEL context integration |
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

**Learning** (`learning_enums.py`) — 9 enums for education/knowledge tracking:
- `LearningLevel` (BEGINNER → EXPERT, with `can_handle()` method)
- `EducationalLevel` (ELEMENTARY → LIFELONG, with `get_age_range()`)
- `MasteryStatus` (NOT_STARTED → MASTERED)
- `KnowledgeStatus` (DRAFT → UNDER_REVIEW, with `to_activity_status()`)
- `ContentType` (CONCEPT, PRACTICE, THEORY, ... 12 values for faceted search)
- `KnowledgeType` (DECLARATIVE, PROCEDURAL, CONCEPTUAL, METACOGNITIVE)
- `SELCategory` (5 SEL framework categories)
- `KuComplexity`, `PracticeLevel`

**User** (`user_enums.py`):
- `UserRole` — 4-tier hierarchy: REGISTERED < MEMBER < TEACHER < ADMIN. Has `has_permission()` for hierarchy-aware checks.
- `ContextHealthScore` — POOR (0.25), FAIR (0.50), GOOD (0.75), EXCELLENT (1.0). UI display methods.

**Metadata** (`metadata_enums.py`) — System-wide configuration:
- `RelationshipType` (48 values — all entity relationship types)
- `Intent` (19 values — user intent classification)
- `Visibility` (PRIVATE, SHARED, TEAM, PUBLIC)
- `SystemConstants` (class with thresholds: MASTERY_THRESHOLD=0.8, etc.)
- Plus: ResponseTone, Personality, GuidanceMode, LearningModality, SearchScope, FacetType, MessageRole, ConversationState, CacheStrategy, TrendDirection, HealthStatus, SeverityLevel, BridgeType, ErrorSeverity, ExtractionMethod

**Finance** (`finance_enums.py`):
- ExpenseStatus (7), PaymentMethod (8+), ExpenseCategory (3), RecurrencePattern (7), BudgetPeriod (4)

**Transcription** (`transcription_enums.py`):
- `TranscriptionStatus` — PENDING, PROCESSING, COMPLETED, FAILED. Has `is_terminal()` and `can_retry()`.

**Neo4j Labels** (`neo_labels.py`):
- `NeoLabel` — 32 labels mapping to Neo4j node types. `from_entity_type()` bridges EntityType → Neo4j label. `is_valid()` validates label strings.

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

ProductivityLevel.PRODUCTIVE.to_score()   # → 0.8
ConsistencyLevel.from_score(0.35)         # → ConsistencyLevel.INCONSISTENT
```

**Enums with scoring:** AlignmentLevel, ProductivityLevel, ProgressLevel, ConsistencyLevel, EngagementLevel, DecisionQualityLevel, ContextHealthScore

### 3. UI Display

Enums that provide colors and icons for rendering:

```python
Priority.HIGH.get_color()                 # → "#F59E0B" (amber)
EntityStatus.ACTIVE.get_color()           # → "#06B6D4" (cyan)
ActivityType.TASK.get_icon()              # → "📝"
CompletionStatus.DONE.get_emoji()         # → "✅"
TrendDirection.INCREASING.get_icon()      # → "📈"
```

**Enums with display methods:** Priority, EntityStatus, ActivityType, CompletionStatus, EducationalLevel, ContentType, ContextHealthScore, TrendDirection, HealthStatus, SeverityLevel, SELCategory

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

# Practice level → Learning level
PracticeLevel.ADVANCED.to_learning_level()       # → LearningLevel.ADVANCED

# Priority → numeric for sorting
Priority.HIGH.to_numeric()                        # → 3

# Recurrence → RRULE
RecurrencePattern.WEEKLY.to_rrule_base()          # → "FREQ=WEEKLY"
```

---

## Dual-Track Assessment

Five assessment enums (ADR-030) compare user self-perception with system measurement. Each has exactly 5 levels with `to_score()` / `from_score()`:

| Enum | Domain | Measures | System Counterpart |
|------|--------|----------|-------------------|
| ProductivityLevel | Tasks | "How productive do I feel?" | Completion rate |
| ProgressLevel | Goals | "How is my progress?" | Milestone completion % |
| ConsistencyLevel | Habits | "How consistent am I?" | Streak data |
| EngagementLevel | Events | "How engaged was I?" | Attendance records |
| DecisionQualityLevel | Choices | "How good are my decisions?" | Outcome tracking |

Used with `DualTrackResult[L]` (generic dataclass in `core/models/shared/dual_track.py`) which captures both user_level and system_level, computes perception_gap, and generates insights.

---

---

## Customization Dials

Priority and Confidence are SKUEL's two first-class customization dials — the most fundamental
way users and admins express dimensional weight across the graph.

| Dial | Enum | Who Sets It | Where |
|------|------|------------|-------|
| Priority | Priority | User | All UserOwnedEntity nodes (Activity, Submissions, LifePath) |
| Confidence | Confidence | Admin/User | Curriculum nodes (KU, LS, LP); all lateral relationship edges |

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

## See Also

- [Constants Usage Guide](/docs/patterns/constants_usage_guide.md) — Named constants vs enums
- [Domain Patterns Catalog](/docs/patterns/DOMAIN_PATTERNS_CATALOG.md) — How enums integrate with the three-tier type system
- Source: `core/models/enums/` (17 files, ~3,400 lines)
