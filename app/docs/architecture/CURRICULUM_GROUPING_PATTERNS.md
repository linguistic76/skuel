---
title: "Curriculum Grouping Patterns: KU, PS, LP + MOC Organization"
updated: 2026-03-03
status: current
category: architecture
tags: [architecture, curriculum, grouping, patterns, moc, montessori]
related: [ADR-023-curriculum-baseservice-migration, ADR-028-ku-moc-unified-relationship-migration]
related_skills: [curriculum-domains]
---

# Curriculum Grouping Patterns: KU, PS, LP + MOC Organization

*Last updated: 2026-04-02*
## Related Skills

For implementation guidance, see:
- [@curriculum-domains](../../.claude/skills/curriculum-domains/SKILL.md)


## Core Philosophy

SKUEL organizes knowledge through **three grouping patterns** and **two access paths**. The patterns (KU, PS, LP) are different perspectives on the same underlying content. The access paths (PS linear, MOC graph) provide different ways to navigate that content.

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

| Pattern | UID Format | Grouping Style | Topology | Metaphor |
|---------|------------|----------------|----------|----------|
| **KU** | `ku_{slug}_{random}` | Atomic unit | Point | A single concept/fact |
| **PS** | `ps:{random}` | Unit for learning | Unit | A step that composes Kus into content |
| **LP** | `lp:{random}` | Linear sequence | Path | An ordered sequence of PathSteps |

**Note:** MOC uses the `ku_{slug}_{random}` format since MOC IS a Ku with ORGANIZES relationships — no separate UID prefix needed.

### Two Paths to Knowledge (Montessori-Inspired)

| Path | Topology | Purpose | Pedagogy |
|------|----------|---------|----------|
| **PS Path** | Linear | Structured curriculum | Teacher-directed |
| **MOC Path** | Graph | Free exploration | Learner-directed |

```
PS Path (Structured):              MOC Path (Exploratory):
                                        KU (root MOC)
LP₁    LP₂    LP₃ (paths)             /    |    \
/|\    /|\    /|\                   KU    KU    KU (topics/sections)
PS PS PS PS PS PS (steps)          / \         / \
|  |  |  |  |  |                 KU  KU     KU   KU (content)
KU KU KU KU KU KU (content)

Sequential "Learn A then B"      Non-linear "Explore what interests you"
```

**Key Insight:** The same KU can appear in multiple PS, LP, and MOC contexts. Progress is tracked on the KU itself, unified across both paths.

---

## Pattern Details

### KU (Knowledge Unit) - The Atomic Unit

**What it is:** The smallest indivisible piece of knowledge content.

**Python Class:** `Ku(Curriculum)` — the concrete leaf class for atomic knowledge units.
`Curriculum` is the shared base class; `Ku`, `PathStep`, `LearningPath`, and `Exercise` are the leaf types.

**Location:** `/core/models/ku/ku.py`

**EntityType:** `EntityType.KU = "ku"` — stored as `entity_type` property in Neo4j.

**Neo4j Labels:** `:Entity:Ku {entity_type: 'ku'}` (dual-label pattern, February 2026)

**Characteristics:**
- Self-contained markdown content
- Has a domain (TECH, HEALTH, etc.)
- Can exist independently
- Referenced by all other patterns

**Example:**
```yaml
uid: ku_python-functions_a1b2c3
title: Python Functions
domain: tech
content: |
  A function is a reusable block of code...
```

**Graph Role:** KU is the leaf node - all other patterns ultimately reference KUs.

---

### PS (Path Step) - The Curriculum Content Entity

**What it is:** A unit for learning that composes Kus into coherent content and sits within LearningPaths.

**Note (2026-04):** The former `Lesson` entity type was merged into `PathStep`. PathStep IS the curriculum content entity. `"lesson"` and `"l"` are backward-compatible aliases in `_ENTITY_TYPE_ALIASES`.

**Characteristics:**
- Composes atomic Kus into a coherent learning narrative
- Has a specific order within a path
- Can require mastery threshold
- May include practice activities

**Example:**
```yaml
uid: ps:abc123
title: Understanding Functions
order: 3
kus:
  - ku_python-functions_a1b2c3
  - ku_python-parameters_d4e5f6
mastery_threshold: 0.8
```

**Graph Role:** PS is the unit — composing Kus into learning content within an LP sequence.

---

### LP (Learning Path) - The Linear Sequence

**What it is:** A complete learning journey from start to finish.

**Characteristics:**
- Ordered sequence of Path Steps
- Has prerequisites and outcomes
- Represents a full competency arc
- Linear progression (Step 1 → 2 → 3 → Done)

**Example:**
```yaml
uid: lp:abc123
title: Python for Beginners
steps:
  - ls:def456
  - ls:ghi789
  - ls:jkl012
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
- Progress tracked on KU, unified across both PS and MOC paths

**Example:**
```cypher
// A Ku acting as a MOC root
(:Entity:Ku {uid: "ku_python-fundamentals_abc123", title: "Python Fundamentals"})

// Organizing other Kus (making it a MOC)
(root:Entity {uid: "ku_python-fundamentals_abc123"})-[:ORGANIZES {order: 1}]->(section:Entity {uid: "ku_python-basics_def456"})
(root)-[:ORGANIZES {order: 2}]->(section2:Entity {uid: "ku_python-advanced_ghi789"})

// Sections organizing child Kus
(section:Entity {uid: "ku_python-basics_def456"})-[:ORGANIZES {order: 1}]->(child:Entity {uid: "ku_python-functions_a1b2c3"})
(section)-[:ORGANIZES {order: 2}]->(child2:Entity {uid: "ku_python-classes_d4e5f6"})
```

**Graph Role:** MOC provides non-linear navigation by organizing KUs into a graph structure parallel to the linear PS/LP structure.

---

## How the Patterns Relate

### The Curriculum Hierarchy (PS Path)

```
KU → PS → LP
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
   │  PS PATH          MOC PATH       │
   │  (Linear)         (Graph)        │
   │                                  │
   │  LP──>LP──>LP     KU (root MOC)  │
   │  |    |    |      /  |  \        │
   │  PS   PS   PS   KU  KU  KU       │
   │  |    |    |    |       |        │
   │  KU   KU   KU   KU      KU       │
   │                                  │
   │  Same KUs, same progress!        │
   └──────────────────────────────────┘
              ↑
        RAW CONTENT (KUs)
```

**Progress Tracked on KU:**
- Whether accessed via PS or MOC path, mastery is tracked on the KU itself
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
KU ──────→ PS ──────→ LP
 ↑          ↑          ↑
 └────← MOC ←─────────┘  (energy feeds back - synergy)
```

Type safety **channels** the relationships so energy (user effort, system computation, semantic meaning) flows through defined paths and feeds back into the system.

### The EntityType Enum

```python
from core.models.enums.entity_enums import EntityType

class EntityType(str, Enum):
    # Atomic knowledge unit
    KU = "ku"
    # MOC is NOT a separate EntityType — any Ku can organize others via ORGANIZES

    # Curriculum structure
    PATH_STEP = "path_step"
    LEARNING_PATH = "learning_path"
    # ... plus 12 more (activity domains, content processing, destination)
```

Curriculum patterns are EntityType values alongside activity domains. The grouping patterns (`KU`, `PATH_STEP`, `LEARNING_PATH`) form the shared knowledge organization system. MOC is not a separate EntityType — any Ku can organize others via ORGANIZES relationships (emergent identity).

**Domain Classification:**
- **Atomic knowledge:** `EntityType.KU` (any Ku can be an organizer via ORGANIZES)
- **Curriculum structure:** `EntityType.PATH_STEP`, `EntityType.LEARNING_PATH`

### Relationship Types

Type-safe relationships between patterns:

```python
# PS Path (Linear)
HAS_STEP           # LP → PS
USES_KU            # PS → KU (primary/supporting content)

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
2. **Organize into LSs** - Group related KUs into path steps
3. **Sequence into LPs** - Create learning journeys from steps
4. **Map with MOCs** - Author non-linear navigation for discovery

### Ingesting from Markdown

All patterns can be defined in markdown with YAML frontmatter and ingested via `UnifiedIngestionService`:

**KU:**
```yaml
---
uid: ku_python-functions_a1b2c3
title: Python Functions
domain: tech
---
# Content here
```

**MOC (a Ku with children defined in YAML):**
```yaml
---
uid: ku_python-overview_abc123
title: Python Overview
organizes:
  - ku_python-functions_a1b2c3
  - ku_python-classes_d4e5f6
---
# Overview here
```

The `UnifiedIngestionService` (at `core/services/ingestion/`) handles all curriculum entity types.

**See:** `/docs/patterns/UNIFIED_INGESTION_GUIDE.md`

---

## Key Files

| Component | File | Purpose |
|-----------|------|---------|
| Ku Model | `/core/models/ku/ku.py` | Ku leaf class (`Ku(Entity)`) |
| PS Model | `/core/models/pathways/path_step.py` | Path Step definition |
| LP Model | `/core/models/pathways/learning_path.py` | Learning Path definition |
| Curriculum Base | `/core/models/curriculum.py` | Shared base class for Ku, PS, LP |
| KuService | `/core/services/ku_service.py` | Ku facade (CRUD, graph, semantics, organization) |
| KuOrganizationService | `/core/services/ku/ku_organization_service.py` | ORGANIZES relationship management (MOC) |
| KuIntelligenceService | `/core/services/ku_intelligence_service.py` | Standalone analytics for KU domain |
| PsService | `/core/services/ps_service.py` | Path Step facade |
| LpService | `/core/services/lp_service.py` | Learning Path facade |
| LpBackend | `/adapters/persistence/neo4j/backends/curriculum_backends.py` | LP-specific graph queries |
| KuBackend | `/adapters/persistence/neo4j/backends/curriculum_backends.py` | Ku ORGANIZES operations |
| EntityType | `/core/models/enums/entity_enums.py` | Type-safe entity identification |
| Ingestion | `/core/services/ingestion/` | Ingest all patterns from markdown |
| Unified Registry | `/core/models/relationship_registry.py` | All domain relationship configs |

**Note (March 2026):** Curriculum models decomposed from `/core/models/curriculum/` into domain-specific directories: `/core/models/exercises/`, `/core/models/pathways/`, `/core/models/lesson_content/`, and `/core/models/ku/`. Base classes in `/core/models/curriculum.py` and `/core/models/curriculum_dto.py`. MOC has no separate model or service; it is handled by `KuOrganizationService`.

**Note (April 2026):** `Lesson` entity type merged into `PathStep`. The `core/models/lesson/` directory is gone; PathStep at `/core/models/pathways/path_step.py` IS the curriculum content entity.

---

## Service Architecture (January 2026)

Each Curriculum Domain follows the **decomposed facade pattern** with complexity appropriately sized to its needs.

### Service Comparison

| Domain | Service | Sub-Services (dedicated) | Intelligence |
|--------|---------|--------------------------|--------------|
| **KU** | `KuService` | 4 in `ku/` package: Core, Search, Relationships, Intelligence | `KuIntelligenceService` (standalone at `ku_intelligence_service.py`) |
| **LP** | `LpService` | 4 in `lp/` package: Core, Search, Progress, AI | `LpIntelligenceService` (standalone at `lp_intelligence_service.py`) |
| **PS** | `PsService` | 10+ in `ps/` package: Core, Search, Intelligence, Mastery, Organization, Graph, Context, Semantic, Practice, AI | `PsIntelligenceService` (in `ps/` package) |

**MOC (January 2026 - KU-Based):** There is no `MOCService`. MOC is handled by `KuOrganizationService` (sub-service of KuService). A Ku "is a MOC" when it has outgoing ORGANIZES relationships — emergent identity, not a separate service or EntityType.

### Why Different Sizes?

**KU is the largest** because semantic knowledge management is inherently complex:
- 9 dedicated sub-services: CRUD, search, semantics, graph, practice, interaction, organization, AI, adaptive
- Semantic relationship management with confidence scoring
- Event-driven substance tracking (applied knowledge philosophy)
- ORGANIZES relationship operations (MOC) via `KuOrganizationService`

**PS is leaner** because steps aggregate Kus into ordered sequences:
- 4 sub-services: core, search, intelligence, AI
- Simple aggregation of Kus into ordered steps

### Backend Pattern

Curriculum Domains use domain backend subclasses where relationship-specific Cypher is needed (March 2026):

| Domain | Backend | Domain-specific methods | Architecture |
|--------|---------|------------------------|--------------|
| KU | `KuBackend` (extends `UniversalNeo4jBackend[Ku]`) | 23 methods: ORGANIZES, namespace/alias search, substance, relationships, prereqs, learning state | Flat (appropriate for atomic domain) |
| PS | `PsBackend` (extends `UniversalNeo4jBackend[PathStep]`) | 71+ methods via 5 mixins: organizes, learning state, semantic, knowledge context, adaptive + 4 search queries | 5 domain-specific mixins |
| LP | `LpBackend` (extends `UniversalNeo4jBackend[LearningPath]`) | 28 methods via 3 mixins: step CRUD (14), progress + search (6), intelligence + adaptive (8) | 3 domain-specific mixins |
| Exercise | `ExerciseBackend` (extends `UniversalNeo4jBackend[Exercise]`) | `link_to_curriculum`, `unlink_from_curriculum`, `get_required_knowledge` | Flat |

Ku/Ps/Lp backends in: `/adapters/persistence/neo4j/backends/curriculum_backends.py`
Exercise/RevisedExercise/EntryReport backends in: `/adapters/persistence/neo4j/backends/exercise_backends.py`
LP mixins in: `_lp_step_mixin.py`, `_lp_progress_mixin.py`, `_lp_intelligence_mixin.py`
PS mixins in: `_organizes_mixin.py`, `_learning_state_mixin.py`, `_semantic_mixin.py`, `_knowledge_context_mixin.py`, `_adaptive_mixin.py`

**See:** CLAUDE.md § "100% Dynamic Backend Pattern"

### Search via BaseService (Unified Pattern)

PS and LP search services inherit from `BaseService`, providing unified search infrastructure automatically:

```python
class PsSearchService(BaseService["PsOperations", PathStep]):
    _config = create_curriculum_domain_config(
        dto_class=PathStepDTO,
        model_class=PathStep,
        domain_name="ps",
        search_fields=("title", "description"),
        category_field="domain",
    )
```

**Inherited methods:** `search()`, `get_by_status()`, `get_by_category()`, `get_prerequisites()`, `get_enables()`, `verify_ownership()`

### Shared Content Model

Curriculum Domains use `_user_ownership_relationship = None`:
- Content is shared (no per-user OWNS relationship)
- Same KU, PS, LP available to all users
- User progress tracked separately via LEARNING, MASTERED relationships

**See:** `/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md` § "Curriculum Domain Service Architecture"

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
