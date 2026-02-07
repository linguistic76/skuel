---
title: SKUEL 14-Domain Architecture
updated: 2026-02-06
status: current
category: architecture
tags:
- architecture
- domain
- fourteen
related:
- ADR-019-transcription-service-standalone
- ADR-023-curriculum-baseservice-migration
- ADR-024-baseintellligence-service-migration
- ADR-025-service-consolidation-patterns
- ADR-040-teacher-assignment-workflow
related_skills:
- activity-domains
---

# SKUEL 14-Domain Architecture

**Last Updated**: February 6, 2026
**Version**: 3.0.0 (ADR-040: Groups + Teacher Assignment Workflow)
## Related Skills

For implementation guidance, see:
- [@activity-domains](../../.claude/skills/activity-domains/SKILL.md)


## Executive Summary

SKUEL is built on a **15-domain + 5 cross-cutting systems architecture** that represents the complete spectrum of human activity and learning. This document defines the foundational mental model:

- **Activity Domains (6)** - What I DO
- **Finance Domain (1)** - What I MANAGE (standalone)
- **Curriculum Domains (3)** - What I LEARN (three grouping patterns: KU, LS, LP)
- **Content/Processing Domains (2)** - How I PROCESS (Journals, Reports)
- **Organizational Domains (2)** - How I ORGANIZE (Groups for classes, MOC for knowledge)
- **LifePath (1)** - Where I'm GOING (The Destination)
- **Cross-Cutting Systems (5)** - The infrastructure that enables everything (4 active + 1 planned)

**Core Philosophy**: "Everything flows toward the life path."

---

## The 14-Domain Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         THE DESTINATION (Domain #14)                         │
│                                                                              │
│                              ┌─────────────┐                                │
│                              │  LIFEPATH   │                                │
│                              │   Where I'm │                                │
│                              │    GOING    │                                │
│                              └──────┬──────┘                                │
│                                     │                                        │
│                    Everything flows toward the life path                     │
└─────────────────────────────────────┼───────────────────────────────────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
        ▼                             ▼                             ▼
┌───────────────┐           ┌─────────────────┐           ┌───────────────┐
│CONTENT/PROC   │           │ACTIVITY DOMAINS │           │  CURRICULUM   │
│ DOMAINS (2)   │           │ (6) + FINANCE   │           │   DOMAINS     │
│               │           │                 │           │      (3)      │
│ How I         │           │ What I DO       │           │ What I LEARN  │
│ PROCESS       │           │                 │           │               │
│               │           │ • Tasks         │           │ • KU (point)  │
│ • Reports     │◄─────────►│ • Habits        │◄─────────►│ • LS (edge)   │
│ • Journals    │           │ • Goals         │           │ • LP (path)   │
│               │           │ • Events        │           │               │
│───────────────│           │ • Principles    │           │───────────────│
│ORGANIZATIONAL │           │ • Choices       │           │Two Access     │
│ DOMAINS (2)   │           │ ─────────────── │           │Paths to KU:   │
│ • Groups      │           │ • Finance (1)   │           │ • LS (linear) │
│ • MOC (KU-    │           │                 │           │ • MOC (graph) │
│   based org)  │           │                 │           │               │
└───────────────┘           └─────────────────┘           └───────────────┘
        │                             │                             │
        └─────────────────────────────┼─────────────────────────────┘
                                      │
                                      ▼
        ┌─────────────────────────────────────────────────────────────┐
        │               CROSS-CUTTING SYSTEMS (5)                      │
        │                                                              │
        │  UserContext • Search • Calendar • Askesis • Messaging      │
        │                                                              │
        │  + Analytics (meta-service aggregation, not a domain)       │
        │                                                              │
        │   The infrastructure that enables cross-domain intelligence  │
        └─────────────────────────────────────────────────────────────┘
```

---

## Domain Categories

### 1. Activity Domains (6) - What I DO

Activity domains are **independent entities** that users create, track, and complete. They represent the concrete actions of living.

| Domain | Purpose | Key Characteristics |
|--------|---------|---------------------|
| **Tasks** | Work items to complete | One-time, deadline-driven, outcome-focused |
| **Habits** | Behaviors to build | Recurring, streak-tracked, lifestyle-integrated |
| **Goals** | Outcomes to achieve | Milestones, progress-measured, aspiration-driven |
| **Events** | Time commitments | Scheduled, calendar-based, attendance-tracked |
| **Principles** | Values to embody | Guiding philosophies, decision-criteria, life-anchors |
| **Choices** | Decisions to make | Options, criteria, outcome-tracked |

### 2. Finance Domain (1) - What I MANAGE

Finance is its **OWN domain group**, NOT an Activity Domain:

| Domain | Purpose | Key Characteristics |
|--------|---------|---------------------|
| **Finance** | Resources to manage | Income, expenses, budget-aligned, **admin-only** |

**Why Standalone**: Finance has unique concepts (budgets, expense categories, recurring expenses) that don't fit Activity Domain patterns. It uses a standalone facade with 4 sub-services (Core, Budget, Reporting, Invoice), not BaseService.

**Security Model**: All Finance routes require ADMIN role. Admin users see ALL finance data (no ownership checks). This simplifies development while maintaining security.

**Event-Driven**: FinanceCoreService publishes domain events (ExpenseCreated, ExpenseUpdated, ExpensePaid, ExpenseDeleted) on all state changes.

**No Cross-Domain Intelligence**: Finance is pure bookkeeping - no intelligence service, no relationship configuration, no cross-domain connections. January 2026 simplification removed FinanceIntelligenceService and FinanceSearchService.

**Common Characteristics (Activity + Finance)**:
- Standalone lifecycle (created → active → completed/archived)
- Direct user manipulation (CRUD operations)

**Graph Relationships**:
```
Task ─[APPLIES_KNOWLEDGE]→ KnowledgeUnit
Task ─[FULFILLS]→ Goal
Habit ─[REINFORCES]→ Principle
Goal ─[INSPIRED_BY]→ Choice
Choice ─[INFORMED_BY]→ KnowledgeUnit
Principle ─[GROUNDED_IN]→ KnowledgeUnit
```

---

## BaseService Mixin Architecture (ADR-031)

**Philosophy:** Decompose monolithic BaseService into composable mixins.

### The 7 Mixins

**Location:** `/core/services/mixins/` (8 files including `__init__.py`)

Services compose only the mixins they need instead of inheriting a bloated base class:

| Mixin | Purpose | Key Methods |
|-------|---------|-------------|
| **ConversionHelpersMixin** | DTO ↔ Model conversion | `to_dto()`, `to_model()`, `to_dict()` |
| **CrudOperationsMixin** | Basic CRUD operations | `create()`, `get()`, `update()`, `delete()`, `list()` |
| **SearchOperationsMixin** | Search & filtering | `search()`, `get_by_status()`, `get_by_category()` |
| **RelationshipOperationsMixin** | Relationship queries | `get_prerequisites()`, `get_enables()` |
| **TimeQueryMixin** | Time-based queries | `get_created_between()`, `get_due_soon()` |
| **UserProgressMixin** | Progress tracking | `get_user_progress()`, `update_progress()` |
| **ContextOperationsMixin** | Graph context | `get_with_context()` via orchestrator |

**Mixin Files:**
```
/core/services/mixins/
├── __init__.py                        # Re-exports all mixins
├── conversion_helpers_mixin.py        # DTO/Model conversions
├── crud_operations_mixin.py           # CRUD
├── search_operations_mixin.py         # Search
├── relationship_operations_mixin.py   # Prerequisites/Enables
├── time_query_mixin.py                # Time filters
├── user_progress_mixin.py             # Progress tracking
└── context_operations_mixin.py        # Graph context
```

**Plus:** `FacadeDelegationMixin` (in `facade_delegation_mixin.py`) for dynamic method delegation to sub-services.

### Activity Domain Service Architecture

Activity domains use a **standardized facade pattern** with common sub-services created via factory:

```python
# File: /core/utils/activity_domain_config.py

@dataclass(frozen=True)
class ActivityDomainConfig:
    """Configuration for an Activity Domain's common sub-services."""
    core_module: str              # e.g., "core.services.tasks"
    core_class: str               # e.g., "TasksCoreService"
    search_module: str
    search_class: str
    intelligence_module: str
    intelligence_class: str
    relationship_config: Any      # UnifiedRelationshipService config
    domain_name: str              # e.g., "tasks"
    entity_label: str             # e.g., "Task"

# Registry of all 6 Activity Domain configurations
ACTIVITY_DOMAIN_CONFIGS: dict[str, ActivityDomainConfig] = {
    "tasks": ActivityDomainConfig(...),
    "goals": ActivityDomainConfig(...),
    "habits": ActivityDomainConfig(...),
    "events": ActivityDomainConfig(...),
    "choices": ActivityDomainConfig(...),
    "principles": ActivityDomainConfig(...),
}
```

### Common Sub-Services Factory

**Function:** `create_common_sub_services(domain, backend, graph_intel, event_bus)`

```python
# Usage in facade __init__:
from core.utils.activity_domain_config import create_common_sub_services

common = create_common_sub_services(
    domain="tasks",                      # Domain name from config
    backend=backend,                     # TasksOperations implementation
    graph_intel=graph_intelligence_service,  # Optional graph intelligence
    event_bus=event_bus,                 # Optional event bus
)

# Assign to facade attributes
self.core = common.core                  # TasksCoreService
self.search = common.search              # TasksSearchService
self.relationships = common.relationships # UnifiedRelationshipService
self.intelligence = common.intelligence  # TasksIntelligenceService
```

**Benefits:**
- **Consistency:** All 6 Activity Domains use identical sub-service structure
- **Reduced boilerplate:** ~480 lines eliminated from facade `__init__` methods
- **Centralized config:** Change behavior once, affects all domains
- **Type-safe:** Static specs with domain-prefixed factories

**Domain Facade Pattern:**
```
TasksService (Facade)
├── .core         → TasksCoreService (CRUD + domain logic)
├── .search       → TasksSearchService (Discovery)
├── .relationships → UnifiedRelationshipService (TASKS_UNIFIED)
└── .intelligence  → TasksIntelligenceService (Analytics, NO AI)
```

All sub-services created via `create_common_sub_services()` factory, eliminating repetitive initialization code.

---

### 3. Curriculum Domains (3) - What I LEARN

Curriculum domains form SKUEL's **educational foundation** through **three grouping patterns** - different perspectives on the same knowledge base:

```
                LP     LP     LP    (Learning Paths - linear sequences)
               /|\    /|\    /|\
              / | \  / | \  / | \
            LS LS LS LS LS LS LS LS  (Learning Steps - sequential steps)
            |  |  |  |  |  |  |  |
           KU KU KU KU KU KU KU KU   (Knowledge Units - atomic content)

    Two Paths to Knowledge (Montessori-Inspired):
    - LS Path: Structured, linear, teacher-directed curriculum
    - MOC Path: Unstructured, graph, learner-directed exploration

    MOC is NOT a separate entity - it IS a KU with ORGANIZES relationships.
    Same KU, two access paths. Progress tracked on the KU itself.
    See section 5 for MOC (Organizational Domain).
```

| Pattern | UID Prefix | Topology | Purpose |
|---------|-----------|----------|---------|
| **KU** | `ku:` | Point | Atomic unit of knowledge content |
| **LS** | `ls:` | Edge | Single step in a learning journey |
| **LP** | `lp:` | Path | Complete learning sequence |

**The Three Curriculum Patterns Explained:**
- **KU (Knowledge Unit)** - The atomic brick. Self-contained knowledge content.
- **LS (Learning Step)** - The staircase step. Aggregates KUs into sequential activities.
- **LP (Learning Path)** - The full staircase. Sequences LSs into complete journeys.

**Key Insight:** The same KU can appear in multiple LS, LP, and MOC contexts. The patterns provide **different views** into the same knowledge base.

**Why Abbreviated Prefixes**:
- Visual distinction: `ku`, `ls`, `lp` immediately signal "grouping pattern"
- Unified system: Abbreviated prefixes indicate these form a cohesive architecture
- Clean code: Shorter prefixes improve YAML/Cypher readability
- Foundation focus: These ARE SKUEL's curriculum foundation
- **Note (January 2026):** MOC uses `ku:` prefix since MOC IS a KU with ORGANIZES relationships

**See:** `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` for detailed documentation.

**The Knowledge Substance Philosophy**:

SKUEL measures knowledge by how it's **LIVED**, not just learned:

| Application Type | Weight | Max | Rationale |
|-----------------|--------|-----|-----------|
| **Habits** | 0.10 | 0.30 | Lifestyle integration (highest) |
| **Journals** | 0.07 | 0.20 | Metacognition |
| **Choices** | 0.07 | 0.15 | Decision-making wisdom |
| **Events** | 0.05 | 0.25 | Practice/embodiment |
| **Tasks** | 0.05 | 0.25 | Real-world application |

**Substance Scale**:
- 0.0-0.2: Pure theory (read about it)
- 0.3-0.5: Applied knowledge (tried it)
- 0.6-0.7: Well-practiced (regular use)
- 0.8-1.0: Lifestyle-integrated (embodied)

---

### 4. Content/Processing Domains (2) - How I PROCESS

Content/Processing domains handle **input processing and AI transformation** across the system.

| Domain | Type | Purpose | Data Flow |
|--------|------|---------|-----------|
| **Reports** | Processing | User-facing report interface | Input → Processing → Activities |
| **Journals** | Processing | Two-tier journal system | Voice/Text → AI → Formatted Output |

**Journals Two-Tier System (December 2025):**

| Tier | Name | Input | Retention | ReportType |
|------|------|-------|-----------|------------|
| **PJ1** | Voice Journals | Audio files | Ephemeral (max 3, FIFO) | `JOURNAL_VOICE` |
| **PJ2** | Curated Journals | Text/Markdown | Permanent | `JOURNAL_CURATED` |

- **PJ1 (Voice)**: Quick capture, auto-cleaned to prevent Neo4j clutter
- **PJ2 (Curated)**: Intentional, refined content worth preserving permanently

**Reports Architecture**:
```
User Upload → ReportSubmissionService
                    ↓
            ReportsProcessingService
                    ↓
            [Processor Selection]
            ├→ Audio → TranscriptionService (Deepgram) → TranscriptProcessorService
            ├→ Text → TranscriptProcessorService
            └→ Other → Future processors
                    ↓
            Activity Extraction (DSL Parser)
                    ↓
            Entity Creation (14 domains)
```

**Note:** TranscriptionService (ADR-019) is a simplified 8-method service that handles
audio → Deepgram → transcript. It publishes TranscriptionCompleted events for downstream
processing. See `/docs/decisions/ADR-019-transcription-service-standalone.md`.

**Key Distinction**:
- **Reports** = User-facing interface (file uploads, submissions)
- **Journals** = AI processing engine (returns `JournalAIInsights`, no entity creation)

---

### 5. Organizational Domains (2) - How I ORGANIZE

#### Groups (ADR-040)

**Groups** mediate ALL teacher-student relationships. A teacher creates a group, adds students, and assigns work to the group. No direct TEACHES relationship.

| Aspect | Description |
|--------|-------------|
| **Purpose** | Teacher-student class management |
| **Key Insight** | Groups are the ONE PATH for teacher-student relationships |
| **UID Format** | `group_{slug}_{random}` |
| **Access** | TEACHER role required for creation; members can view |

**Group Service Architecture:**
```
GroupService (standalone)
├── create_group()          - TEACHER creates group
├── add_member()            - Add student via MEMBER_OF
├── remove_member()         - Remove student
├── get_members()           - List group members
├── list_teacher_groups()   - Teacher's groups
└── get_user_groups()       - Student's groups
```

**Key Relationships:**
```cypher
(teacher:User)-[:OWNS]->(group:Group)
(student:User)-[:MEMBER_OF {joined_at, role}]->(group:Group)
(project:ReportProject)-[:FOR_GROUP]->(group:Group)        // Assignment targeting
(report:Report)-[:FULFILLS_PROJECT]->(project:ReportProject)  // Student submission
```

**Assignment Workflow (ReportProject evolution):**
ReportProject evolved with `scope`, `due_date`, `processor_type`, `group_uid` fields. When `scope=ASSIGNED`, the project targets a group via FOR_GROUP. Students submit reports that auto-share with the teacher via SHARES_WITH.

**See:** `/docs/decisions/ADR-040-teacher-assignment-workflow.md`

#### MOC (Map of Content)

**MOC** provides **non-linear knowledge organization** using KUs organized via ORGANIZES relationships.

**January 2026 - KU-Based Architecture:**
- **MOC is NOT a separate entity** - it IS a KU with ORGANIZES relationships
- A KU "is" a MOC when it has outgoing ORGANIZES relationships (emergent identity)
- Sections within MOCs are also KUs organized via ORGANIZES
- Same KU can be in multiple MOCs (many-to-many)
- Progress tracked on the KU itself, unified across LS and MOC paths

**Two Paths to Knowledge (Montessori-Inspired):**

| Path | Topology | Purpose | Pedagogy |
|------|----------|---------|----------|
| **LS** | Linear | Structured curriculum | Teacher-directed |
| **MOC** | Graph | Free exploration | Learner-directed |

```
LS Path (Structured):              MOC Path (Exploratory):
KU → KU → KU → KU                      KU (root MOC)
Sequential learning                   /    |    \
"Learn this, then this"            KU    KU    KU (topics)
                                  / \         / \
                                KU  KU     KU   KU
                                Non-linear, browse freely
                                "Explore what interests you"
```

**ORGANIZES Relationship:**
```cypher
// Create organization (KU organizing KU)
(parent:Ku)-[:ORGANIZES {order: int}]->(child:Ku)

// Check if KU is a MOC
MATCH (ku:Ku {uid: $ku_uid})
OPTIONAL MATCH (ku)-[:ORGANIZES]->(child:Ku)
RETURN count(child) > 0 AS is_moc

// Get organized children (ordered)
MATCH (parent:Ku {uid: $ku_uid})-[r:ORGANIZES]->(child:Ku)
RETURN child.uid, child.title, r.order
ORDER BY r.order ASC
```

**MOC Service Architecture:**
```
MOCService (thin facade)
└── MocNavigationService (all MOC operations)
    └── KuService (underlying KU CRUD)
```

**Key Files:**
- `/core/services/moc_service.py` - Facade
- `/core/services/moc/moc_navigation_service.py` - Navigation service
- `/docs/domains/moc.md` - Full documentation

**LS vs MOC - Complementary, Not Competing:**

| Aspect | Learning Step (LS) | Map of Content (MOC) |
|--------|-------------------|---------------------|
| **Structure** | Linear sequence | Non-linear graph |
| **Purpose** | "Learn X step-by-step" | "Browse everything about X" |
| **Navigation** | Next/Previous | Jump anywhere |
| **Progress** | Tracked on KU | Tracked on KU (same!) |
| **Use Case** | Structured learning | Reference & exploration |

---

### 6. LifePath (1) - The Destination

**LifePath** is Domain #14 - the ultimate destination toward which everything flows.

```
"Everything flows toward the life path."

"The user's vision is understood via the words user uses to communicate,
the UserContext is determined via user's actions."
```

| Aspect | Description |
|--------|-------------|
| **Purpose** | Answer: "Am I living my life path?" |
| **Key Insight** | LifePath bridges VISION (words) with ACTIONS (behavior) |
| **Not a stored entity** | It's a DESIGNATION on an LP via ULTIMATE_PATH relationship |
| **Measurement** | 5-dimension alignment score (0.0-1.0) |

**LifePath Service Structure** (`/core/services/lifepath/`):
```
LifePathService (Facade)
├── .vision     → LifePathVisionService    (capture, analyze, recommend)
├── .core       → LifePathCoreService      (designation CRUD)
├── .alignment  → LifePathAlignmentService (calculate alignment)
└── .intelligence → LifePathIntelligenceService (recommendations)
```

**5-Dimension Alignment**:
| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| Knowledge | 25% | Mastery of knowledge in life path LP |
| Activity | 25% | Tasks/habits supporting life path |
| Goal | 20% | Active goals contributing to life path |
| Principle | 15% | Values aligned with life path direction |
| Momentum | 15% | Recent activity trend toward life path |

**AlignmentLevel Enum**:
- `FLOURISHING` (0.9+) - Life purpose deeply integrated
- `ALIGNED` (0.7-0.9) - Consistent alignment with life path
- `EXPLORING` (0.4-0.7) - Making progress, some drift
- `DRIFTING` (<0.4) - Significant misalignment

**Key Relationships**:
```
(User)-[:ULTIMATE_PATH]->(Lp)         # User's designated life path
(Entity)-[:SERVES_LIFE_PATH]->(Lp)    # Entity contributes to life path
```

**See**: [LifePath Domain Documentation](/docs/domains/lifepath.md)

---

### 6. Cross-Cutting Systems (5) - The Infrastructure

Cross-cutting systems provide **foundation and infrastructure** without being domains themselves.

| System | Purpose | Status | Key Features |
|--------|---------|--------|--------------|
| **UserContext** | User state awareness | ✅ Active | ~240 fields, rich context, UID tracking |
| **Search** | Unified discovery | ✅ Active | Semantic search across all 14 domains |
| **Calendar** | Time aggregation | ✅ Active | Aggregates Tasks, Events, Habits, Goals |
| **Askesis** | AI orchestration | ✅ Active | LLM integration, intelligent assistance |
| **Messaging** | Communication | 📋 Planned | Notifications, alerts, reminders |

**Note:** 4 cross-cutting systems are fully implemented; Messaging is planned for future development.

**Analytics** is a meta-service (statistical aggregation), not a cross-cutting system. See `/docs/architecture/REPORTS_ARCHITECTURE.md`.

**UserContext - The Source of Truth**:
```python
@dataclass
class UserContext:
    # Activity awareness (6 domains)
    active_task_uids: list[str]
    active_habit_uids: list[str]
    active_goal_uids: list[str]
    active_event_uids: list[str]
    core_principle_uids: list[str]
    pending_choice_uids: list[str]

    # Finance awareness (1 domain)
    recent_expense_uids: list[str]

    # Curriculum awareness (3 curriculum domains; MOC is KU-based)
    knowledge_mastery: dict[str, float]  # ku_uid → mastery
    active_learning_step_uids: list[str]
    enrolled_learning_path_uids: list[str]

    # Cross-domain relationships
    tasks_by_goal: dict[str, list[str]]
    habits_by_principle: dict[str, list[str]]
    knowledge_by_task: dict[str, list[str]]

    # Life path alignment (Domain #14)
    life_path_alignment_score: float
    aligned_goal_count: int

    # ~200 more fields for complete user state
```

---

## Activity Domain Service Architecture

*Updated: January 2026 - Harmonized Architecture*

All 6 Activity Domains follow a **unified facade pattern** with embedded intelligence. This architecture was harmonized in January 2026 to ensure consistent patterns across all domains.

### Harmonized Creation Pattern

All 6 Activity Domains are created through a single unified helper in `services_bootstrap.py`:

```python
# services_bootstrap.py - Single point of creation
activity_services = _create_activity_services(
    tasks_backend=tasks_backend,
    events_backend=events_backend,
    habits_backend=habits_backend,
    goals_backend=goals_backend,
    choices_backend=choices_backend,
    principles_backend=principles_backend,
    graph_intelligence=graph_intelligence,
    event_bus=event_bus,
    # ... other dependencies
)

# All 6 services created uniformly:
# activity_services["tasks"]     → TasksService
# activity_services["events"]    → EventsService
# activity_services["habits"]    → HabitsService
# activity_services["goals"]     → GoalsService
# activity_services["choices"]   → ChoicesService
# activity_services["principles"] → PrinciplesService
```

### Sub-Service Structure

```
{Domain}Service (Facade)
├── {Domain}CoreService         - CRUD operations, status transitions
├── {Domain}SearchService       - Search and discovery
├── {Domain}ProgressService     - Progress tracking
├── {Domain}PlanningService     - Context-first planning (where applicable)
├── {Domain}SchedulingService   - Capacity and schedule management (where applicable)
├── UnifiedRelationshipService + {DOMAIN}_CONFIG - Graph relationships
├── {Domain}IntelligenceService - Analytics and insights (embedded)
└── {Domain}LearningService     - Learning path integration (where applicable)
```

**Scheduling Services** (capacity management and schedule optimization):
- `TasksSchedulingService` - Context-aware task scheduling with learning alignment
- `EventsSchedulingService` - Calendar conflict detection, time slot optimization
- `HabitsSchedulingService` - Capacity management, habit stacking, frequency optimization
- `GoalsSchedulingService` - Goal capacity, timeline suggestions, achievability assessment (January 2026)

### Embedded Intelligence Pattern

All Activity Domain facades embed their intelligence service, accessed via the `.intelligence` property:

```python
# Access intelligence through the facade
tasks_intelligence = services.tasks.intelligence
goals_intelligence = services.goals.intelligence
habits_intelligence = services.habits.intelligence
# ... same pattern for all 6 domains
```

### Services Dataclass Organization

The `Services` dataclass groups Activity Domains together with proper protocol types:

```python
@dataclass
class Services:
    # ================================================================
    # ACTIVITY DOMAINS (6) - All use facade pattern with embedded intelligence
    # Created by _create_activity_services(), access intelligence via .intelligence
    # ================================================================
    tasks: TasksOperations | None = None
    goals: GoalsOperations | None = None
    habits: HabitsOperations | None = None
    events: EventsOperations | None = None
    choices: ChoicesOperations | None = None
    principles: PrinciplesOperations | None = None

    # ================================================================
    # FINANCE (1) - NOT an Activity Domain (standalone facade)
    # ================================================================
    finance: FinancesOperations | None = None
    # ...
```

**Note:** As of January 2026, `goals_backend` is no longer exposed in Services. Use `services.goals.backend` pattern instead (consistent with all other domains).

### Orchestration Services (Separate from Activity Domains)

Cross-domain orchestration services coordinate between Activity Domains but are NOT part of them:

```python
orchestration = _create_orchestration_services(
    goals_backend=goals_backend,
    tasks_backend=tasks_backend,
    habits_backend=habits_backend,
    events_backend=events_backend,
)
# Returns: goal_task_generator, habit_event_scheduler
```

**Note:** As of December 2025, Activity Domains use `UnifiedRelationshipService` with domain configs.
Old `{Domain}RelationshipService` files archived to `zarchives/relationships/`.
See `/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md`.

### SearchService Pattern

**Core Principle**: "Search is fundamental to SKUEL. Search builds UserContext. Askesis is built on top of both UserContext and Search."

All activity domains implement the `DomainSearchOperations[T]` protocol for consistent search interfaces:

| Domain | SearchService | Key Methods |
|--------|--------------|-------------|
| Tasks | `TaskSearchService` | `get_tasks_for_goal()`, `get_curriculum_tasks()` |
| Goals | `GoalSearchService` | `get_goals_by_timeframe()`, `get_goals_needing_habits()` |
| Habits | `HabitSearchService` | `get_habits_by_frequency()`, `get_habits_needing_attention()` |
| Events | `EventSearchService` | `get_events_in_range()`, `get_conflicting_events()` |
| Choices | `ChoiceSearchService` | `get_pending_choices()`, `get_choices_by_urgency()` |
| Principles | `PrincipleSearchService` | `get_principles_guiding_goal()`, `get_active_principles()` |

### Universal Search Methods (All Domains)

```python
# Protocol: DomainSearchOperations[T]
async def search(query: str, limit: int = 50) -> Result[list[T]]
async def get_by_status(status: str, limit: int = 100) -> Result[list[T]]
async def get_by_domain(domain: Domain, limit: int = 100) -> Result[list[T]]
async def get_prioritized(user_context: UserContext, limit: int = 10) -> Result[list[T]]
async def get_by_relationship(related_uid: str, relationship_type: str) -> Result[list[T]]
async def get_due_soon(days_ahead: int = 7) -> Result[list[T]]
async def get_overdue(limit: int = 100) -> Result[list[T]]
```

**See**: `/docs/patterns/search_service_pattern.md` for complete documentation.

---

## Curriculum Domain Service Architecture

*Added: January 2026*

The 3 Curriculum Domains (KU, LS, LP) follow a **decomposed facade pattern** similar to Activity Domains, with complexity appropriately sized to each domain's needs. MOC is the Organizational Domain documented in section 5 - it's KU-based (not a separate entity).

### Complexity by Domain (Curriculum)

| Domain | Facade Lines | Sub-Services | Complexity | Rationale |
|--------|-------------|--------------|------------|-----------|
| **KU** | 1,120 | 7 | Very High | Semantic knowledge is inherently complex |
| **LP** | 408 | 8 | High | Learning paths need validation/adaptive |
| **LS** | 311 | 3 | **Minimal** | Steps are simple aggregations |

**MOC (Organizational Domain - January 2026 KU-based):**
| Domain | Facade Lines | Sub-Services | Complexity | Rationale |
|--------|-------------|--------------|------------|-----------|
| **MOC** | ~100 | 1 | Minimal | Thin facade over MocNavigationService; MOC is KU with ORGANIZES |

### Sub-Service Decomposition

**KU (Knowledge Units) - Most Sophisticated:**
```
KuService (facade)
├── KuCoreService         - CRUD operations
├── KuSearchService       - Search & discovery (facets, tags, semantic)
├── KuGraphService        - Graph navigation
├── KuSemanticService     - Semantic relationships
├── KuLpService           - Learning path integration
├── KuPracticeService     - Event-driven practice tracking
└── KuInteractionService  - Pedagogical tracking (VIEWED → IN_PROGRESS → MASTERED)
```

**LP (Learning Paths) - Well-Decomposed:**
```
LpService (facade)
├── LpCoreService         - CRUD & persistence
├── LpValidationService   - Prerequisites & blockers
├── LpContextService      - Graph traversal context
├── LpAnalysisService     - Knowledge scope & gaps
├── LpAdaptiveService     - Personalized sequences
├── LpProgressService     - Event-driven progress
├── LpRelationshipService - Graph-native queries
└── LpSearchService       - Search operations (BaseService)
```

**LS (Learning Steps) - Minimal Design:**
```
LsService (facade)
├── LsCoreService         - CRUD operations
├── LsRelationshipService - Step-path associations
└── LsSearchService       - Search operations (BaseService)
```

**MOC (Map of Content) - KU-Based (January 2026):**
```
MOCService (thin facade)
└── MocNavigationService  - All MOC navigation/organization
    └── KuService         - Underlying KU CRUD operations
```
**Key Insight:** MOC is NOT a separate entity - it IS a KU with ORGANIZES relationships. The old 6-service architecture was replaced with a single navigation service.

### Backend Pattern

| Domain | Backend Approach |
|--------|-----------------|
| **KU** | Direct `UniversalNeo4jBackend[Ku]` (no wrapper) |
| **LS** | `LsUniversalBackend` extends `UniversalNeo4jBackend[Ls]` |
| **LP** | `LpUniversalBackend` extends `UniversalNeo4jBackend[Lp]` |
| **MOC** | No backend - MOC uses KuService (MOC IS a KU with ORGANIZES) |

### Search Service Pattern

LS and LP search services inherit from `BaseService`, providing unified search infrastructure:

```python
class LsSearchService(BaseService["LsUniversalBackend", Ls]):
    _dto_class = LearningStepDTO
    _model_class = Ls
    _search_fields = ["title", "intent", "description"]
    _supports_user_progress = True  # Curriculum feature opt-in
    _user_ownership_relationship = None  # Shared content (no OWNS filter)
```

**Inherited Methods (via BaseService):**
- `search()`, `get_by_status()`, `get_by_domain()`
- `graph_aware_faceted_search()` - Rich graph context
- `get_prerequisites()`, `get_enables()` - Prerequisite chains
- `get_hierarchy()` - KU → LS → LP hierarchy
- `get_user_progress()` - User mastery data

### Intelligence Services

| Domain | Intelligence | Pattern |
|--------|--------------|---------|
| **KU** | `KuIntelligenceService` (197 lines) | Standalone service |
| **LP** | `LpIntelligenceService` (349 lines) | Standalone service |
| **LS** | None | Relies on LP parent intelligence |
| **MOC** | None | MOC is KU-based; uses KU intelligence |

**Key Insight:** KU and LP have standalone intelligence services for learning recommendations. LS relies on LP parent capabilities. MOC is KU-based (January 2026) so it uses KU intelligence and navigation services.

### Bootstrap Integration

Curriculum domains are created in `_create_learning_services()`:

```python
learning_services = _create_learning_services(
    driver=driver,
    progress_backend=progress_backend,
    learning_backend=learning_backend,
    # ...
)

# Extract services:
ku_service = learning_services["ku_service"]
learning_paths = learning_services["learning_paths"]  # LpService
learning_steps = learning_services["learning_steps"]  # LsService
```

MOC is created with KuService dependency (January 2026 - KU-based architecture):

```python
moc_service = MOCService(
    ku_service=learning_services["ku_service"],
    driver=driver,
)
```

### Key Design Decisions

1. **Appropriate Complexity** - Complex domains (KU) have more code; simple domains (LS) have minimal code
2. **No Unnecessary Duplication** - BaseService inheritance provides common search infrastructure
3. **Shared Content Model** - Curriculum domains have `_user_ownership_relationship = None` (no OWNS filter)
4. **Standalone Intelligence Where Needed** - KU/LP need learning recommendations; LS/MOC don't

---

## DSL Integration

The **Activity DSL** enables natural language parsing into all 14 domains:

### DSL Syntax

```markdown
# Activity Domains (6)
- [ ] Complete project report @context(task) @when(2025-12-01) @priority(1)
- [ ] Morning meditation @context(habit) @repeat(daily) @duration(20m)
- [ ] Launch MVP @context(goal) @when(2025-Q1)
- [ ] Team standup @context(event) @when(2025-11-28T09:00)
- [ ] Practice non-attachment @context(principle) @energy(spiritual)
- [ ] Choose tech stack @context(choice) @link(goal:mvp-launch)

# Finance Domain (1)
- [ ] AWS hosting $150 @context(finance) @category(skuel)

# Curriculum Domains (3)
- [ ] Python async/await patterns @context(ku) @energy(focus)
- [ ] Complete async exercises @context(ls) @ku(ku:python/async) @duration(2h)
- [ ] Master async programming @context(lp) @link(goal:python-expert)

# Content/Organization Domains (3)
- [ ] Process voice memo @context(report) @type(audio)
- [ ] Format journal entry @context(journal) @type(text)
- [ ] Organize Python knowledge @context(moc) @parent(moc:tech)

# LifePath - The Destination (1)
- [ ] Embody wisdom and service @context(lifepath) @link(principle:service)
```

### DSL Processing Pipeline

The complete pipeline from natural text to SKUEL entities:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: LLM DSL Bridge (Natural Text → DSL)                            │
│                                                                          │
│ Natural Journal Text:                                                    │
│ "I need to finish the quarterly report by Friday. Also want to          │
│  start meditating daily - 10 minutes each morning."                     │
│                           ↓                                              │
│            LLMDSLBridgeService.transform()                              │
│                           ↓                                              │
│ DSL-Tagged Text:                                                         │
│ - @context(task) Finish the quarterly report @when(Friday) @priority(1) │
│ - @context(habit) Meditate @repeat(daily) @duration(10)                 │
└─────────────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ PHASE 2: DSL Parsing (DSL → ParsedActivities)                           │
│                           ↓                                              │
│            ActivityDSLParser.parse_journal()                            │
│                           ↓                                              │
│ ParsedJournal:                                                           │
│   - tasks: [ParsedActivityLine(task, "Finish report", ...)]             │
│   - habits: [ParsedActivityLine(habit, "Meditate", ...)]                │
└─────────────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ PHASE 3: Entity Conversion (ParsedActivities → Domain Dicts)            │
│                           ↓                                              │
│            ActivityEntityConverter.convert_journal()                     │
│                           ↓                                              │
│ Dict with 15 keys (14 domains + errors):                                │
│   - tasks: [TaskCreateRequest(...)]                                      │
│   - habits: [HabitDict(...)]                                             │
│   - ...all 14 domains...                                                │
└─────────────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ PHASE 4: Entity Creation (Domain Dicts → SKUEL Entities)                │
│                           ↓                                              │
│       JournalActivityExtractorService.extract_and_create()              │
│                           ↓                                              │
│ Created Entities:                                                        │
│   - Task(uid="task:abc123", title="Finish report", ...)                 │
│   - Habit(uid="habit:xyz789", title="Meditate", ...)                    │
│                           ↓                                              │
│              DSLKnowledgeConnector.plan_connections()                   │
│                           ↓                                              │
│ Graph Relationships: APPLIES_KNOWLEDGE, FULFILLS_GOAL, etc.             │
└─────────────────────────────────────────────────────────────────────────┘
```

### LLM DSL Bridge

The `LLMDSLBridgeService` uses GPT-4o-mini to intelligently recognize activities in natural text and add appropriate @context tags:

```python
from core.services.dsl import create_llm_dsl_bridge

# Create bridge (uses OPENAI_API_KEY from environment)
bridge = create_llm_dsl_bridge()

# Transform natural text to DSL format
result = await bridge.transform(
    text="""
    I need to finish the quarterly report by Friday.
    Also want to start meditating daily - 10 minutes each morning.
    Thinking about whether to take that job offer.
    Spent $150 on groceries today.
    Want to learn Python for data science.
    Life goal: become a respected teacher who inspires others.
    """,
    user_uid="user:mike",
)

if result.is_ok:
    print(result.value.transformed_text)
    # Output:
    # - @context(task) Finish the quarterly report @when(Friday) @priority(high)
    # - @context(habit) Meditate @repeat(daily) @duration(10) @energy(low)
    # - @context(choice) Decide on job offer @priority(high)
    # - @context(finance) Groceries @amount(150) @when(today)
    # - @context(lp) Python for data science @priority(high)
    # - @context(lifepath) Become a respected teacher who inspires others

    print(f"Activities identified: {result.value.activities_identified}")
    # Activities identified: 6
```

**Domain Recognition Prompt:**

The LLM is instructed to recognize all 14 SKUEL domains:

| Domain | Recognition Pattern |
|--------|---------------------|
| `@context(task)` | One-time actions with deadlines |
| `@context(habit)` | Recurring behaviors to build |
| `@context(goal)` | Outcomes to achieve |
| `@context(event)` | Scheduled appointments/meetings |
| `@context(principle)` | Values/beliefs to embody |
| `@context(choice)` | Decisions to make |
| `@context(finance)` | Money matters |
| `@context(ku)` | Knowledge to acquire |
| `@context(ls)` | Learning activities |
| `@context(lp)` | Learning paths |
| `@context(report)` | Content to process |
| `@context(journal)` | AI-processed journal entries |
| `@context(moc)` | Knowledge hierarchy organization |
| `@context(lifepath)` | Life vision alignment |

---

## UserContext + Askesis Integration

The **Supporting Services** work together to provide intelligent content discovery based on user activities.

### The Integration Pattern

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    USER READY FOR CONTENT                                │
│                                                                          │
│  "What should I learn that's relevant to what I'm working on?"          │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 1: Get User Context (UserService)                                   │
│                                                                          │
│  user_context = await user_service.get_user_context(user_uid)           │
│                                                                          │
│  UserContext contains (~240 fields):                                     │
│    - active_goal_uids: ['goal:learn-python', 'goal:get-fit']            │
│    - habit_streaks: {'habit:meditate': 21, 'habit:read': 7}             │
│    - pending_choice_uids: ['choice:career-path']                        │
│    - active_task_uids: ['task:write-report']                            │
│    - core_principle_uids: ['principle:continuous-learning']              │
│    - upcoming_event_uids: ['event:workshop-ml']                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 2: Find Relevant Knowledge (AskesisService)                         │
│                                                                          │
│  relevant = await askesis_service.find_relevant_for_context(            │
│      active_goals=user_context.active_goal_uids,                        │
│      current_habits=list(user_context.habit_streaks.keys()),            │
│      recent_choices=user_context.pending_choice_uids,                   │
│  )                                                                       │
│                                                                          │
│  Returns:                                                                │
│    - knowledge_units: KUs relevant to user activities                   │
│    - relevance_scores: How relevant each KU is (0.0-1.0)                │
│    - relevance_reasons: WHY each KU is relevant                         │
│    - domain_coverage: Which domains each KU supports                    │
│    - recommended_order: Optimal learning order                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 3: Present to User                                                  │
│                                                                          │
│  "Based on your goals and activities, here's what to learn next:"       │
│                                                                          │
│  1. Python Async/Await (relevance: 0.9)                                  │
│     - Supports goal: learn-python                                        │
│     - Enables task: write-report                                         │
│     - Relevant to event: workshop-ml                                     │
│                                                                          │
│  2. Meditation Techniques (relevance: 0.7)                               │
│     - Reinforces habit: meditate                                         │
│     - Aligns with principle: continuous-learning                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### Usage Example

```python
from core.services.user_service import UserService
from core.services.askesis_service import AskesisService

# Get user's current context
user_context_result = await user_service.get_user_context(user_uid)
if user_context_result.is_error:
    return user_context_result

user_context = user_context_result.value

# Find knowledge relevant to their activities
relevant_result = await askesis_service.find_relevant_from_user_context(
    user_context,
    max_results=10,
    min_relevance_score=0.5,
)

if relevant_result.is_ok:
    relevant = relevant_result.value

    print(f"Found {len(relevant['knowledge_units'])} relevant knowledge units")

    for ku in relevant['knowledge_units']:
        uid = ku['uid']
        score = relevant['relevance_scores'][uid]
        reasons = relevant['relevance_reasons'][uid]
        domains = relevant['domain_coverage'][uid]

        print(f"\n{ku['title']} (relevance: {score:.2f})")
        print(f"  Domains covered: {', '.join(domains)}")
        for reason in reasons:
            print(f"  - {reason}")
```

### Relevance Scoring

Knowledge is scored based on multiple factors:

| Factor | Weight | Description |
|--------|--------|-------------|
| Connection Count | 0.2 per connection | More activity connections = more relevant |
| Domain Coverage | 0.15 per domain | Multi-domain KUs are more valuable |
| Goal Alignment | High | Knowledge required for active goals |
| Task Enablement | Medium | Knowledge that unblocks pending tasks |
| Habit Reinforcement | Medium | Knowledge supporting habit formation |
| Principle Grounding | Lower | Foundational knowledge for values |

### Methods Available

| Method | Purpose |
|--------|---------|
| `find_relevant_for_context()` | Find KUs relevant to specific activity UIDs |
| `find_relevant_from_user_context()` | Convenience method that extracts UIDs from UserContext |
| `get_knowledge_application_opportunities()` | Where can I apply a specific KU? |
| `get_optimal_next_learning_steps()` | What should I learn next? |
| `get_daily_work_plan()` | Complete daily plan across all domains |

---

### Domain Detection Methods

```python
class ParsedActivityLine:
    # Activity Domains (7)
    def is_task(self) -> bool: ...
    def is_habit(self) -> bool: ...
    def is_goal(self) -> bool: ...
    def is_event(self) -> bool: ...
    def is_principle(self) -> bool: ...
    def is_choice(self) -> bool: ...
    def is_finance(self) -> bool: ...

    # Curriculum Domains (3)
    def is_ku(self) -> bool: ...
    def is_ls(self) -> bool: ...
    def is_lp(self) -> bool: ...

    # Meta Domains (3)
    def is_report(self) -> bool: ...
    def is_calendar(self) -> bool: ...

    # The Destination (+1)
    def is_lifepath(self) -> bool: ...
```

---

## Graph Architecture

### Node Types (15 domains)

```cypher
// Activity Domains (6)
(:Task {uid, title, due_date, status, priority, ...})
(:Habit {uid, title, recurrence_pattern, streak, ...})
(:Goal {uid, title, target_date, progress, ...})
(:Event {uid, title, event_date, duration, ...})
(:Principle {uid, name, statement, category, ...})
(:Choice {uid, title, decision_deadline, ...})

// Finance Domain (1)
(:Expense {uid, amount, category, expense_date, ...})

// Curriculum Domains (3)
(:Ku {uid, title, content, domain, complexity, ...})
(:Ls {uid, title, intent, estimated_hours, ...})
(:Lp {uid, name, goal, difficulty, ...})

// Content/Processing Domains (2)
(:Report {uid, report_type, status, ...})
(:Journal {uid, content, processed_at, ...})

// Organizational Domains (2) - Groups + MOC
(:Group {uid, name, description, owner_uid, is_active, max_members, created_at, ...})
(:ReportProject {uid, name, instructions, scope, due_date, processor_type, group_uid, ...})
// MOC is KU-based
// MOC is NOT a separate node type - it IS a :Ku with ORGANIZES relationships
// A KU "is" a MOC when: EXISTS((ku:Ku)-[:ORGANIZES]->(:Ku))

// LifePath - The Destination (1)
// NOTE: LifePath is NOT a stored entity - it's a DESIGNATION on an LP
// The User designates an LP as their life path via ULTIMATE_PATH relationship
// Life path data is stored on User node (vision_statement, vision_themes, etc.)

// Supporting (not domains)
(:User {uid, email, name, ...})
```

### Relationship Types

```cypher
// Task Relationships
(task)-[:APPLIES_KNOWLEDGE]->(ku)
(task)-[:FULFILLS]->(goal)
(task)-[:DEPENDS_ON]->(task)
(task)-[:BLOCKED_BY]->(task)

// Habit Relationships
(habit)-[:REINFORCES]->(principle)
(habit)-[:SUPPORTS]->(goal)
(habit)-[:REQUIRES_KNOWLEDGE]->(ku)

// Goal Relationships
(goal)-[:INSPIRED_BY]->(choice)
(goal)-[:GUIDED_BY]->(principle)
(goal)-[:MILESTONE_OF]->(goal)  // sub-goals

// Knowledge Relationships
(ku)-[:REQUIRES]->(ku)  // prerequisites
(ku)-[:ENABLES]->(ku)   // what it unlocks
(ls)-[:TEACHES]->(ku)
(lp)-[:CONTAINS]->(ls)

// MOC Organizational Relationships (KU organizing KUs)
(ku)-[:ORGANIZES {order: int}]->(ku)  // MOC hierarchy

// Group & Assignment Relationships (ADR-040)
(teacher)-[:OWNS]->(group)                    // Teacher owns group
(student)-[:MEMBER_OF {joined_at, role}]->(group)  // Student membership
(project)-[:FOR_GROUP]->(group)               // Assignment targets group
(report)-[:FULFILLS_PROJECT]->(project)       // Student submission
(teacher)-[:SHARES_WITH {role: "teacher"}]->(report)  // Auto-shared on assignment submit

// Life Path Relationships
(user)-[:ULTIMATE_PATH]->(lp)             // User's designated life path
(entity)-[:SERVES_LIFE_PATH]->(lp)        // Entity contributes to life path

// User Ownership
(user)-[:OWNS]->(task|habit|goal|event|...)
(user)-[:MASTERED]->(ku)
(user)-[:LEARNING]->(ku)
(user)-[:ENROLLED]->(lp)
```

---

## Service Architecture

### Domain Services

Each domain has a consistent service structure:

```
core/services/
├── tasks/
│   ├── tasks_core_service.py       # CRUD operations
│   ├── tasks_relationship_service.py  # Graph relationships
│   └── tasks_intelligence_service.py  # AI features
├── habits/
│   ├── habits_core_service.py
│   ├── habits_relationship_service.py
│   └── habits_intelligence_service.py
├── goals/
│   └── ...
├── ku/
│   └── ...
├── ls/
│   └── ...
├── lp/
│   └── ...
└── ...
```

### Intelligence Service Base Class (January 2026)

All 6 Activity Domain intelligence services inherit from `BaseAnalyticsService[B, T]`:

```python
# core/services/base_intelligence_service.py
class BaseAnalyticsService(Generic[B, T]):
    _service_name: ClassVar[str] = "intelligence"      # Logger name
    _require_relationships: ClassVar[bool] = False     # Fail-fast validation

    def __init__(self, backend, graph_intelligence_service=None, relationship_service=None, ...):
        self.backend = backend
        self.graph_intel = graph_intelligence_service
        self.relationships = relationship_service
        self.logger = get_logger(f"skuel.services.{self._service_name}")
```

**Services Using BaseAnalyticsService:**
- `TasksIntelligenceService` - `_service_name = "tasks.intelligence"`
- `GoalsIntelligenceService` - `_service_name = "goals.intelligence"`, `_require_relationships = True`
- `HabitsIntelligenceService` - `_service_name = "habits.intelligence"`, `_require_relationships = True`
- `EventsIntelligenceService` - `_service_name = "events.intelligence"`
- `ChoicesIntelligenceService` - `_service_name = "choices.intelligence"`
- `PrinciplesIntelligenceService` - `_service_name = "principles.intelligence"`

### BaseService Mixin Architecture (January 2026)

`BaseService` is decomposed into 7 focused mixins following Single Responsibility Principle:

```python
class BaseService[B: BackendOperations, T: DomainModelProtocol](
    ConversionHelpersMixin[B, T],      # DTO conversion, result handling
    CrudOperationsMixin[B, T],          # create, get, update, delete, ownership
    SearchOperationsMixin[B, T],        # search, filtering, graph-aware search
    RelationshipOperationsMixin[B, T],  # graph relationships, prerequisites
    TimeQueryMixin[B, T],               # date range queries, due_soon, overdue
    UserProgressMixin[B, T],            # mastery tracking, curriculum progress
    ContextOperationsMixin[B, T],       # get_with_context, graph enrichment
):
```

**Location:** `/core/services/mixins/`

All 6 Activity Domain core services inherit from `BaseService`, gaining full mixin functionality with zero additional configuration.

**See:** [ADR-031](/docs/decisions/ADR-031-baseservice-mixin-decomposition.md)

### Facade Factory Pattern (January 2026)

Activity Domain facades use `create_common_sub_services()` from `core/utils/activity_domain_config.py`:

```python
# In facade __init__:
common = create_common_sub_services(
    domain="events",
    backend=backend,
    graph_intel=graph_intelligence_service,
    event_bus=event_bus,
)
self.core = common.core
self.search = common.search
self.relationships = common.relationships
self.intelligence = common.intelligence

# Domain-specific sub-services added after
self.habits = EventsHabitIntegrationService(...)
```

**Key Files:**
- `core/utils/activity_domain_config.py` - Domain registry + factory function
- `core/services/base_intelligence_service.py` - Base class for intelligence services
- `core/services/base_service.py` - Composed of 7 mixins (see ADR-031)
- `core/services/mixins/` - BaseService mixin implementations

### Supporting Services

```
core/services/
├── user/
│   ├── user_service.py
│   ├── user_context_builder.py
│   └── unified_user_context.py
├── search/
│   ├── semantic_search_service.py
│   └── embeddings_service.py
├── askesis/
│   └── askesis_service.py
└── dsl/
    ├── activity_dsl_parser.py
    ├── activity_entity_converter.py
    └── journal_activity_extractor.py
```

### Meta Services

```
core/services/
├── reports/                                  # Reports domain (January 2026)
│   ├── __init__.py
│   ├── reports_submission_service.py
│   ├── reports_processing_service.py
│   ├── reports_core_service.py
│   ├── reports_search_service.py
│   ├── reports_relationship_service.py
│   ├── report_project_service.py            # ReportProject CRUD + assignment scope
│   └── teacher_review_service.py            # Teacher review queue + feedback (ADR-040)
├── groups/                                   # Groups domain (ADR-040)
│   ├── __init__.py
│   └── group_service.py                     # CRUD + membership management
├── report_service.py
├── reports/
│   ├── report_metrics_service.py
│   ├── report_aggregation_service.py
│   └── report_life_path_service.py
└── calendar_service.py
```

---

## API Routes Structure

Every domain follows the **Factory Pattern**:

```
adapters/inbound/
├── tasks_routes.py           # Factory
├── tasks_api.py              # REST endpoints
├── tasks_intelligence_api.py # AI features
├── tasks_ui.py               # UI components
├── habits_routes.py
├── habits_api.py
├── habits_intelligence_api.py
├── habits_ui.py
└── ... (all 14 domains)
```

### REST Endpoints Pattern

```
POST   /{domain}/create     # Create entity
GET    /{domain}/get        # Get by UID
POST   /{domain}/update     # Update entity
POST   /{domain}/delete     # Delete entity
GET    /{domain}/list       # List with pagination
GET    /{domain}/search     # Search entities
```

---

## Cross-Domain Intelligence

### The Intelligence Flow

```
User Action (any domain)
       ↓
UserContext updated
       ↓
Cross-domain analysis
       ↓
Recommendations generated
       ↓
Life path alignment calculated
```

### Intelligence Examples

**Task Intelligence**:
```python
# When completing a task that applies knowledge
async def on_task_completed(task_uid: str):
    # Update knowledge mastery
    for ku_uid in task.applies_knowledge_uids:
        await update_mastery(ku_uid, delta=0.05)

    # Check goal progress
    if task.fulfills_goal_uid:
        await update_goal_progress(task.fulfills_goal_uid)

    # Update life path alignment
    await recalculate_life_alignment(user_uid)
```

**Habit Intelligence**:
```python
# When habit streak increases
async def on_habit_streak_increased(habit_uid: str, streak: int):
    # Strengthen principle reinforcement
    for principle_uid in habit.reinforces_principle_uids:
        await strengthen_principle_adherence(principle_uid)

    # Update related goal progress
    for goal_uid in habit.supports_goal_uids:
        await update_goal_momentum(goal_uid)
```

**Knowledge Intelligence**:
```python
# When knowledge mastery increases
async def on_mastery_increased(ku_uid: str, new_mastery: float):
    # Unlock dependent knowledge
    dependents = await get_knowledge_dependents(ku_uid)
    for dep_uid in dependents:
        await check_prerequisite_completion(dep_uid, user_uid)

    # Update learning path progress
    await update_learning_path_progress(user_uid)
```

---

## Implementation Status

### Fully Implemented (November 2025)

| Component | Status | Location |
|-----------|--------|----------|
| DSL Parser (14 domains) | ✅ Complete | `core/services/dsl/activity_dsl_parser.py` |
| Entity Converters (14 domains) | ✅ Complete | `core/services/dsl/activity_entity_converter.py` |
| Activity Extractor (14 domains) | ✅ Complete | `core/services/dsl/journal_activity_extractor.py` |
| Activity Domain Services (7) | ✅ Complete | `core/services/{domain}/` |
| Curriculum Domain Services (3) | ✅ Complete | `core/services/ku/, ls/, lp/` |
| UserContext | ✅ Complete | `core/services/user/unified_user_context.py` |
| Search Service | ✅ Complete | `core/services/search/` |
| Report Service | ✅ Complete | `core/services/report_service.py` |
| Calendar Service | ✅ Complete | `core/services/calendar_service.py` |
| Reports Pipeline | ✅ Complete | `core/services/reports/` |

### In Development

| Component | Status | Target |
|-----------|--------|--------|
| LifePath Service | 🔄 Partial | Q4 2025 |
| Askesis Service | 🔄 Partial | Q4 2025 |
| Messaging Service | 📋 Planned | Q1 2026 |

---

## Summary

The **15-domain + 5 cross-cutting systems architecture** provides a complete framework for:

1. **What I DO** (Activity Domains) - 6 domains for concrete action
2. **What I MANAGE** (Finance) - 1 domain for resource management
3. **What I LEARN** (Curriculum Domains) - 3 domains for knowledge acquisition
4. **How I PROCESS** (Content/Processing) - 2 domains for input processing (Reports, Journals)
5. **How I ORGANIZE** (Organizational Domains) - 2 domains (Groups for classes, MOC for knowledge)
6. **Where I'm GOING** (LifePath) - Domain #15, the destination
7. **The Infrastructure** (Cross-Cutting Systems) - 4 active + 1 planned system

**Domain Count Breakdown**:
- Activity: 6 (Tasks, Habits, Goals, Events, Principles, Choices)
- Finance: 1 (standalone)
- Curriculum: 3 (KU, LS, LP)
- Content/Processing: 2 (Reports, Journals)
- Organizational: 2 (Groups for teacher-student classes, MOC for knowledge navigation)
- LifePath: 1 (The Destination)
- **Total: 15 domains**

**Cross-Cutting Systems**: UserContext (✅), Search (✅), Calendar (✅), Askesis (✅), Messaging (📋 planned)

**Core Insight**: By categorizing all human activity into 15 domains + 5 cross-cutting systems, SKUEL can:
- Parse natural language into structured entities
- Track progress across all life dimensions
- Provide intelligent recommendations
- Measure alignment with life purpose
- Connect knowledge to action

**Philosophy**: "Everything flows toward the life path."

---

## See Also

### Architecture Documentation

| Document | Purpose |
|----------|---------|
| [UNIFIED_USER_ARCHITECTURE.md](UNIFIED_USER_ARCHITECTURE.md) | UserContext (~240 fields), ProfileHubData |
| [NEO4J_DATABASE_ARCHITECTURE.md](NEO4J_DATABASE_ARCHITECTURE.md) | Database schema, constraints, indexes |
| [RELATIONSHIPS_ARCHITECTURE.md](RELATIONSHIPS_ARCHITECTURE.md) | Cross-domain relationships |
| [CURRICULUM_GROUPING_PATTERNS.md](CURRICULUM_GROUPING_PATTERNS.md) | KU/LS/LP/MOC curriculum patterns |
| [REPORTS_ARCHITECTURE.md](REPORTS_ARCHITECTURE.md) | Analytics meta-service pattern |
| [SEARCH_ARCHITECTURE.md](SEARCH_ARCHITECTURE.md) | Unified search across all domains |

### Domain Documentation

| Domain | Documentation |
|--------|---------------|
| Activity Domains | [/docs/domains/](../domains/) (tasks, goals, habits, events, choices, principles) |
| Finance | [/docs/domains/finance.md](../domains/finance.md) |
| Curriculum | [CURRICULUM_GROUPING_PATTERNS.md](CURRICULUM_GROUPING_PATTERNS.md) |
| Journals | [/docs/domains/journals.md](../domains/journals.md) |
| Reports | [ASSIGNMENTS_PIPELINE.md](ASSIGNMENTS_PIPELINE.md) |

### Related Patterns

- [protocol_architecture.md](../patterns/protocol_architecture.md) - Protocol-based dependency injection
- [query_architecture.md](../patterns/query_architecture.md) - Query builders and patterns

---

*Last Updated: February 6, 2026*
*Architecture: 15-Domain + 5 Cross-Cutting Systems (4 active + 1 planned)*
*Status: Production-Ready*
