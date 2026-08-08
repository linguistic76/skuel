# MOC Intelligence (KU-Based Architecture)

**Last Updated:** January 20, 2026 · **Code-accuracy audit:** August 8, 2026 (removed a fictional `MocNavigationService`/`MOCService` architecture; see below)

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

KU analytics are handled by `KuIntelligenceService`. There is **no MOC service of any kind** — the KU-based refactoring removed `MocIntelligenceService` outright and did **not** replace it with a facade.

## Current Architecture

**There is no `MOCService`, `MocNavigationService`, or `KuOrganizationService`.** MOC is not a service layer — it is emergent identity: any `Entity` with outgoing `ORGANIZES` edges *is* a MOC. What used to be "MOC operations" is now distributed across the ORGANIZES edge and existing services:

| Concern | Where it lives (verified) |
|---------|---------------------------|
| MOC identity | Emergent — any `Entity` with outgoing `ORGANIZES` edges (no flag, no service). See `CLAUDE.md` and [`CURRICULUM_GROUPING_PATTERNS.md`](/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md). |
| Authoring MOC edges | Ingestion — `moc: true` frontmatter → `ORGANIZES {order}` edges (`core/services/ingestion/moc_links.py`). |
| ORGANIZES relationships on PathSteps | `PsOrganizationService` (`core/services/ps/ps_organization_service.py`) — hierarchical previous/next-sibling navigation over the ORGANIZES order. |
| MOC navigation surface | UserContext (`active_moc_uids`, `recently_viewed_moc_uids`), consumed by Askesis (`core/services/askesis/context_retriever.py`). |
| KU/MOC analytics | `KuIntelligenceService` — a Ku that organizes others is analyzed as a Ku. |

> **Prior fiction (removed 2026-08-08 audit):** earlier revisions of this doc described a `MOCService` → `MocNavigationService` → `KuService` stack with methods `is_moc` / `get_moc_view` / `organize` / `list_root_mocs` / etc. **None of those classes, files, or methods exist** — they were never built. The table above reflects the actual code.

## Two Paths to Knowledge

MOC provides the **learner-directed exploration path** parallel to the **teacher-directed PS path**:

| Path | Topology | Purpose | Pedagogy |
|------|----------|---------|----------|
| PS | Linear | Structured curriculum | Teacher-directed |
| MOC | Graph | Free exploration | Learner-directed |

Progress is tracked on the KU itself, unified across both paths.

---

## See Also

- [KU_INTELLIGENCE.md](./KU_INTELLIGENCE.md) - KU analytics (MOC uses KU intelligence)
- [/docs/domains/moc.md](/docs/domains/moc.md) - MOC domain documentation
- [CURRICULUM_GROUPING_PATTERNS.md](/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md) - Two paths to knowledge
