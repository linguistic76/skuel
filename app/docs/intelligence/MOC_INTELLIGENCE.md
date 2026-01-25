# MOC Intelligence (KU-Based Architecture)

**Last Updated:** January 20, 2026

---

## January 2026 - KU-Based Architecture

**MOC no longer has a dedicated intelligence service.**

MOC is NOT a separate entity - it IS a Knowledge Unit (KU) that organizes other KUs via ORGANIZES relationships. A KU "is" a MOC when it has outgoing ORGANIZES relationships (emergent identity).

## Previous Architecture (Deleted)

The old `MocIntelligenceService` (~790 lines) was deleted as part of the KU-based MOC refactoring. It provided:

- Navigation recommendations
- Content coverage analysis
- Cross-domain bridge strength
- Section hierarchy analysis
- Practice integration assessment

These capabilities are now handled through:

1. **KU Intelligence** - `KuIntelligenceService` handles all KU analytics
2. **MOC Navigation Service** - `MocNavigationService` handles MOC-specific navigation operations

## Current Architecture

```
MOCService (thin facade)
└── MocNavigationService (all MOC operations)
    └── KuService (underlying KU CRUD)
```

### Key Files

| Component | File |
|-----------|------|
| MOC Facade | `/core/services/moc_service.py` |
| Navigation Service | `/core/services/moc/moc_navigation_service.py` |
| MOC Domain Docs | `/docs/domains/moc.md` |

### MOC Navigation Operations

The `MocNavigationService` provides:

| Method | Purpose |
|--------|---------|
| `is_moc(ku_uid)` | Check if KU has ORGANIZES relationships |
| `get_moc_view(ku_uid, depth)` | Get hierarchical view of organized KUs |
| `organize(parent_uid, child_uid, order)` | Create ORGANIZES relationship |
| `unorganize(parent_uid, child_uid)` | Remove ORGANIZES relationship |
| `reorder(parent_uid, child_uid, new_order)` | Change order position |
| `find_mocs_containing(ku_uid)` | Find parent MOCs for a KU |
| `list_root_mocs(limit)` | List top-level MOC KUs |
| `get_organized_children(ku_uid)` | Get direct children |

## Two Paths to Knowledge

MOC provides the **learner-directed exploration path** parallel to the **teacher-directed LS path**:

| Path | Topology | Purpose | Pedagogy |
|------|----------|---------|----------|
| LS | Linear | Structured curriculum | Teacher-directed |
| MOC | Graph | Free exploration | Learner-directed |

Progress is tracked on the KU itself, unified across both paths.

---

## See Also

- [KU_INTELLIGENCE.md](./KU_INTELLIGENCE.md) - KU analytics (MOC uses KU intelligence)
- [/docs/domains/moc.md](/docs/domains/moc.md) - MOC domain documentation
- [CURRICULUM_GROUPING_PATTERNS.md](/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md) - Two paths to knowledge
