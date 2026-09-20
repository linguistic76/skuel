---
title: MOC (Map of Content) - Emergent Organization via ORGANIZES
created: 2025-12-04
updated: 2026-09-20
status: current
category: domains
tags:
- moc
- map-of-content
- organizational-domain
- organizes
- montessori
related_skills:
- curriculum-domains
---

# MOC (Map of Content) — Emergent Organization

**Type:** Organizational pattern (not an `EntityType`)
**Identity:** Any Entity with outgoing `ORGANIZES` relationships
**Topology:** Graph (non-linear navigation)

## Emergent Identity

**MOC is NOT a separate entity — it IS whichever entity organizes.**

An entity "is" a MOC when it has outgoing `ORGANIZES` relationships to other entities. No flag is stored: the backend reads the edge (`is_organizer`) and nothing else defines the identity. The organizer is usually a PathStep or a Ku; in a personal vault it can be a UserEntry knowledge map (see [Authoring a MOC from the vault](#authoring-a-moc-from-the-vault)).

## Two Paths to Knowledge (Montessori-Inspired)

**Skill:** [@curriculum-domains](../../.claude/skills/curriculum-domains/SKILL.md)

SKUEL provides two fundamental ways to reach curriculum content:

| Path | Topology | Purpose | Pedagogy |
|------|----------|---------|----------|
| **PS / LP** | Linear | Structured curriculum | Teacher-directed |
| **MOC (ORGANIZES)** | Graph | Free exploration | Learner-directed |

Same entity, two access paths. Learning state is an edge from the user to the entity, so it reads the same whichever path reached it.

```
PS Path (Structured):              MOC Path (Exploratory):
PS → PS → PS → PS                      PS (root MOC)
Sequential learning                   /    |    \
"Learn this, then this"            PS    PS    PS (topics)
                                  / \         / \
                                PS  Ku     PS   Ku
                                Non-linear, browse freely
                                "Explore what interests you"
```

## Key Concepts

| Concept | Definition |
|---------|------------|
| MOC | An entity that organizes other entities via `ORGANIZES` relationships |
| Section | An organized child that itself organizes children (nested MOC) |
| ORGANIZES | Relationship type: `(parent:Entity)-[:ORGANIZES {order: int}]->(child:Entity)` |
| Root MOC | An entity that organizes others but is not itself organized |

## Service Architecture

ORGANIZES operations are the `organization` slot of the PathStep facade — `PsService.organization` is a `PsOrganizationService` (`core/services/ps/ps_organization_service.py`), and the facade delegates every method. The backend is `_OrganizesMixin` (`adapters/persistence/neo4j/_organizes_mixin.py`), mixed into `PsBackend` and `UserEntryBackend`; its statements match `:Entity` by uid. The service narrows that for the unauthenticated PathStep door: every read (`is_organizer`, `get_organization_view`, `get_navigation`, `find_organizers`, `get_organized_children`) and the **create** `organize()` resolve their subject through `ps_core.get()`, which matches `:PathStep`, and answer not-found for any other entity; and the other end of a read — organizers, children, roots — is scoped to `SHARED_CURRICULUM_TYPES` on the query (`list_root_organizers` carries the scope on every call, being the one unanchored read). The facade and the API therefore create PathStep → PathStep edges only and never return a user-owned entity. `unorganize()` and `reorder()` go straight to the mixin and act on any existing `ORGANIZES` edge, including a vault-authored PathStep → Ku edge. Cross-entity edges — a PathStep organizing a Ku, a UserEntry knowledge map — are authored in the vault and written by ingestion on `:Entity`: `moc: true` body links through `IngestionWriteBackend.refresh_moc_organizes` (any ingestible file), or an `organizes:` frontmatter list through the relationship-registry edge writer (a **PathStep** field — `generate_ingestion_relationship_config` emits `organizes` for `EntityType.PATH_STEP` only; a Ku or UserEntry authors through `moc: true`).

```python
ps_service = services.ps  # PsService

# Identity — does this entity organize anything?
is_moc = await ps_service.is_organizer("ps.core.python-reference")

# The organizer with its organized children, depth-limited — PathStep roots only
view = await ps_service.get_organization_view("ps.core.python-reference", max_depth=3)

# Create — both uids must be PathSteps (a Ku or UserEntry uid is not found)
await ps_service.organize("ps.core.python-reference", "ps.core.python-basics", order=1)
# Reorder / remove — any existing edge, whatever the child's entity type
await ps_service.reorder("ps.core.python-reference", "ku.sel.empathy", new_order=2)
await ps_service.unorganize("ps.core.python-reference", "ku.sel.empathy")

# Navigate
parents = await ps_service.find_organizers("ps.core.python-basics")
children = await ps_service.get_organized_children("ps.core.python-reference")
roots = await ps_service.list_root_organizers(limit=50)
nav = await ps_service.get_navigation("ps.core.python-basics")  # StepNavigation — siblings under the first curriculum organizer
```

## Key Files

| Component | Location |
|-----------|----------|
| Facade | `/core/services/ps_service.py` (§ ORGANIZATION delegation) |
| Organization Service | `/core/services/ps/ps_organization_service.py` |
| Backend mixin | `/adapters/persistence/neo4j/_organizes_mixin.py` (`_OrganizesMixin` — on `PsBackend` and `UserEntryBackend`) |
| Backend protocol | `PsOrganizesBackendOperations` in `/core/ports/curriculum_protocols.py` |
| Relationship Config | `ORGANIZES` in `/core/models/relationship_registry.py` — `PS_CONFIG.relationships` (ingestible as `organizes:`, target `Entity`); `KU_CONFIG.bidirectional_relationships` (read-side only) |
| API Routes | `/adapters/inbound/path_steps_api.py` § ORGANIZES HIERARCHY |
| Vault authoring | `/core/services/ingestion/moc_links.py` (`moc: true` body links, any ingestible file) → `IngestionWriteBackend.refresh_moc_organizes` in `/adapters/persistence/neo4j/ingestion_write_backend.py`; `organizes:` frontmatter (PathStep files) → the relationship-registry edge writer. Ingestion is where cross-entity `ORGANIZES` edges come from |

## ORGANIZES Relationship

The backend's own statements — every match is on `:Entity`, never on a domain label:

```cypher
// Organize (MERGE — idempotent; re-running re-sets the order)
MATCH (parent:Entity {uid: $parent_uid})
MATCH (child:Entity {uid: $child_uid})
MERGE (parent)-[r:ORGANIZES]->(child)
SET r.order = $order

// Is this entity an organizer?
MATCH (n:Entity {uid: $entity_uid})
OPTIONAL MATCH (n)-[:ORGANIZES]->(child:Entity)
RETURN n IS NOT NULL AS entity_exists, count(child) > 0 AS is_organizer

// Direct organized children, in order
MATCH (parent:Entity {uid: $parent_uid})-[r:ORGANIZES]->(child:Entity)
RETURN child.uid, child.title, r.order
ORDER BY r.order ASC
```

## Example MOC Structure

A vault-authored map (the PathStep → Ku edges below come from `moc: true` body links; the API writes PathStep → PathStep only):

```
PS: "Python Reference" (root MOC)
├── ORGANIZES(order=1) → PS: "Fundamentals"
│   ├── ORGANIZES(order=1) → Ku: "python-basics"
│   ├── ORGANIZES(order=2) → Ku: "python-syntax"
│   └── ORGANIZES(order=3) → PS: "Data Types" (nested section)
│       ├── ORGANIZES(order=1) → Ku: "python-strings"
│       └── ORGANIZES(order=2) → Ku: "python-lists"
├── ORGANIZES(order=2) → PS: "Advanced"
│   ├── ORGANIZES(order=1) → Ku: "python-async"
│   └── ORGANIZES(order=2) → Ku: "python-decorators"
└── ORGANIZES(order=3) → Ku: "python-best-practices"
```

## API Endpoints

All in `adapters/inbound/path_steps_api.py`. The three writes are admin-only and CSRF-protected. The reads carry no authentication — curriculum is shared content — and two guards in `PsOrganizationService` keep a user-owned entity out of them, because the `ORGANIZES` edge joins any two entities and a personal-vault `moc: true` map organizes PathSteps too: the **subject** of every read resolves through `ps_core.get()` (a `:PathStep` match; a UserEntry or Ku uid is not-found), and the **other end** — organizers, children, roots — is scoped to `SHARED_CURRICULUM_TYPES` (every `ContentOrigin.CURRICULUM` entity type, derived from the enum) on the backend query. So `organizers` on a PathStep does not return the private note that links to it, and `root-organizers` never lists one. The private map keeps its owner-verified read on `/gradebook/{uid}`, where `UserEntryBackend` reaches the same mixin without the scope. Pinned by `tests/integration/test_organizes_reads_curriculum_scope.py`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/path-steps/{uid}/is-organizer` | GET | Does this entity organize anything? |
| `/api/path-steps/{uid}/organization` | GET | The organizer with its organized-children hierarchy (PathStep roots only) |
| `/api/path-steps/{uid}/organizers` | GET | Parents that organize this entity |
| `/api/path-steps/{uid}/organized-children` | GET | Direct organized children, in order |
| `/api/path-steps/root-organizers?limit=50` | GET | Root MOCs (organize others, organized by nothing) |
| `/api/path-steps/organize` | POST | Create an `ORGANIZES` edge between two PathSteps (`StepOrganizeRequest`: `parent_uid`, `child_uid`, `order`) — admin |
| `/api/path-steps/unorganize` | POST | Remove an existing `ORGANIZES` edge, any entity types — admin |
| `/api/path-steps/reorder` | POST | Change a child's order on an existing edge, any entity types (`StepReorderRequest`: `parent_uid`, `child_uid`, `new_order`) — admin |

There is no MOC-specific create door: organizers and children are ordinary entities, created through vault ingestion or their own domain's API. An edge whose parent or child is not a PathStep is *created* in the vault, never through `organize`; once it exists, `reorder` and `unorganize` act on it like any other.

## Properties

Nothing is stored on the node for MOC-ness. Everything below is derived from edges:

| Property | Type | Description |
|----------|------|-------------|
| `is_organizer` | Computed | True if the entity has outgoing `ORGANIZES` (emergent identity) |
| organizers | Query | Entities that organize this one (incoming `ORGANIZES`) |
| organized children | Query | Entities this one organizes (outgoing `ORGANIZES`, ordered by `order`) |

## Progress Tracking

Learning state is an edge from the user to the entity — `(User)-[:VIEWED|IN_PROGRESS|MASTERED]->(PathStep)` through `PsService.mastery`, `(User)-[:IN_PROGRESS|MASTERED]->(Ku)` through `KuService.mark_as_studying` / `mark_as_understood` — keyed by the entity's uid. A MOC never carries progress of its own; the same edge is read whichever path reached the entity:

```python
# Reached through an LP or through a MOC — the same edge either way
state = await ps_service.mastery.get_learning_state(user_uid, "ps.core.python-basics")
```

## Authoring a MOC from the vault

`moc: true` in the frontmatter of ANY ingestible file turns the file's body links (wiki + markdown) into `ORGANIZES {order}` edges to the link targets that resolve to ingested entities — `order` is document position, and edits re-draw the edges on the next sync. Dangling links are skipped silently in personal vaults and warned about in the content vault. The `moc` field itself is inert; nothing queries it — identity stays emergent.

**See:** `/docs/patterns/UNIFIED_INGESTION_GUIDE.md` § MOC files.

## Related Documentation

- [KU Domain](ku.md) - The atomic unit
- [PS Domain](ps.md) - THE curriculum content entity (linear path, parallel to MOC)
- [LP Domain](lp.md) - Learning paths sequencing path steps
- [Curriculum Grouping Patterns](../architecture/CURRICULUM_GROUPING_PATTERNS.md)
