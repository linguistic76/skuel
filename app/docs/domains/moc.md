---
title: MOC (Map of Content) - KU-Based Architecture
created: 2025-12-04
updated: 2026-01-20
status: current
category: domains
tags:
- moc
- map-of-content
- organizational-domain
- ku-based
- montessori
related_skills:
- curriculum-domains
---

# MOC (Map of Content) - KU-Based Architecture

**Type:** Organizational Domain (1 of 1)
**Entity:** KU (Knowledge Unit) with ORGANIZES relationships
**Topology:** Graph (non-linear navigation)

## January 2026 - Architectural Change

**MOC is NOT a separate entity - it IS a Knowledge Unit.**

A KU "is" a MOC when it has outgoing ORGANIZES relationships to other KUs. This is emergent identity - no special flag needed.

## Two Paths to Knowledge (Montessori-Inspired)

**Skill:** [@curriculum-domains](../../.claude/skills/curriculum-domains/SKILL.md)

SKUEL provides two fundamental ways to interact with Knowledge Units:

| Path | Topology | Purpose | Pedagogy |
|------|----------|---------|----------|
| **LS** | Linear | Structured curriculum | Teacher-directed |
| **MOC** | Graph | Free exploration | Learner-directed |

Same KU, two access paths. Progress is tracked on the KU itself, not the path.

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

## Key Concepts

| Concept | Definition |
|---------|------------|
| MOC | A KU that organizes other KUs via ORGANIZES relationships |
| Section | A KU within a MOC that organizes child KUs (nested MOC) |
| ORGANIZES | Relationship type: `(parent:Ku)-[:ORGANIZES {order: int}]->(child:Ku)` |
| Root MOC | A KU that organizes others but is not itself organized |

## Service Architecture

```python
from core.services.moc_service import MOCService

# MOCService is a thin facade over MocNavigationService
moc_service = MOCService(
    ku_service=ku_service,  # REQUIRED - underlying KU operations
    driver=driver,          # REQUIRED - for graph queries
)

# Check if KU acts as MOC
is_moc = await moc_service.is_moc("ku.python-reference")

# Get MOC view (KU with organized children)
moc_view = await moc_service.get("ku.python-reference", max_depth=3)

# Organize KUs
await moc_service.organize("ku.python-reference", "ku.python-basics", order=1)

# Find MOCs containing a KU
mocs = await moc_service.find_mocs_containing("ku.python-basics")

# List root MOCs
roots = await moc_service.list_root_mocs(limit=50)
```

## Key Files

| Component | Location |
|-----------|----------|
| Facade | `/core/services/moc_service.py` |
| Navigation Service | `/core/services/moc/moc_navigation_service.py` |
| Relationship Config | `/core/services/relationships/domain_configs.py` (KU config with ORGANIZES) |
| API Routes | `/adapters/inbound/moc_api.py` |

## ORGANIZES Relationship

The ORGANIZES relationship connects KUs in a MOC hierarchy:

```cypher
// Create organization
MATCH (parent:Ku {uid: $parent_uid})
MATCH (child:Ku {uid: $child_uid})
MERGE (parent)-[r:ORGANIZES]->(child)
SET r.order = $order

// Check if KU is a MOC
MATCH (ku:Ku {uid: $ku_uid})
OPTIONAL MATCH (ku)-[:ORGANIZES]->(child:Ku)
RETURN count(child) > 0 AS is_moc

// Get organized children
MATCH (parent:Ku {uid: $ku_uid})-[r:ORGANIZES]->(child:Ku)
RETURN child.uid, child.title, r.order
ORDER BY r.order ASC
```

## Example MOC Structure

```
KU: "Python Reference" (root MOC)
├── ORGANIZES(order=1) → KU: "Fundamentals"
│   ├── ORGANIZES(order=1) → KU: "python-basics"
│   ├── ORGANIZES(order=2) → KU: "python-syntax"
│   └── ORGANIZES(order=3) → KU: "Data Types" (nested section)
│       ├── ORGANIZES(order=1) → KU: "python-strings"
│       └── ORGANIZES(order=2) → KU: "python-lists"
├── ORGANIZES(order=2) → KU: "Advanced"
│   ├── ORGANIZES(order=1) → KU: "python-async"
│   └── ORGANIZES(order=2) → KU: "python-decorators"
└── ORGANIZES(order=3) → KU: "python-best-practices"
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/moc/is-moc?uid=...` | GET | Check if KU is a MOC |
| `/api/moc/get?uid=...&max_depth=3` | GET | Get MOC view with hierarchy |
| `/api/moc/organize` | POST | Create ORGANIZES relationship |
| `/api/moc/unorganize` | POST | Remove ORGANIZES relationship |
| `/api/moc/reorder` | POST | Change order of child KU |
| `/api/moc/containing?uid=...` | GET | Find MOCs containing a KU |
| `/api/moc/roots?limit=50` | GET | List root MOCs |
| `/api/moc/children?uid=...` | GET | Get direct children of MOC |
| `/api/moc/create-ku` | POST | Create KU (convenience) |

## Properties

| Property | Type | Description |
|----------|------|-------------|
| KU fields | Various | All standard KU fields (title, description, content, etc.) |
| is_moc | Computed | True if KU has outgoing ORGANIZES (emergent identity) |
| organized_by | Query | MOCs that organize this KU (via incoming ORGANIZES) |
| organizes | Query | KUs organized by this KU (via outgoing ORGANIZES) |

## Progress Tracking

Progress is tracked on the KU itself, unified across both LS and MOC paths:

```python
# Same KU, accessed via different paths
# Progress is tracked on KU node, not path

# Via LS path
ku_progress = await ku_service.get_progress("ku.python-basics", user_uid)

# Via MOC path - same progress!
ku_progress = await ku_service.get_progress("ku.python-basics", user_uid)
```

## Migration from Old Architecture

The old architecture had:
- `MapOfContent` entity (separate from KU)
- `MOCSection` entity (separate from KU)
- 8 sub-services (core, search, section, content, discovery, intelligence, template, AI)

The new architecture:
- MOC IS a KU with ORGANIZES relationships
- Sections ARE KUs within the hierarchy
- 1 navigation service (MocNavigationService)
- Underlying KU operations via KuService

## Related Documentation

- [KU Domain](ku.md) - The fundamental entity type
- [LS Domain](ls.md) - Structured learning path (parallel to MOC)
- [LP Domain](lp.md) - Learning paths containing LSs
- [Curriculum Grouping Patterns](../architecture/CURRICULUM_GROUPING_PATTERNS.md)
