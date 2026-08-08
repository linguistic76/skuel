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
| ORGANIZES operations (create/read/reorder) | `PsOrganizationService` (`core/services/ps/ps_organization_service.py`) + the `PsService` facade. **8** have routes in `adapters/inbound/path_steps_api.py`: `organize` / `unorganize` / `reorder` / `get_organized_children` / `is_organizer` / `get_organization_view` / `find_organizers` / `list_root_organizers`. `get_navigation` exists on the service but is **not** route-registered (service-only). PathStep-scoped. |
| MOC navigation surface (cross-domain context) | UserContext `active_moc_uids` / `recently_viewed_moc_uids` (consumed by Askesis, `core/services/askesis/context_retriever.py`) — **user-owned organizers only**: the query is `(user)-[:OWNS]->(moc:Entity)-[:ORGANIZES]->` (`adapters/persistence/neo4j/user_context_queries.py`), so shared KU/PathStep MOCs (the canonical curriculum case) do **not** appear here; only a user's own ORGANIZES-bearing entities do. |
| MOC navigation surface (UserEntry UI) | `GET /gradebook/{uid}` (`adapters/inbound/user_entry_ui.py`) renders a `moc: true` UserEntry's ORGANIZES children as a **"Map of Content"** card — via `UserEntryOrchestrator.get_entry_organized_children` → `UserEntryService.get_organized_children` (shared `_OrganizesMixin` backend). This is the implemented non-PathStep MOC read/navigation flow. |
| KU/MOC analytics | `KuIntelligenceService` is the KU analytics service (a Ku that organizes others is analyzed as a Ku). Its `assess_mastery_dual_track` **is** consumed (the Ku mastery-checkin route, `POST /explore/ku/{uid}/mastery-checkin`), but its **three generic route-factory methods** (`get_with_context` / `get_performance_analytics` / `get_domain_insights`) have no KU route (see the INDEX). Corpus-level KU structural health is separately reported by `KnowledgeHealthService`. |

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

The same knowledge node is reachable via both the PS (linear) and MOC (graph) paths. The shared organizing node carries **no** progress field of its own (a `Ku` has none; a `moc: true` UserEntry has none) — per-user learning progress is maintained by the learning-state / progress services (`PsProgressService`, `LpProgressService`, `user_progress_recorder_service`), not intrinsically on the organizing Entity.

---

## See Also

- [KU_INTELLIGENCE.md](./KU_INTELLIGENCE.md) - KU analytics (MOC uses KU intelligence)
- [/docs/domains/moc.md](/docs/domains/moc.md) - MOC domain documentation
- [CURRICULUM_GROUPING_PATTERNS.md](/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md) - Two paths to knowledge
