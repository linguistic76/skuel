---
title: ADR-044: Neo4j as Committed Architectural Choice
updated: 2026-05-25
status: current
category: decisions
tags: [adr, decisions, architecture, neo4j, hexagonal]
related: [ADR-022, ADR-029, ADR-031, ADR-052, ADR-062]
---

# ADR-044: Neo4j as Committed Architectural Choice

**Status:** Accepted

**Date:** 2026-03-05

**Decision Type:** ✅ Pattern/Practice  ✅ Graph Schema

**Related ADRs:**
- Related to: ADR-022 (Graph-Native Authentication)
- Related to: ADR-029 (GraphNative Service Removal)
- Related to: ADR-031 (BaseService Mixin Decomposition)
- Scoped by: ADR-052 (Firefly III Finance Integration) — the finance store sits *outside* this commitment
- Scoped by: ADR-062 (ChargeKeep Billing Layer) — the proposed billing store sits *outside* this commitment

---

## Context

SKUEL uses Neo4j as its database. The question this ADR answers is: **what kind of choice is that?**

Two interpretations are possible:

1. **Swappable adapter:** Neo4j is the current implementation of an abstract persistence layer. Swapping it for Postgres or another database would require only adapter-layer changes. The service and domain layers remain untouched.

2. **Committed architectural choice:** Neo4j's graph semantics are load-bearing throughout the architecture. The service layer is intentionally graph-aware. Replacing Neo4j would require rewriting multiple layers, not just the adapter.

SKUEL is the second. This ADR makes that explicit so future contributors — human or AI — don't mistake the current state for an incomplete refactor toward the first.

**What triggered this decision:**

The `ContextOperationsMixin` and `RelationshipOperationsMixin` in `core/services/mixins/` contain methods that build graph traversal queries — concepts like `depth`, `traverse`, `graph_enrichment_patterns`, and `prerequisite_relationships`. These live in the service mixin layer, not the adapter layer. A pure hexagonal architecture would push these concerns entirely into the adapter.

The question arose: is this coupling a gap to close, or is it the intended design? This ADR records that it is the intended design, and why.

---

## Decision

**Neo4j is a committed architectural dependency, not a swappable implementation detail.**

The hexagonal boundary in SKUEL is at `UniversalNeo4jBackend` (and its 27 subclasses under `adapters/persistence/neo4j/backends/`). This is where Neo4j specifics — driver calls, Cypher generation, label conventions, relationship syntax — stop. Above this boundary, the service layer and domain models are written in domain concepts. Below it, everything is Neo4j.

**The mixin layer is intentionally graph-aware.** `ContextOperationsMixin` and `RelationshipOperationsMixin` use graph vocabulary (`depth`, `traverse`, `graph_enrichment_patterns`) because SKUEL's domain model is inherently a graph. The relationships between a Task, its prerequisite KUs, its contributing Goal, and its SERVES_LIFE_PATH target are not incidental storage concerns — they are the domain. Expressing them in graph terms at the service layer is not a leaky abstraction; it is appropriate coupling.

**What "committed" means in practice:**

- The MEGA-QUERY (UserContext), graph traversal (context enrichment), and relationship-driven recommendations all depend on Neo4j's native capabilities.
- The Entity Type Architecture uses multi-label nodes (`:Entity:Task`, `:Entity:Ku`) — a Neo4j convention that has no direct analogue in relational or document databases.
- `ORGANIZES`, `SERVES_LIFE_PATH`, `SHARES_WITH`, `BLOCKS`, `PREREQUISITE_FOR` — these relationships are domain primitives, not storage implementation details.
- The intelligence layer (UserContextIntelligence, BaseAnalyticsService) derives insights by traversing the graph. This is not a query optimization; it is how the domain works.

**What "hexagonal boundary at UniversalNeo4jBackend" means:**

The backend layer holds the driver calls, label conventions, and relationship syntax. Service mixins *should* call backend methods (`self.backend.traverse()`, `self.backend.find_by()`) rather than writing Cypher directly — that is the target state, not an invariant the codebase currently upholds everywhere (see **Current State & Known Debt** below). If Neo4j were ever replaced (see Consequences), the backend layer would be rewritten, the mixin layer would need to be reconsidered, and every service still authoring Cypher would have to move too — but the domain models and protocols would survive intact.

### Scope: this commitment governs the domain graph, not the finance/billing edge

"Below the boundary, everything is Neo4j" describes the **domain graph** — the 25 EntityTypes, graph-native auth (ADR-022), and the intelligence layer that traverses them. It is **not** a claim that SKUEL is single-store. SKUEL is deliberately a **polystore at the finance/billing edge**, where the **Leverage Maintained Software** principle (a non-technical founder; every custom subsystem is a liability) outranks the graph commitment:

| Data | Store | Seam | Status |
|------|-------|------|--------|
| Expenses, budgets, reporting | **Firefly III** — own MariaDB, Docker sidecar (`finance` profile) | `firefly_client` outbound adapter behind `FireflyOperations` (`core/ports/finance_protocols.py`) | ADR-052 — **Accepted**; adapter + protocol + Docker stack landed (`c3258630`) |
| SaaS billing: checkout, subscriptions, invoicing | **ChargeKeep** — SaaS (Stripe underneath) | proposed `chargekeep_client` behind `BillingProvider` | ADR-062 — **Proposed**, spike-gated; no code yet |

This is not a violation of the commitment, for two reasons:

1. **Different seam.** These stores sit behind *outbound adapters* in `adapters/outbound/` — the same hexagonal pattern as `invoice_renderer.py`, **not** behind `UniversalNeo4jBackend`. The Neo4j boundary this ADR defends is untouched; the finance/billing data simply never crossed it.
2. **Isolated domain.** Finance has no cross-domain relationships and no intelligence / ZPD / LifePath wiring (ADR-052 § Context). It is a clean seam with nothing graph-native to lose — which is precisely why it can be offloaded to maintained external software.

So the commitment is **scoped**, not absolute: Neo4j is load-bearing for everything that *is* a graph (the domain), and silent on the admin-only / payment-scoped finance edge, which is owned by ADR-052 + ADR-062. (The local WeasyPrint invoice module still lives in Neo4j today; ADR-062 proposes moving it to ChargeKeep.)

---

## Alternatives Considered

### Alternative 1: Pure hexagonal — all graph concerns in the adapter

**Description:** Push `ContextOperationsMixin` and `RelationshipOperationsMixin` entirely into `UniversalNeo4jBackend`. Service mixins speak only in domain terms (`get_related_entities`, not `traverse`). The adapter translates to graph calls.

**Pros:**
- Cleaner separation of concerns in theory
- Easier to reason about what is "domain" vs "infrastructure"

**Cons:**
- `get_related_entities` is a meaningless abstraction when the domain *is* relationships — it just renames graph concepts without removing the dependency
- The backend would absorb domain logic (which entities are prerequisites, which relationships matter for context) that currently lives correctly in the service layer
- Premature generalization: SKUEL has no requirement to support multiple databases

**Why rejected:** The abstraction would be hollow. The service layer would still need to tell the backend *which* relationships to follow, *what depth* to traverse, *which patterns* to enrich with — i.e., all the graph decisions. Hiding this behind a generic method name doesn't reduce the coupling; it obscures it.

### Alternative 2: Annotate the coupling but don't formalize it

**Description:** Leave the current architecture as-is, but add comments where graph concepts appear in the service layer.

**Pros:**
- No changes required
- Low overhead

**Cons:**
- Leaves future contributors to rediscover (or misread) the intent
- Doesn't prevent well-meaning refactors that try to "fix" the coupling

**Why rejected:** The point of an ADR is to record decisions so they aren't relitigated. Comments don't carry the same weight.

---

## Consequences

### Positive Consequences
- ✅ Service mixins can express graph traversal in natural, domain-appropriate terms
- ✅ No artificial abstraction layer between domain logic and graph capabilities
- ✅ Full use of Neo4j's native strengths: multi-label nodes, variable-depth traversal, relationship metadata
- ✅ Developer velocity: adding a new relationship type doesn't require updating an abstraction layer

### Negative Consequences
- ⚠️ Swapping Neo4j would require rewriting `UniversalNeo4jBackend`, the `backends/` cluster files, `UserBackend`, and reconsidering `ContextOperationsMixin` and `RelationshipOperationsMixin` — it is not a one-layer change
- ⚠️ New contributors familiar with strict hexagonal architecture may read the mixin layer as incomplete refactoring; this ADR exists to correct that reading

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Service layer accumulates raw Cypher strings | **Resolved + guarded** | Medium | Debt paid down (2026-05 — see below) and now enforced by **`SKUEL021`** (ERROR), which flags raw Cypher authored in `core/services/`. Note: `SKUEL001` bans **APOC** only; `SKUEL021` is the rule that covers raw Cypher generally. |
| Graph semantics bleed past the mixin layer into routes | Low | Medium | Routes call service methods; Cypher never appears in route files |

> ⚠️ **Correction (2026-05-24):** earlier revisions of this ADR claimed "SKUEL001 linter rule prohibits direct Cypher in the service layer; all Cypher lives in the backend." That was never true. `SKUEL001` (`scripts/lint_skuel.py`) bans a fixed list of **APOC** procedures only — raw Cypher in the service layer was unguarded. That gap is now closed by the new **`SKUEL021`** rule (added 2026-05-24, after the debt below was paid down).

---

## Implementation Details

### The Boundary in Code

```
Routes (FastHTML)
    ↓ call service methods
Services + Mixins (ContextOperationsMixin, RelationshipOperationsMixin)
    ↓ call backend methods via self.backend.*
UniversalNeo4jBackend / backends/ cluster files   ← HEXAGONAL BOUNDARY
    ↓ write Cypher, call Neo4j driver
Neo4j
```

Above the boundary: domain concepts (`get_with_context`, `get_prerequisites`, `traverse`).
At the boundary: generic backend protocol methods (`find_by`, `execute_query`, `relate`).
Below the boundary: Cypher strings, `AsyncDriver` calls, label conventions.

### Code Location

- Hexagonal boundary: `adapters/persistence/neo4j/universal_backend.py` and `adapters/persistence/neo4j/backends/`
- Intentionally graph-aware mixins: `core/services/mixins/context_operations_mixin.py`, `core/services/mixins/relationship_operations_mixin.py`
- Linter enforcement: `SKUEL001` (bans **APOC procedures only** — not raw Cypher)
- Backend protocol: `core/ports/base_protocols.py` — `BackendOperations[T]`

### Testing Strategy
- Protocol compliance: `tests/unit/test_protocol_mixin_compliance.py` (29 tests) — verifies mixin interfaces match protocols
- Backend isolation: service tests mock `BackendOperations`, not the Neo4j driver — the boundary is respected in tests

### Current State (2026-05-24) — boundary fully closed + guarded

"All Cypher lives below the boundary" is now **true and enforced.** Ports expose
no driver types, the generic backend and `BaseService` are Cypher-free, routes
never touch the driver, and `core/services/` no longer authors Cypher. Authoring
location, not injection, was the original violation — the executor was always a
proper adapter seam; the Cypher text just used to live above it.

**Relocated below the boundary (2026-05-24)** — each as an adapter backend
(`adapters/persistence/neo4j/`), most behind a `core/ports` protocol; services
keep orchestration + result-shaping and call backend methods:

| Was (core/services) | Now (adapter backend) |
|---|---|
| `user_relationship_service` *(false "Direct Driver" docstring)* | `UserRelationshipBackend` + `UserRelationshipOperations` |
| `analytics_relationship_service` *(false "Direct Driver" docstring)* | `AnalyticsRelationshipBackend` + `AnalyticsRelationshipOperations` — **both since deleted** (2026-07, SKUEL030 findings §1: the backend queried a purged `:Report` label and had no callers) |
| `schema_service` | `Neo4jSchemaService` (relocated) |
| `templates/__init__` attach/detach/list | `TemplateAttachmentBackend` + `TemplateAttachmentOperations` |
| `infrastructure/graph_query_builder` | `query/graph_context_query_builder` (backend builds by intent) |
| `ps_engagement/*` (service, gateway, loader) | `PsEngagementBackend` + `PsEngagementOperations` |
| `ingestion/*` (service, batch, validator) | `IngestionWriteBackend` |
| `chunks/batch_chunking_service` | `BatchChunkingBackend` |
| `ps/ps_intelligence_service` | `PsIntelligenceBackend` |
| `user/user_context_queries` (MEGA / CONSOLIDATED) | relocated to `adapters/persistence/neo4j/` |
| `query/*` (optimizer, templates, faceted, validator, graph-context) | relocated to `adapters/persistence/neo4j/query_builders/` |

Two latent bugs were fixed en route (a raw driver was passed where executor /
adapter methods were called, in the analytics and learning-services wiring).

**Enforcement:** new Cypher in the service layer is now blocked by **`SKUEL021`**
(ERROR, `scripts/lint_skuel.py`). `cross_domain_backend.py` and the backends
above are the templates for any future graph code.

> ⚠️ The `ingestion` write path and the `ps_engagement` spawn lifecycle were
> moved faithfully (verbatim Cypher; behavior preserved) and are covered by the
> relocated unit tests, but a **live smoke-test (real ingest + engage→spawn)** is
> still advisable before relying on them in production.

---

## Future Considerations

### When to Revisit
- SKUEL has **already** adopted second stores for the finance/billing domain — Firefly III (landed) and the proposed ChargeKeep (see *Scope: this commitment governs the domain graph, not the finance/billing edge* above). The rule that emerged: an *isolated* non-graph domain (no cross-domain edges, no intelligence wiring) may live behind its own outbound adapter rather than `UniversalNeo4jBackend`. If a **graph-coupled** domain ever needs a second store (e.g., time-series Habits completion history that still relates to Goals/KUs), revisit this ADR to define where that split boundary sits — that case is genuinely harder than the isolated finance seam.
- New Cypher-authoring in the service layer is now blocked by `SKUEL021` (ERROR). If that rule is ever relaxed or a service legitimately needs a `# skuel-lint: disable=SKUEL021` suppression, treat it as a signal to extend a backend instead — the boundary should stay closed.

### Evolution Path
Neo4j is the committed platform for SKUEL across all three deployment stages (Docker → DigitalOcean Droplet → AuraDB). The graph model is not a current-state compromise pending migration; it is the intended final form.

---

## Documentation & Communication

### Related Documentation
- Architecture: `/docs/patterns/protocol_architecture.md` — service protocol hierarchy
- Architecture: `/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md` — entity type graph model
- Linter: `/docs/patterns/linter_rules.md` — SKUEL001 enforcement
- Code: `adapters/persistence/neo4j/universal_backend.py` — boundary implementation

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-03-05 | Claude Code | Initial draft | 1.0 |
| 2026-05-24 | Claude Code | Corrected false "SKUEL001 prohibits raw Cypher in services" claim (it bans APOC only); added Current State & Known Debt; recorded relocation of relationship/analytics/schema backends below the boundary | 1.1 |
| 2026-05-24 | Claude Code | Completed the campaign: ALL raw Cypher relocated out of `core/services/` (templates, graph_query_builder, ps_engagement, ingestion, chunks, ps_intelligence, MEGA-QUERY, query/* builders) + added enforcement rule `SKUEL021` so it can't recur | 1.2 |
| 2026-05-25 | Claude Code | Reconciled the "below the boundary, everything is Neo4j" framing with polystore reality: added a **Scope** subsection (finance = Firefly III sidecar, landed; billing = proposed ChargeKeep — both behind outbound adapters, not `UniversalNeo4jBackend`), updated *When to Revisit* (finance already adopted a second store), and cross-linked ADR-052 + ADR-062 | 1.3 |
