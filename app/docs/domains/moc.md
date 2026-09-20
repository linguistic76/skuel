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

ORGANIZES operations are the `organization` slot of the PathStep facade — `PsService.organization` is a `PsOrganizationService` (`core/services/ps/ps_organization_service.py`), and the facade delegates every method. The backend is `_OrganizesMixin` (`adapters/persistence/neo4j/_organizes_mixin.py`), mixed into `PsBackend` and `UserEntryBackend`; it matches `:Entity` by uid, so any entity type can organize or be organized.

```python
ps_service = services.ps  # PsService

# Identity — does this entity organize anything?
is_moc = await ps_service.is_organizer("ps.core.python-reference")

# The organizer with its organized children, depth-limited
view = await ps_service.get_organization_view("ps.core.python-reference", max_depth=3)

# Write the hierarchy
await ps_service.organize("ps.core.python-reference", "ps.core.python-basics", order=1)
await ps_service.reorder("ps.core.python-reference", "ps.core.python-basics", new_order=2)
await ps_service.unorganize("ps.core.python-reference", "ps.core.python-basics")

# Navigate
parents = await ps_service.find_organizers("ps.core.python-basics")
children = await ps_service.get_organized_children("ps.core.python-reference")
roots = await ps_service.list_root_organizers(limit=50)
nav = await ps_service.get_navigation("ps.core.python-basics")  # StepNavigation
```

## Key Files

| Component | Location |
|-----------|----------|
| Facade | `/core/services/ps_service.py` (§ ORGANIZATION delegation) |
| Organization Service | `/core/services/ps/ps_organization_service.py` |
| Backend mixin | `/adapters/persistence/neo4j/_organizes_mixin.py` (`_OrganizesMixin` — on `PsBackend` and `UserEntryBackend`) |
| Backend protocol | `PsOrganizesBackendOperations` in `/core/ports/curriculum_protocols.py` |
| Relationship Config | `ORGANIZES` definitions in `/core/models/relationship_registry.py` (`KU_CONFIG` and the PathStep config) |
| API Routes | `/adapters/inbound/path_steps_api.py` § ORGANIZES HIERARCHY |
| Vault authoring | `/core/services/ingestion/moc_links.py` (`moc: true` body links → `ORGANIZES {order}` edges) |

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

All in `adapters/inbound/path_steps_api.py`. The three writes are admin-only and CSRF-protected; the reads are open (curriculum is shared content).

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/path-steps/{uid}/is-organizer` | GET | Does this entity organize anything? |
| `/api/path-steps/{uid}/organization` | GET | The organizer with its organized-children hierarchy |
| `/api/path-steps/{uid}/organizers` | GET | Parents that organize this entity |
| `/api/path-steps/{uid}/organized-children` | GET | Direct organized children, in order |
| `/api/path-steps/root-organizers?limit=50` | GET | Root MOCs (organize others, organized by nothing) |
| `/api/path-steps/organize` | POST | Create an `ORGANIZES` edge (`StepOrganizeRequest`: `parent_uid`, `child_uid`, `order`) — admin |
| `/api/path-steps/unorganize` | POST | Remove an `ORGANIZES` edge — admin |
| `/api/path-steps/reorder` | POST | Change a child's order (`StepReorderRequest`: `parent_uid`, `child_uid`, `new_order`) — admin |

There is no MOC-specific create door: organizers and children are ordinary entities, created through vault ingestion or their own domain's API.

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
