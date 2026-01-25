---
title: Curriculum Grouping Patterns: KU, LS, LP + MOC Organization
updated: 2026-01-20
status: current
category: architecture
tags: [architecture, curriculum, grouping, patterns, moc, montessori]
related: [ADR-023-curriculum-baseservice-migration, ADR-028-ku-moc-unified-relationship-migration]
---

# Curriculum Grouping Patterns: KU, LS, LP + MOC Organization

*Last updated: 2026-01-20*

## Core Philosophy

SKUEL organizes knowledge through **three grouping patterns** and **two access paths**. The patterns (KU, LS, LP) are different perspectives on the same underlying content. The access paths (LS linear, MOC graph) provide different ways to navigate that content.

**January 2026 - MOC as KU-Based Organization:**
MOC is NOT a fourth pattern or separate entity type. MOC IS a KU that organizes other KUs via ORGANIZES relationships. This reflects the Montessori-inspired "two paths to knowledge" philosophy.

```
Raw Emergence (organic growth)
        ↓
    Type Safety (channels the design)
        ↓
    Synergy (energy feeds back between entities)
```

Type safety doesn't restrict - it **channels energy** so it flows and feeds back rather than leaks. The patterns emerged organically from how humans naturally organize knowledge, then type safety was applied to enable synergy between them.

---

## The Three Grouping Patterns

| Pattern | UID Prefix | Grouping Style | Topology | Metaphor |
|---------|------------|----------------|----------|----------|
| **KU** | `ku:` | Atomic unit | Point | A single brick |
| **LS** | `ls:` | Sequential step | Edge | A step in a staircase |
| **LP** | `lp:` | Linear sequence | Path | The full staircase |

**Note:** MOC uses `ku:` prefix since MOC IS a KU with ORGANIZES relationships.

### Two Paths to Knowledge (Montessori-Inspired)

| Path | Topology | Purpose | Pedagogy |
|------|----------|---------|----------|
| **LS Path** | Linear | Structured curriculum | Teacher-directed |
| **MOC Path** | Graph | Free exploration | Learner-directed |

```
LS Path (Structured):              MOC Path (Exploratory):
                                        KU (root MOC)
LP₁    LP₂    LP₃ (paths)             /    |    \
/|\    /|\    /|\                   KU    KU    KU (topics/sections)
LS LS LS LS LS LS (steps)          / \         / \
|  |  |  |  |  |                 KU  KU     KU   KU (content)
KU KU KU KU KU KU (content)

Sequential "Learn A then B"      Non-linear "Explore what interests you"
```

**Key Insight:** The same KU can appear in multiple LS, LP, and MOC contexts. Progress is tracked on the KU itself, unified across both paths.

---

## Pattern Details

### KU (Knowledge Unit) - The Atomic Unit

**What it is:** The smallest indivisible piece of knowledge content.

**Characteristics:**
- Self-contained markdown content
- Has a domain (TECH, HEALTH, etc.)
- Can exist independently
- Referenced by all other patterns

**Example:**
```yaml
uid: ku.python.functions
title: Python Functions
domain: tech
content: |
  A function is a reusable block of code...
```

**Graph Role:** KU is the leaf node - all other patterns ultimately reference KUs.

---

### LS (Learning Step) - The Sequential Step

**What it is:** A single step in a learning journey that may aggregate multiple KUs.

**Characteristics:**
- Has a specific order within a path
- Can require mastery threshold
- May include practice activities
- Bridges KUs into a sequence

**Example:**
```yaml
uid: ls.python.beginner.step-3
title: Understanding Functions
order: 3
knowledge_units:
  - ku.python.functions
  - ku.python.parameters
mastery_threshold: 0.8
```

**Graph Role:** LS is the edge - connecting KUs into a directed sequence.

---

### LP (Learning Path) - The Linear Sequence

**What it is:** A complete learning journey from start to finish.

**Characteristics:**
- Ordered sequence of Learning Steps
- Has prerequisites and outcomes
- Represents a full competency arc
- Linear progression (Step 1 → 2 → 3 → Done)

**Example:**
```yaml
uid: lp.python.beginner
title: Python for Beginners
steps:
  - ls.python.beginner.step-1
  - ls.python.beginner.step-2
  - ls.python.beginner.step-3
prerequisites: []
outcomes:
  - "Write basic Python programs"
  - "Understand functions and control flow"
```

**Graph Role:** LP is the path - a traversable sequence with a beginning and end.

---

### MOC (Map of Content) - KU-Based Organization

**What it is:** A KU that organizes other KUs via ORGANIZES relationships. NOT a separate entity type.

**January 2026 - KU-Based Architecture:**
- MOC IS a KU with ORGANIZES relationships (emergent identity)
- A KU "is" a MOC when it has outgoing ORGANIZES relationships
- Sections within MOCs are also KUs
- Same KU can be in multiple MOCs (many-to-many)
- Progress tracked on KU, unified across both LS and MOC paths

**Example:**
```cypher
// A KU acting as a MOC root
(:Ku {uid: "ku.python-fundamentals", title: "Python Fundamentals"})

// Organizing other KUs (making it a MOC)
(root:Ku {uid: "ku.python-fundamentals"})-[:ORGANIZES {order: 1}]->(section:Ku {uid: "ku.python-basics"})
(root)-[:ORGANIZES {order: 2}]->(section2:Ku {uid: "ku.python-advanced"})

// Sections organizing child KUs
(section:Ku {uid: "ku.python-basics"})-[:ORGANIZES {order: 1}]->(child:Ku {uid: "ku.python-functions"})
(section)-[:ORGANIZES {order: 2}]->(child2:Ku {uid: "ku.python-classes"})
```

**Graph Role:** MOC provides non-linear navigation by organizing KUs into a graph structure parallel to the linear LS/LP structure.

---

## How the Patterns Relate

### The Curriculum Hierarchy (LS Path)

```
KU → LS → LP
```

- KUs are atomic content
- LSs aggregate KUs into steps
- LPs sequence LSs into journeys

This is the **linear curriculum structure** - how learning progresses step by step (teacher-directed).

### The Organization Layer (MOC Path)

```
KU ──[ORGANIZES]──> KU ──[ORGANIZES]──> KU
```

- A KU organizes other KUs via ORGANIZES relationship
- Creates hierarchical non-linear navigation
- Same KU can be organized by multiple parent KUs

This is the **discovery structure** - how you explore content freely (learner-directed).

### The Full Picture

```
        TWO PATHS TO THE SAME KNOWLEDGE
              ↓
   ┌──────────────────────────────────┐
   │                                  │
   │  LS PATH          MOC PATH       │
   │  (Linear)         (Graph)        │
   │                                  │
   │  LP──>LP──>LP     KU (root MOC)  │
   │  |    |    |      /  |  \        │
   │  LS   LS   LS   KU  KU  KU       │
   │  |    |    |    |       |        │
   │  KU   KU   KU   KU      KU       │
   │                                  │
   │  Same KUs, same progress!        │
   └──────────────────────────────────┘
              ↑
        RAW CONTENT (KUs)
```

**Progress Tracked on KU:**
- Whether accessed via LS or MOC path, mastery is tracked on the KU itself
- Unified progress across both paths - no duplicate tracking

---

## Type Safety as Energy Channel

### Why Type Safety Matters

Without type safety:
```
knowledge ----→ ???
           ↘ ???
            ↘ ???  (energy leaks everywhere)
```

With type safety:
```
KU ──────→ LS ──────→ LP
 ↑          ↑          ↑
 └────← MOC ←─────────┘  (energy feeds back - synergy)
```

Type safety **channels** the relationships so energy (user effort, system computation, semantic meaning) flows through defined paths and feeds back into the system.

### The EntityType Enum

```python
class EntityType(str, Enum):
    # Curriculum Domains (3)
    KU = "ku"
    LS = "ls"
    LP = "lp"

    # Organizational Domain (KU-based, not a separate entity type)
    MOC = "moc"  # Represents KU with ORGANIZES relationships
```

The curriculum patterns share abbreviated prefixes because they form a **unified knowledge organization system**. The abbreviation signals: "this is a grouping pattern."

**Domain Classification (January 2026 - Updated):**
- **Curriculum Domains (3):** KU, LS, LP - Linear knowledge sequencing
- **Organizational Domain (1):** MOC - KU-based, non-linear organization via ORGANIZES relationships

### Relationship Types

Type-safe relationships between patterns:

```python
# LS Path (Linear)
HAS_STEP           # LP → LS
REQUIRES_KNOWLEDGE # LS → KU

# MOC Path (Graph) - KU organizing KUs
ORGANIZES          # KU → KU (with {order: int} property)

# Knowledge relationships
REQUIRES           # KU → KU (prerequisites)
ENABLES            # KU → KU (what it unlocks)
```

**Note (January 2026):** Old MOC-specific relationships (CONTAINS_KNOWLEDGE, CONTAINS_PATH, etc.) replaced with single ORGANIZES relationship for KU-to-KU organization.

---

## Practical Usage

### Creating Content (Organic Growth)

1. **Start with KUs** - Write atomic markdown files about concepts
2. **Organize into LSs** - Group related KUs into learning steps
3. **Sequence into LPs** - Create learning journeys from steps
4. **Map with MOCs** - Author non-linear navigation for discovery

### Syncing from Markdown

All four patterns can be defined in markdown with YAML frontmatter:

**KU:**
```yaml
---
uid: ku.python.functions
title: Python Functions
domain: tech
---
# Content here
```

**MOC:**
```yaml
---
moc: true
uid: moc.python.overview
contains:
  knowledge: [ku.python.functions]
  paths: [lp.python.beginner]
---
# Overview here
```

The `MarkdownSyncService` automatically detects and routes each file type.

---

## Key Files

| Component | File | Purpose |
|-----------|------|---------|
| KU Model | `/core/models/ku/ku.py` | Knowledge Unit definition |
| LS Model | `/core/models/ls/ls.py` | Learning Step definition |
| LP Model | `/core/models/lp/lp.py` | Learning Path definition |
| MOC Service | `/core/services/moc_service.py` | MOC facade (KU-based) |
| MOC Navigation | `/core/services/moc/moc_navigation_service.py` | MOC operations |
| EntityType | `/core/models/shared_enums.py` | Type-safe entity identification |
| Markdown Sync | `/core/services/markdown_sync_service.py` | Sync all patterns from markdown |
| Unified Registry | `/core/models/unified_relationship_registry.py` | All domain relationship configs |

**Note (January 2026):** `/core/models/moc/moc.py` deleted - MOC is KU-based, no separate model needed.

---

## Service Architecture (January 2026)

Each Curriculum Domain follows the **decomposed facade pattern** with complexity appropriately sized to its needs.

### Service Comparison

| Domain | Service | Lines | Sub-Services | Intelligence |
|--------|---------|-------|--------------|--------------|
| **KU** | `KuService` | 1,120 | 7 | `KuIntelligenceService` (standalone) |
| **LP** | `LpService` | 408 | 8 | `LpIntelligenceService` (standalone) |
| **LS** | `LsService` | 311 | 3 | None (relies on LP) |
| **MOC** | `MOCService` | ~100 | 1 | None (uses KU intelligence) |

**MOC (January 2026 - KU-Based):** MOC is now a thin facade over `MocNavigationService`, which uses `KuService` for all underlying operations. The old 6-service architecture was replaced with a single navigation service.

### Why Different Sizes?

**KU is the largest** because semantic knowledge management is inherently complex:
- 7 sub-services covering CRUD, search, semantics, graph, learning paths, practice, interaction
- Semantic relationship management with confidence scoring
- Event-driven substance tracking (applied knowledge philosophy)
- Custom search with facets, tags, semantic intent

**LS is the smallest** because steps are simple:
- Only 3 sub-services: core, relationships, search
- Simple aggregation of KUs into ordered steps
- No dedicated intelligence (uses LP parent)

### Backend Pattern

Curriculum Domains use `UniversalNeo4jBackend[T]` directly (January 2026 - wrappers deleted):

| Domain | Backend | Relationship Service |
|--------|---------|---------------------|
| KU | `UniversalNeo4jBackend[Ku]` | `self.relationships` (UnifiedRelationshipService) |
| LS | `UniversalNeo4jBackend[Ls]` | `self.relationships` (UnifiedRelationshipService) |
| LP | `UniversalNeo4jBackend[Lp]` | `self.relationships` (UnifiedRelationshipService) |
| MOC | No backend (KU-based) | Uses KuService for all operations |

**Note (January 2026):** MOC no longer has its own backend or model. MOC IS a KU with ORGANIZES relationships. The `MocUniversalBackend` was deleted along with the `MapOfContent` model.

### Search via BaseService (Unified Pattern)

LS and LP search services inherit from `BaseService`, providing unified search infrastructure automatically:

```python
class LsSearchService(BaseService["BackendOperations[Ls]", Ls]):
    _search_fields = ["title", "intent", "description"]
    _user_ownership_relationship = None  # Shared content
```

**Inherited methods:** `search()`, `get_by_status()`, `get_by_domain()`, `graph_aware_faceted_search()`, `get_prerequisites()`, `get_enables()`, `get_user_progress()`

### Shared Content Model

Curriculum Domains use `_user_ownership_relationship = None`:
- Content is shared (no per-user OWNS relationship)
- Same KU, LS, LP available to all users
- User progress tracked separately via LEARNING, MASTERED relationships

**See:** `/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md` § "Curriculum Domain Service Architecture"

---

## Design Principles

1. **Organic First, Type Safety Second**
   - Patterns emerged from natural knowledge organization
   - Type safety was applied to channel energy, not restrict it

2. **Same Content, Different Views**
   - A KU can appear in multiple LSs, LPs, and MOCs
   - The patterns are views, not containers

3. **Synergy Through Typed Relationships**
   - Energy flows through defined relationship types
   - Feedback loops enable system-wide intelligence

4. **User-Authored Understanding**
   - MOCs capture relationships only the user knows
   - The system amplifies user insight, doesn't replace it

5. **Markdown as Source of Truth**
   - All patterns defined in human-readable markdown
   - Graph relationships derived from YAML frontmatter
   - Neo4j is the query layer, markdown is the authoring layer
