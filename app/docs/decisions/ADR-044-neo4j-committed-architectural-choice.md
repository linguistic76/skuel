---
title: ADR-044: Neo4j as Committed Architectural Choice
updated: 2026-03-05
status: current
category: decisions
tags: [adr, decisions, architecture, neo4j, hexagonal]
related: [ADR-022, ADR-029, ADR-031]
---

# ADR-044: Neo4j as Committed Architectural Choice

**Status:** Accepted

**Date:** 2026-03-05

**Decision Type:** ✅ Pattern/Practice  ✅ Graph Schema

**Related ADRs:**
- Related to: ADR-022 (Graph-Native Authentication)
- Related to: ADR-029 (GraphNative Service Removal)
- Related to: ADR-031 (BaseService Mixin Decomposition)

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

The hexagonal boundary in SKUEL is at `UniversalNeo4jBackend` (and its subclasses in `domain_backends.py`). This is where Neo4j specifics — driver calls, Cypher generation, label conventions, relationship syntax — stop. Above this boundary, the service layer and domain models are written in domain concepts. Below it, everything is Neo4j.

**The mixin layer is intentionally graph-aware.** `ContextOperationsMixin` and `RelationshipOperationsMixin` use graph vocabulary (`depth`, `traverse`, `graph_enrichment_patterns`) because SKUEL's domain model is inherently a graph. The relationships between a Task, its prerequisite KUs, its contributing Goal, and its SERVES_LIFE_PATH target are not incidental storage concerns — they are the domain. Expressing them in graph terms at the service layer is not a leaky abstraction; it is appropriate coupling.

**What "committed" means in practice:**

- The MEGA-QUERY (UserContext), graph traversal (context enrichment), and relationship-driven recommendations all depend on Neo4j's native capabilities.
- The Entity Type Architecture uses multi-label nodes (`:Entity:Task`, `:Entity:Ku`) — a Neo4j convention that has no direct analogue in relational or document databases.
- `ORGANIZES`, `SERVES_LIFE_PATH`, `SHARES_WITH`, `BLOCKS`, `PREREQUISITE_FOR` — these relationships are domain primitives, not storage implementation details.
- The intelligence layer (UserContextIntelligence, BaseAnalyticsService) derives insights by traversing the graph. This is not a query optimization; it is how the domain works.

**What "hexagonal boundary at UniversalNeo4jBackend" means:**

The backend layer contains all Neo4j driver calls, all Cypher strings, all label conventions, all relationship syntax. Service mixins call backend methods (`self.backend.traverse()`, `self.backend.find_by()`) — they do not write Cypher directly. If Neo4j were ever replaced (see Consequences), the backend layer would be rewritten, and the mixin layer would need to be reconsidered — but the domain models and protocols would survive intact.

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
- ⚠️ Swapping Neo4j would require rewriting `UniversalNeo4jBackend`, `domain_backends.py`, `UserBackend`, and reconsidering `ContextOperationsMixin` and `RelationshipOperationsMixin` — it is not a one-layer change
- ⚠️ New contributors familiar with strict hexagonal architecture may read the mixin layer as incomplete refactoring; this ADR exists to correct that reading

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Mixin layer accumulates raw Cypher strings | Medium | Medium | SKUEL001 linter rule prohibits direct Cypher in service layer; all Cypher lives in backend or `core/models/query/cypher/` |
| Graph semantics bleed past the mixin layer into routes | Low | Medium | Routes call service methods; service mixins call backend methods; Cypher never appears in route files |

---

## Implementation Details

### The Boundary in Code

```
Routes (FastHTML)
    ↓ call service methods
Services + Mixins (ContextOperationsMixin, RelationshipOperationsMixin)
    ↓ call backend methods via self.backend.*
UniversalNeo4jBackend / domain backends      ← HEXAGONAL BOUNDARY
    ↓ write Cypher, call Neo4j driver
Neo4j
```

Above the boundary: domain concepts (`get_with_context`, `get_prerequisites`, `traverse`).
At the boundary: generic backend protocol methods (`find_by`, `execute_query`, `relate`).
Below the boundary: Cypher strings, `AsyncDriver` calls, label conventions.

### Code Location

- Hexagonal boundary: `adapters/persistence/neo4j/universal_backend.py` and `domain_backends.py`
- Intentionally graph-aware mixins: `core/services/mixins/context_operations_mixin.py`, `core/services/mixins/relationship_operations_mixin.py`
- Linter enforcement: `SKUEL001` (no APOC/raw Cypher in domain services)
- Backend protocol: `core/ports/base_protocols.py` — `BackendOperations[T]`

### Testing Strategy
- Protocol compliance: `tests/unit/test_protocol_mixin_compliance.py` (29 tests) — verifies mixin interfaces match protocols
- Backend isolation: service tests mock `BackendOperations`, not the Neo4j driver — the boundary is respected in tests

---

## Future Considerations

### When to Revisit
- If SKUEL ever adopts a second database for a specific domain (e.g., time-series data for Habits completion history), this ADR should be revisited to define where that boundary sits
- If `ContextOperationsMixin` or `RelationshipOperationsMixin` begin writing raw Cypher strings directly (currently prohibited by SKUEL001), the boundary has eroded and needs correction

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
