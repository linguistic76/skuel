---
title: "Curriculum Grouping Patterns: KU, PS, LP + MOC Organization"
updated: 2026-08-14
status: current
category: architecture
tags: [architecture, curriculum, grouping, patterns, moc, montessori]
related: [ADR-023-curriculum-baseservice-migration, ADR-028-ku-moc-unified-relationship-migration]
related_skills: [curriculum-domains]
---

# Curriculum Grouping Patterns: KU, PS, LP + MOC Organization

*Last updated: 2026-08-14*
## Related Skills

For implementation guidance, see:
- [@curriculum-domains](../../.claude/skills/curriculum-domains/SKILL.md)


## Core Philosophy

> **PathStep IS knowledge. Exercise is APPLIED knowledge. This hierarchy is fundamental.**

SKUEL organizes knowledge through **four curriculum EntityTypes** that form a hierarchy,
not a flat peer group. Three of these are grouping/structure patterns (Ku, PathStep,
LearningPath); one is an applied-knowledge anchor (Exercise).

| EntityType | Role | Hierarchy |
|---|---|---|
| Ku | Atomic knowledge unit | Foundation |
| PathStep | Composed knowledge | Built on Kus — the teachable unit |
| LearningPath | Organisational structure | Sequences PathSteps |
| Exercise | Applied knowledge | Anchored below PathStep via `HAS_EXERCISE` |

Exercise is NOT a fourth structural pattern alongside LP. It is subordinate to PathStep —
the instruction template that operationalises PathStep content into concrete practice. A
PathStep without an Exercise is knowledge waiting to be applied. An Exercise without a
PathStep is an orphan: the learning loop cannot close for it.

The three **grouping patterns** (Ku, PS, LP) and **two access paths** below describe
the structural/navigational side of curriculum. Exercise is covered separately at the end.

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

| Pattern | UID (authored = stored) | Grouping Style | Topology | Metaphor |
|---------|------------|----------------|----------|----------|
| **KU** | `ku.{ns}.{slug}` (API-generated: `ku_{slug}_{random}`) | Atomic unit | Point | A single concept/fact |
| **PS** | `ps.{namespace}.{slug}` | Unit for learning | Unit | A step that composes Kus into content |
| **LP** | `lp.{namespace}.{slug}` | Linear sequence | Path | An ordered sequence of PathSteps |

**Note:** MOC uses whatever UID form its Ku carries, since MOC IS a Ku with ORGANIZES relationships — no separate UID prefix needed.

### Authoring Spelling: Dots (colons retired 2026-08-14)

Vault files author curriculum UIDs in **dot form directly** (`ps.mindfulness.breath-awareness-basics`)
— what you author is exactly what the graph stores. The former colon authoring spelling
(`ps:mindfulness:…`) was retired by ruling on 2026-08-14, and the whole content vault was swept
to dots in the same pass (572 rewrites across 265 files; identity unchanged, since both spellings
resolved to the same stored UID).

**The colon input alias was DELETED (ruled by Mike 2026-08-14, strict One Path).**
`normalize_uid()` — the boundary shim that rewrote `:` → `.` on entity `uid:`, rel-config UID
fields, and Edge-YAML `from`/`to` — is gone: a colon-spelled entity uid now fails prefix
validation **loudly** instead of being silently rewritten. Authored input is stored verbatim.
This retires the colon as an *entity-UID spelling only*; deliberately-colon **internal machine
identifiers** are untouched and now own the character outright (see the grammar table's colon
row below): periodic UserEntry UIDs (`ue:daily:{user_uid}:{date}`), the `edge:` tracker-row
sentinel, and `transcription:`/`invoice:` mints.

Consequences:
- File UID and graph UID compare **directly** — no mental translation, no normalization step
  anywhere.
- Stored UIDs are NOT being migrated to flat `{prefix}_{slug}_{random}` — the graph holds dotted
  authored curriculum UIDs; the flat form activates only for API-created entities. Both forms
  stay sanctioned; see the never-sniff rule below.

### Separator Grammar (ratified 2026-08-14)

One character, one job. This is the whole separator law — anything a doc or code comment says
beyond this table is historical:

| Character | Role |
|-----------|------|
| `-` hyphen | Joins words **within** a single segment (`active-listening`). The only word-joiner, everywhere — `UIDGenerator.slugify()` emits it, and folds input underscores into it (`active_listening` → `active-listening`). Author hyphens. |
| `.` dot | Segment separator of **authored** UIDs — authored and stored identically. Shape: `{prefix}.{grouping-label}.{slug}`. (The `:` colon authoring spelling was retired 2026-08-14 and its input alias deleted — a colon-spelled entity uid is rejected loudly. The DSL's `@link(type:id)` argument colon is tag syntax, not a UID spelling.) |
| `_` underscore | Segment separator of **generated** UIDs (`{prefix}_{slug}_{random}`, `{prefix}_{random}`), and the conventional filename type-prefix (`ku_attention.md`). |
| `:` colon | **Internal machine identifier, never an entity UID** (ratified 2026-08-14): periodic UserEntry UIDs (`ue:daily:{user}:{date}` — the calendar routes' join contract), the `edge:` tracker-row sentinel (`ingestion_write_backend.py`), and `transcription:`/`invoice:` mints. The disjoint spelling is what makes these collision-proof against entity UIDs — do NOT unify them into underscore form (`ue_daily_…` would masquerade as a generated entity uid while carrying parsed segments, and the `edge:` sentinel's exclusion query depends on distinctness). |
| *(edges)* | Family. Parent/child/lineage lives **only** in graph relationships (`ORGANIZES`, `USES_KU`, `HAS_STEP`, …) — never in UID strings. |

Two clarifications the grammar hangs on:

- **The middle segment of an authored UID is a human-readable grouping *hint*, not machine
  hierarchy.** `ku.mindfulness.attention` tells a human editor which family the author had in
  mind; the system never parses it (see the never-sniff rule below). Knowledge is a graph —
  one Ku belongs to many families at once, which no string can encode. Hierarchy-in-edges is
  what makes multiple parents possible.
- **Separator spelling is provenance** — dot says "authored/curated", underscore says
  "API-generated". It carries no type information and no behavior.

**Supersession note:** the January 2026 migration plan
(`/docs/migrations/UID_STANDARDIZATION_MIGRATION_2026-01-30.md`) assigned dots the job of
encoding hierarchy ("Rule 2: Dot for Hierarchical Curriculum Entities"). That rule was
superseded by ADR-013 — hierarchy is never encoded in UIDs — and the demotion of the dot to
a provenance marker with a human-readable hint was ratified 2026-08-14. The dated migration
log itself stays as history.

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

#### Two Sanctioned UID Forms — the Never-Sniff Rule

Both KU UID spellings are sanctioned (ADR-013, explicit `uid:` override; ruling
reaffirmed 2026-07-03):

| Form | Format | Provenance |
|------|--------|------------|
| Authored | `ku.{namespace}.{slug}` | Vault/editorial — validator-enforced (`core/services/ingestion/validator.py` requires `"{prefix}."`); authored in dot form directly (colon spelling retired 2026-08-14, its `normalize_uid` input shim deleted with it — a colon-spelled entity uid now fails prefix validation loudly, per § Authoring Spelling) |
| Generated | `ku_{slug}_{random}` | API — the Universal flat format shared with all Activity domains |

**No migration between them, ever.** UID spelling is provenance (curated vs
generated), not type information. **Entity kind is determined by label,
`entity_type`, or edge — NEVER by UID string prefix.** A `startswith("ku_")`
check silently drops every authored KU (and vice versa); consumers that need
to split mixed UID lists take the `entity_type` field the MEGA-QUERY carries
on `knowledge_relationships`, or resolve by lookup.

**Lint-enforced since 2026-08-30 (SKUEL034, ERROR).** The rule was prose-only until a real
violation lived from the initial commit to 2026-08-27: `_get_knowledge_domain` grouped
masteries by `"tech" in knowledge_uid.lower()`, inventing a Domain no entity carries (#1170).
SKUEL034 flags the shape that has no legitimate form — a string-literal membership test
against a singular uid (`"lit" in uid`, `not in`, and through `.lower()`-style unwraps).
Membership in a *collection* of uids (`"ku.a.b" in ku_uids`) is ordinary and is not flagged.

Prefix and segment reads are **deliberately out of the rule's scope**, because their
legitimacy depends on what the branch does with the answer. All four live sites are
sanctioned, and each says so in its own docstring:

| Site | Why it is not sniffing |
|------|------------------------|
| `parse_calendar_item_uid` (`core/models/event/calendar_models.py`) | Parses a composite **wire format the app itself mints** (`task-{uid}`), not an entity uid |
| `_extract_label_from_uid` (`adapters/persistence/neo4j/_relationship_crud_mixin.py`) | Performance fast path only; an unknown shape returns `None` and **falls back to the DB label**, so it is never a wrong answer |
| `_table_domain` + its caller (`core/services/entity_inference_service.py`) | The keys are **hardcoded inference-table literals** authored beside their keywords, never stored uids |

The distinction the table draws is the one to apply to any new site: reading your own minted
format, or a literal you wrote, is not sniffing. Deriving an entity's kind from a uid that
came out of the graph is.

---

### PS (Path Step) - The Curriculum Content Entity

**What it is:** A unit for learning that composes Kus into coherent content and sits within LearningPaths.

**Note (2026-04):** The former `Lesson` entity type was merged into `PathStep`. PathStep IS the curriculum content entity. `"lesson"` is accepted by the ingestion detector (`TYPE_MAPPING` in `detector.py`); use `"ps"` or `"pathstep"` for DSL/`from_string()` parsing.

**Characteristics:**
- Composes atomic Kus into a coherent learning narrative
- Has a specific order within a path
- Can require mastery threshold
- May include practice activities

**Example (authored = stored):**
```yaml
uid: ps.python.understanding-functions
title: Understanding Functions
order: 3
kus:
  - ku.python.functions
  - ku.python.parameters
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

**Example (authored = stored):**
```yaml
uid: lp.python.beginners
title: Python for Beginners
connections:
  contains_steps:
    - ps.python.understanding-functions
    - ps.python.control-flow
    - ps.python.first-program
prerequisites: []
outcomes:
  - "Write basic Python programs"
  - "Understand functions and control flow"
```

**Graph Role:** LP is the path - a traversable sequence with a beginning and end.

---

### Exercise — Applied Knowledge (Anchored to PathStep)

**What it is:** The instruction template that operationalises PathStep content into
concrete practice. Exercise is NOT a structural pattern like LP — it is applied knowledge
subordinate to PathStep in the hierarchy.

**The hierarchy relationship:**

```
(PathStep)-[:HAS_EXERCISE]->(Exercise)
```

PathStep and Exercise are NOT peers. Exercise is anchored below PathStep in the same
structural relationship as a sub-goal under a parent goal. This is why:

- `Exercise.path_step_uid` is a persisted **hierarchy-membership property** — not a
  scoring or enrichment field. It identifies which knowledge unit this instruction belongs
  to, and is written at creation time alongside the `HAS_EXERCISE` edge (dual-write).
- `EntityType.EXERCISE.is_applied_knowledge()` returns `True`.
- `EntityType.EXERCISE.is_curriculum_structure()` returns `False` — Exercise is not
  organisational structure.

**Why Exercise inherits from Curriculum:**

Exercise shares substance tracking, learning metadata, and confidence fields with PathStep
and LearningPath — that is the only reason they share the `Curriculum` base class. Shared
base class does not mean structural peers.

**One Exercise per PathStep (PERSONAL scope):**

A PERSONAL-scope Exercise belongs to exactly one PathStep. This is the canonical loop
anchor. ASSIGNED-scope Exercises (teacher → group) omit `path_step_uid` and use a
`group_uid` instead.

**Graph Role:** Exercise is the applied-knowledge anchor — the bridge between curriculum
knowledge (PathStep) and user practice (UserEntry → EntryReport → RevisedExercise).

**See:** `/docs/architecture/CROSS_DOMAIN_UID_PATTERNS.md` — the canonical reference for the structural anchor vs enrichment link rule across all entity types (Curriculum and Activity Domains).

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

**July 2026 - Vault authoring surface (`moc: true`) + any-Entity MOCs:**
The ORGANIZES Path gained its authoring surface: `moc: true` in the
frontmatter of ANY ingestible vault file turns the file's body links
(wiki + markdown) into `ORGANIZES {order}` edges to link targets that
resolve to ingested entities (order = document position; edits re-draw on
next sync). The identity rule generalizes beyond Ku: any Entity with
outgoing ORGANIZES edges is a MOC — e.g. a personal-vault UserEntry
knowledge map. Identity stays emergent; the `moc` field itself is inert
(nothing queries it). Dangling links are plans (skipped silently) in
personal vaults; the content vault keeps strict warnings.
**See:** `/docs/patterns/UNIFIED_INGESTION_GUIDE.md` § MOC files.

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
| KU | `KuBackend` (extends `UniversalNeo4jBackend[Ku]`) | 22 methods: ORGANIZES, alias search, substance, relationships, prereqs, learning state | Flat (appropriate for atomic domain) |
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
