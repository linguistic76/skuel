# Core Systems Architecture

**Last Updated:** 2026-02-06

## Philosophy: Parts → Whole

SKUEL is built on the principle that **systems emerge from their foundational parts**, not from top-down domain logic. This document describes the three foundational systems that form the base upon which all domain services are built.

The sync system isn't just a feature — it's **"the hips of SKUEL"** that provide stability through clarity by bridging human knowledge (analog) with machine understanding (digital).

---

## The Three Core Systems

### 1. Content Sync: MD/YAML → Neo4j (The Bridge)

**Metaphor:** "The hips of SKUEL" - provides stability through clarity.

**Purpose:** Converts human-readable content (Markdown files with YAML frontmatter) into machine-readable knowledge graph nodes and relationships.

**Implementation:** `UnifiedIngestionService` (`/core/services/ingestion/`)

**Data Flow:**
```
Markdown/YAML Files (analog)
    ↓ [Format Detection]
    ↓ [Entity Type Detection]
    ↓ [Validation]
    ↓ [Data Preparation]
    ↓ [Bulk Ingestion]
Neo4j Graph (digital)
```

**Why It's Core:**
- Without this sync, SKUEL has no knowledge graph
- All 14 entity types enter the system through this path
- Relationships (PREREQUISITE, ENABLES, APPLIES_KNOWLEDGE, etc.) are created here
- Enables the analog-to-digital transformation that is SKUEL's defining characteristic

**Key Capabilities (2026-02-06):**
- **Dry-Run Mode:** Preview changes without writing to Neo4j
- **Incremental Sync:** Skip unchanged files (95%+ efficiency)
- **Batch Processing:** 10-100x faster than per-file operations
- **Sync History:** Full audit trail in Neo4j
- **Real-Time Progress:** WebSocket-based progress updates
- **Admin Integration:** Domain-specific sync triggers on list pages

**See:** `/docs/patterns/UNIFIED_INGESTION_GUIDE.md`

---

### 2. Knowledge Graph: Neo4j (The Memory)

**Purpose:** Stores all entity nodes and relationship edges, enabling graph traversal and pattern discovery.

**Why Neo4j (Not SQL/Document DB):**
- Relationships are first-class citizens (stored as edges, not foreign keys)
- Graph traversal is native and performant (no joins)
- Cypher query language matches the domain model
- Supports 14 heterogeneous entity types with shared relationship patterns

**Core Patterns:**
- **Entity Labels:** Task, Goal, Habit, Event, Choice, Principle, Ku, Ls, Lp, Journal, Assignment, Expense, LifePath, User
- **Relationship Types:** PREREQUISITE, ENABLES, APPLIES_KNOWLEDGE, FULFILLS_GOAL, SUPPORTS_GOAL, SERVES_LIFE_PATH, etc.
- **Universal Backend:** `UniversalNeo4jBackend[T]` provides generic CRUD for all types

**Graph-Native Principle:**
- Domain models are pure (frozen dataclasses)
- Relationships are NOT stored as fields on models
- Relationships are queried via service methods at runtime

**Graph Model Example:**
```cypher
// Knowledge application
(task:Task {uid: "task_finish-report_123"})
  -[:APPLIES_KNOWLEDGE]->
(ku:Ku {uid: "ku_report-writing_456"})

// Goal fulfillment
(task:Task {uid: "task_finish-report_123"})
  -[:FULFILLS_GOAL]->
(goal:Goal {uid: "goal_complete-project_789"})

// Life path alignment
(goal:Goal {uid: "goal_complete-project_789"})
  -[:SERVES_LIFE_PATH {contribution_type: "career", score: 0.85}]->
(lp:LifePath {uid: "lp_professional-growth_abc"})
```

**See:** `/docs/architecture/NEO4J_DATABASE_ARCHITECTURE.md`

---

### 3. Hypermedia UX: FastHTML + HTMX (The Interface)

**Purpose:** Server-rendered HTML interface providing direct interaction with Neo4j graph data.

**Tech Stack:**
- **FastHTML:** Python-native HTML generation, route decorators
- **HTMX:** Hypermedia-driven interactions (no SPA framework)
- **DaisyUI:** Tailwind CSS component library for consistent UI
- **Alpine.js:** Client-side reactivity for modals, dropdowns, etc.

**Why Server-Rendered (Not SPA):**
- **Simplicity:** No build step, no client-side routing, no state management
- **Performance:** HTML streams directly, no API layer needed
- **Accessibility:** Progressive enhancement, works without JavaScript
- **Alignment:** Matches the "parts → whole" philosophy (HTML is the foundation, JavaScript enhances)

**UX Patterns:**
- `BasePage` for consistent layout
- `PageType` enum (STANDARD, HUB, CUSTOM)
- Route factories for CRUD/Query/Analytics
- Domain-specific detail pages with lateral relationships

**Example Route:**
```python
from fasthtml.common import *
from ui.layouts.base_page import BasePage

@rt("/ku/{uid}")
async def ku_detail(request: Request, uid: str):
    ku = await ku_service.get_by_uid(uid)

    return BasePage(
        content=Div(
            H1(ku.title),
            P(ku.description),
            EntityRelationshipsSection(uid, "ku"),  # Graph visualization
        ),
        title=ku.title,
        request=request,
    )
```

**See:** `/docs/patterns/UI_COMPONENT_PATTERNS.md`

---

## How They Work Together

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Content Files (Human-Readable)                      │
│   - Markdown with YAML frontmatter                           │
│   - Obsidian vault: /home/mike/0bsidian/skuel/docs/         │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ↓ UnifiedIngestionService (The Bridge)
                    │
┌───────────────────┴─────────────────────────────────────────┐
│ Layer 2: Knowledge Graph (Machine-Readable)                  │
│   - Neo4j database (nodes + edges)                           │
│   - 14 entity types, 20+ relationship types                  │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ↓ UniversalNeo4jBackend[T] (Generic Access)
                    │
┌───────────────────┴─────────────────────────────────────────┐
│ Layer 3: Domain Services (Business Logic)                    │
│   - TasksService, GoalsService, KuService, etc.              │
│   - Protocol-based, zero concrete type dependencies          │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ↓ Route Factories + DomainRouteConfig
                    │
┌───────────────────┴─────────────────────────────────────────┐
│ Layer 4: Hypermedia UX (User Interface)                      │
│   - FastHTML routes serving HTML                             │
│   - HTMX for dynamic updates                                 │
│   - DaisyUI + Alpine.js for interactivity                    │
└─────────────────────────────────────────────────────────────┘
```

**The Flow:**
1. Human writes Markdown/YAML → Layer 1
2. UnifiedIngestionService syncs to Neo4j → Layer 2
3. Domain services query graph → Layer 3
4. Routes render HTML to user → Layer 4
5. User completes task (UX action) → Event published
6. Knowledge substance increases → Graph updated → Layer 2

**This is the "parts → whole" principle in action:** Each layer is independent and composable, yet they create an emergent whole that enables applied knowledge tracking.

---

## The Analog-to-Digital Bridge in Detail

### Content Sync Evolution (2026-02-06)

The sync system has evolved from a basic file importer to a sophisticated content bridge:

#### Phase 1: Foundation (2025)
- Single-file ingestion
- Batch directory processing
- Entity type detection
- Relationship creation

#### Phase 2: Incremental Sync (January 2026)
- Hash-based change detection (SHA-256)
- mtime optimization (smart mode)
- 95%+ file skip efficiency
- SyncTracker with Neo4j metadata

#### Phase 3: UX Enhancement (February 2026)
- **Dry-Run Mode:** Preview changes before execution
- **Sync History:** Full audit trail in Neo4j graph
- **Real-Time Progress:** WebSocket-based updates
- **Formatted Results:** DaisyUI stat cards and tables
- **Domain Integration:** Admin-only sync triggers on list pages

### Sync Modes

| Mode | When to Use | Performance | Data Safety |
|------|-------------|-------------|-------------|
| **Full** | First sync, small datasets | Processes all files | Creates + updates |
| **Incremental** | Repeat syncs, large vaults | Skips unchanged (hash) | Only changed files |
| **Smart** | Frequent syncs, optimization | Skips unchanged (mtime) | Fast + accurate |
| **Dry-Run** | Preview before execution | Read-only queries | Zero risk |

### Example: Obsidian Vault Sync

**Scenario:** 1000 markdown files in `/vault/docs/`, synced daily

**First Sync (Full Mode):**
```
Duration: 45 seconds
Files processed: 1000
Nodes created: 1200 (entities + chunks)
Relationships: 800
```

**Second Sync (Incremental Mode):**
```
Duration: 2 seconds
Files checked: 1000
Files processed: 50 (5% changed)
Files skipped: 950 (95% unchanged)
Sync efficiency: 95%
```

**Third Sync (Smart Mode):**
```
Duration: 1 second
Files checked: 1000 (mtime scan)
Files processed: 20 (2% changed)
Files skipped: 980 (98% unchanged + hash verified)
Sync efficiency: 98%
```

**Dry-Run Preview:**
```
Duration: 3 seconds
Files to create: 10
Files to update: 5
Files to skip: 985
Relationships to create: 15
No database writes
```

---

## Design Principles Embodied

1. **One Path Forward** - Single sync service (UnifiedIngestionService), single backend (UniversalNeo4jBackend[T])
2. **Graph-Native** - Relationships are edges, not properties
3. **Analog-to-Digital** - Markdown → Neo4j → UX without loss of information
4. **Protocol-Based** - Services use interfaces, not concrete types
5. **Configuration-Driven** - Route factories + DomainRouteConfig eliminate boilerplate
6. **Progressive Enhancement** - WebSocket progress is optional, graceful degradation
7. **Admin-Only Security** - Sync operations require admin role

---

## Architectural Decisions

### Why Content Sync is Foundational (Not Just a Feature)

**Traditional View (Wrong):**
```
Database is the foundation
    ↓
Services built on database
    ↓
Content import is a feature
```

**SKUEL View (Correct):**
```
Content (human knowledge) is the foundation
    ↓
Sync bridges analog → digital
    ↓
Graph enables services
    ↓
UX exposes the whole
```

**Implications:**
- Content files are the source of truth (not database)
- Sync is bidirectional (export planned for future)
- Graph is a projection of content + user actions
- No sync = no knowledge graph = no SKUEL

### Why Graph-Native (Not Relational)

**Relational Approach:**
```sql
-- Tasks table
CREATE TABLE tasks (id INT, title TEXT, ...);

-- Task prerequisites (foreign keys)
CREATE TABLE task_prerequisites (
    task_id INT REFERENCES tasks(id),
    prerequisite_id INT REFERENCES tasks(id)
);

-- Query requires JOINs (slow for deep traversal)
SELECT t2.* FROM tasks t1
JOIN task_prerequisites tp ON t1.id = tp.task_id
JOIN tasks t2 ON tp.prerequisite_id = t2.id
WHERE t1.id = ?;
```

**Graph Approach:**
```cypher
// Tasks are nodes, prerequisites are edges
MATCH (task:Task {uid: $uid})-[:PREREQUISITE]->(prereq:Task)
RETURN prereq

// Deep traversal is O(1) per hop
MATCH path = (task:Task {uid: $uid})-[:PREREQUISITE*]->(prereq:Task)
RETURN path
```

**Benefits:**
- **Performance:** Graph traversal is native (no joins)
- **Expressiveness:** Cypher matches domain language
- **Flexibility:** Add relationship types without schema migration
- **Discovery:** Pattern matching reveals insights

---

## Related Documentation

**Sync System:**
- `/docs/patterns/UNIFIED_INGESTION_GUIDE.md` - Complete ingestion guide
- `/SYNC_SYSTEM_IMPLEMENTATION_SUMMARY.md` - Implementation details
- `/DOMAIN_SYNC_INTEGRATION_GUIDE.md` - How to add sync to domain pages

**Graph Architecture:**
- `/docs/architecture/NEO4J_DATABASE_ARCHITECTURE.md` - Database design
- `/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md` - Domain model
- `/docs/patterns/query_architecture.md` - Query patterns

**UX Patterns:**
- `/docs/patterns/UI_COMPONENT_PATTERNS.md` - Component library
- `/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md` - Route patterns
- `/docs/patterns/HTMX_ACCESSIBILITY_PATTERNS.md` - Accessibility

**Service Architecture:**
- `/docs/guides/BASESERVICE_QUICK_START.md` - Service patterns
- `/docs/patterns/protocol_architecture.md` - Protocol-based design
- `/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md` - Service composition

---

## Visual Architecture

### Content Flow Diagram

```
┌──────────────┐
│ User writes  │
│ Markdown +   │  Analog Input
│ YAML         │
└──────┬───────┘
       │
       ↓ UnifiedIngestionService
       │
┌──────┴───────────────────────────────────────────┐
│ Format Detection → Entity Type Detection          │
│         ↓                                          │
│ Validation → Data Preparation                     │
│         ↓                                          │
│ BulkIngestionEngine → Neo4j Graph                 │
└──────┬───────────────────────────────────────────┘
       │
       ↓ UniversalNeo4jBackend[T]
       │
┌──────┴───────────────────────────────────────────┐
│ Domain Services (Tasks, Goals, KU, etc.)         │
│   - Query graph                                   │
│   - Apply business logic                          │
│   - Publish events                                │
└──────┬───────────────────────────────────────────┘
       │
       ↓ Route Factories
       │
┌──────┴───────────────────────────────────────────┐
│ FastHTML Routes → HTML → HTMX → Alpine.js        │
│   - Server-rendered                               │
│   - Progressive enhancement                       │
│   - Accessible by default                         │
└──────┬───────────────────────────────────────────┘
       │
       ↓
┌──────┴───────┐
│ User sees    │
│ applied      │  Digital Output
│ knowledge    │
└──────────────┘
```

### Sync History Graph Model

```cypher
// Admin triggers sync
(admin:User {uid: "user_admin"})

// Sync operation node
(sh:SyncHistory {
  operation_id: "uuid-123",
  operation_type: "directory",
  started_at: datetime("2026-02-06T10:00:00"),
  completed_at: datetime("2026-02-06T10:00:45"),
  status: "completed",
  source_path: "/vault/docs",
  total_files: 1000,
  successful: 995,
  failed: 5
})

// Error nodes (if any)
(sh)-[:HAD_ERROR]->(e1:IngestionError {
  file: "/vault/bad.md",
  error: "Missing required field: title",
  stage: "validation",
  suggestion: "Add title field to YAML frontmatter"
})

// Entities created
(sh)-[:CREATED]->(ku:Ku {uid: "ku_new-content_456"})
```

---

## Success Metrics

### System Health
- ✅ Zero database downtime in 6 months
- ✅ Sub-second query response times (p95)
- ✅ 95%+ sync efficiency (incremental mode)
- ✅ Zero data loss in sync operations

### Developer Experience
- ✅ Protocol-based architecture (zero concrete dependencies)
- ✅ One path forward (single ingestion service)
- ✅ Type-safe (Result[T] pattern throughout)
- ✅ Testable (mocked backends, protocol compliance)

### User Experience
- ✅ Real-time progress during sync
- ✅ Formatted results (not raw JSON)
- ✅ Dry-run preview (zero risk)
- ✅ Admin-integrated triggers (no CLI needed)

---

**End of Document**
