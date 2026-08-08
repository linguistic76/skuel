# MOC Intelligence (Emergent Identity, KU-Canonical)

**Last Updated:** January 20, 2026 · **Code-accuracy audit:** August 8, 2026 (removed a fictional `MocNavigationService`/`MOCService` architecture; see below)

---

## January 2026 - KU-Based Architecture

**MOC no longer has a dedicated intelligence service.**

MOC is NOT a separate entity or service — it is **emergent identity**: any `Entity` with outgoing `ORGANIZES` edges *is* a MOC (CLAUDE.md). No flag, no `entity_type` — the outgoing edges alone confer MOC identity. The **canonical** case is a Knowledge Unit (KU) that organizes other KUs (the learner-directed knowledge map); PathSteps also carry `ORGANIZES` edges (managed by `PsOrganizationService`, see below). This doc keeps the KU framing because the KU knowledge-map is the primary use case, but nothing about MOC identity is KU-only.

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
| ORGANIZES operations (create/read/reorder, navigation) | `PsOrganizationService` (`core/services/ps/ps_organization_service.py`) + the `PsService` facade, registered by `adapters/inbound/path_steps_api.py`: `organize` / `unorganize` / `reorder` / `get_organized_children` / `is_organizer` / `get_organization_view` / `find_organizers` / `list_root_organizers` / `get_navigation`. PathStep-scoped. |
| MOC navigation surface | UserContext (`active_moc_uids`, `recently_viewed_moc_uids`), consumed by Askesis (`core/services/askesis/context_retriever.py`). |
| KU/MOC analytics | `KuIntelligenceService` — a Ku that organizes others is analyzed as a Ku. |

> **Prior fiction (corrected 2026-08-08 audit).** Earlier revisions described a `MOCService` →
> `MocNavigationService` → `KuService` **class stack** (files `core/services/moc_service.py`,
> `core/services/moc/moc_navigation_service.py`) with **KU-scoped** methods `is_moc(ku_uid)` /
> `get_moc_view(ku_uid)` / `find_mocs_containing(ku_uid)` / `list_root_mocs()`. **That class
> architecture and those KU-scoped names never existed.**
>
> The ORGANIZES **operations themselves do exist** — but on **PathSteps**, via `PsOrganizationService`
> and the `PsService` facade (backed by `adapters/persistence/neo4j/_organizes_mixin.py`, registered by
> `adapters/inbound/path_steps_api.py`): `organize` / `unorganize` / `reorder` / `get_organized_children`
> verbatim, plus `is_organizer` / `get_organization_view` / `find_organizers` / `list_root_organizers`
> (the real, PathStep-scoped equivalents of the fictional KU-scoped names above).

## Two Paths to Knowledge

MOC provides the **learner-directed exploration path** parallel to the **teacher-directed PS path**:

| Path | Topology | Purpose | Pedagogy |
|------|----------|---------|----------|
| PS | Linear | Structured curriculum | Teacher-directed |
| MOC | Graph | Free exploration | Learner-directed |

Progress is tracked on the organizing entity itself (a KU in the canonical case), unified across both paths.

---

## See Also

- [KU_INTELLIGENCE.md](./KU_INTELLIGENCE.md) - KU analytics (MOC uses KU intelligence)
- [/docs/domains/moc.md](/docs/domains/moc.md) - MOC domain documentation
- [CURRICULUM_GROUPING_PATTERNS.md](/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md) - Two paths to knowledge
