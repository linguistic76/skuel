---
title: "ADR-085: Ownership Read-Enforcement Contract"
updated: 2026-08-30
status: accepted
category: decisions
tags: [adr, decisions, ownership, multi-tenancy, security, search, reads]
related: [ADR-038, ADR-086]
related_skills: [security, skuel-search-architecture]
---

# ADR-085: Ownership Read-Enforcement Contract

**Status:** Accepted — founder-ratified 2026-08-21
**Date:** 2026-08-21
**Deciders:** MCF
**Arc:** Ownership bundle — four deferred-work entries (write-side `:OWNS` writers, Group's
declaration, the missing `User.uid` index, the Askesis read-side P1) taken together as facets
of one root. This ADR is the read half; ADR-086 is the write half.
**Related:** ADR-086 (universal `:OWNS` + `ATTENDS` attendance), ADR-038 (content sharing),
`/docs/patterns/OWNERSHIP_VERIFICATION.md`, `/docs/architecture/SEARCH_ARCHITECTURE.md`
§ Ownership Scoping.

> Contract numbering note: the arc contract drafted these as "ADR-084/ADR-085"; ADR-084 was
> already taken (compact font-size tokens), so they shipped as ADR-085/ADR-086.

## Context

Ownership is *declared* in three places — the denormalized `user_uid` property, the
`(User)-[:OWNS]->` edge, and DomainConfig's `SearchVisibility` — and until this arc it was
*enforced* in only one composition point, `build_search_visibility_clause()`
(`adapters/persistence/neo4j/query/cypher/crud_queries.py:264`), reached only via SearchRouter
strategies and route-mediated `verify_ownership` checks. Everything else that reads on behalf
of a user — service-to-service by-UID fetches, relationship traversals, nested projections —
either threads no user at all or trusts the caller to have checked.

A census (2026-08-21, re-verified per site) found seven read-side gaps where a user-facing
read path can return another user's rows (G1–G7 below). None is exploitable through the main
search surfaces — those are scoped — but each is a latent cross-user disclosure the moment a
new caller wires through it.

The alternative designs — scope `CrudOperationsMixin.get()` itself repo-wide, or leave
enforcement to per-route discipline — were both rejected: the first forces a `user_uid`
parameter onto genuinely internal mechanics (ingestion reconciliation, event handlers,
post-verification re-reads) and turns every internal read into a policy decision; the second
is the status quo that produced the census.

## Decision

### 1. Two chokepoints, one floor

Every read performed **on behalf of a user** passes through exactly one of two enforcement
chokepoints:

| Chokepoint | Mechanism | Serves |
|---|---|---|
| **Visibility clause** | `build_search_visibility_clause()` composes the audience predicate from the domain's `SearchVisibility` declaration | All SearchRouter strategies (text/tags/graph/faceted) **and** audience-aware by-UID reads via `get_visible_to_user` |
| **`verify_ownership`** | `BaseService.verify_ownership(uid, user_uid)` (and the standalone-service implementations of the same contract) — 404-not-403 semantics | Route-mediated access: the route verifies, then acts |

This is the **floor**, not a ceiling: a read that passes neither chokepoint and returns
user-owned data to a user-facing caller is a defect, even when today's callers happen to be
safe. (One shape is deliberately outside the chokepoints because it decides no audience
question: self-anchored reads of the requesting user's own subgraph — defined precisely in
§4.)

### 2. `get_visible_to_user` is THE audience-aware by-UID read

`UniversalNeo4jBackend.get_visible_to_user(uid, user_uid, visibility)`
(`adapters/persistence/neo4j/_crud_mixin.py:309-359`, declared on `CrudOperations[T]` in
`core/ports/base_protocols.py:495`) is promoted from a single-caller convenience
(`ExerciseService`, `core/services/exercises/exercise_service.py:356`) to the canonical
service-to-service by-UID read. Its contract:

- Composes the same `build_search_visibility_clause()` the search strategies use, so a direct
  read and a search of the same domain agree **by construction**, not by two hand-maintained
  policies.
- Not-found and not-visible are the same outcome (`Result.ok(None)`) — the 404-equivalent
  refusal of OWNERSHIP_VERIFICATION.md, preserved below the route layer.
- The *domain's own declaration* decides the scoping: a `PUBLIC` domain (curriculum) yields no
  predicate and the read is deliberately as open as `get()`. Callers pass the domain's
  `search_visibility`, never a literal chosen at the call site.
- The publication gate is deliberately NOT applied (`apply_publication_gate=False`) — drafts
  are *unlisted* (a discovery concern), not forbidden by UID.

### 3. Legality rules for bare `get()`

`CrudOperationsMixin.get(uid)` stays unscoped, and its signature does not change. A bare
`get()` is legal ONLY as internal mechanics:

1. **Post-verification:** a chokepoint already ran for this uid in the same request path
   (e.g. `verify_ownership` at the route, then `get()` inside the service call it guards).
2. **Not on behalf of a user:** system reads where no requesting user exists — ingestion
   reconciliation, event-handler enrichment, startup checks, admin diagnostics behind
   `@require_admin`.
3. **Structurally public domains:** reads of domains whose declaration is `PUBLIC`, where
   `get_visible_to_user` would compose no predicate anyway. Passing the declaration is still
   preferred for uniformity; it is not required.

A `get()` whose uid arrives from user input with no prior chokepoint in the path is, by
definition, one of the gaps in §5 — the fix is routing through a chokepoint (usually
`get_visible_to_user`), never widening `get()`.

### 4. No third mechanism — ever

Nothing may add a third **audience-policy** mechanism. New read surfaces compose
`build_search_visibility_clause()` or call `verify_ownership`/`get_visible_to_user`. A
hand-rolled audience predicate or an ad-hoc "is this yours?" check is a defect **even when
its logic is correct** — the entire value of the contract is that audience policy has two
auditable homes, and drift between copies is how the census gaps appeared in the first place.

**Self-anchored reads are not a third mechanism.** The user-context queries
(`user_context_queries.py` — MEGA-QUERY/CONSOLIDATED) anchor on the requesting user's own
node and traverse that user's subgraph; they decide no audience question, so there is no
policy to centralize. Their obligation is different: **every projection must stay tied to
the anchor** (`user.uid`). A nested projection that escapes the anchor is a scoping bug
*within* a self-anchored read — G2 below is exactly this — and its fix re-ties the
projection to the anchored user (the shape the sibling projections already use), restoring
the anchor rather than adding a predicate home. A *new* read surface may be self-anchored
only when it reads exclusively the requesting user's own data; the moment it can return
another user's rows it is an audience read and belongs to a chokepoint.

(The one existing composition-adjacent rule stands unchanged: `has_user=True` is fail-closed
convention everywhere the clause composes — deriving `has_user` from `user_uid is not None`
turns a null uid into an unscoped query. See SEARCH_ARCHITECTURE § Ownership Scoping.)

### 5. The gap census (G1–G7) — the closure worklist

Verified 2026-08-21 (file:line as of that date). Closing these is the arc's read-side PR;
each closure gets a pinning test whose fixtures mirror writer shapes.

| # | Gap | Where | Shape |
|---|---|---|---|
| G1 | Askesis bundle fetch (the P1) | `core/services/askesis/context_retriever.py:431` has `user_uid` in frame; `_fetch_entities_by_uid` (`:750-775`) calls bare `service.get(uid)` per uid | Thread `user_uid` down; replace with `get_visible_to_user` (curriculum stays visible via PUBLIC, activities scope OWNER_ONLY) |
| G2 | MEGA-QUERY nested projections | `adapters/persistence/neo4j/user_context_queries.py:829` (and sibling prereq projections `:816/:827`) project PS-linked Habits with no owner predicate — vs `:1104`/`:1134` which carry `user_uid = user.uid` | Re-tie the projection to the anchored user (`user_uid = user.uid`, the sibling shape) — an anchor-escape fix inside a self-anchored read (§4), not a new predicate home. *Closure truth-up (PR-3): the user-owned escapes were the `BUILDS_HABIT` (`:829`) and `ASSIGNS_TASK` (`:843`) projections — both re-tied. The `:816`/`:827` prereq projections target ownerless PathSteps (shared curriculum), so no owner predicate applies there by design.* |
| G3 | Relationship traversal | `_search_raw_mixin.py:116` `relationship_traversal_raw` and `core/services/mixins/search_operations_mixin.py:312` `get_by_relationship` take no `user_uid`/visibility | Add `user_uid` + visibility composition; update events/principles search-service callers |
| G4 | Lateral targets | `core/services/lateral_relationships/lateral_relationship_service.py:256` returns targets unfiltered (anchor check exists at `:412`) | Filter returned targets by the caller's audience |
| G5 | `build_array_contains_query` | `crud_queries.py:678` lacks the visibility/user params its sibling `build_array_any_match_query` (`:737`) has; caller `search_array_field` is dormant | Add the params; resolve the dormant caller's staged status explicitly |
| G6 | Insight by-UID | `core/services/insight/insight_store.py:161` `get_insight_by_uid` takes no `user_uid` (sibling `:263` does) | Adopt the sibling's shape |
| G7 | Factory search route | `adapters/inbound/route_factories/crud_route_factory.py:703-751` `_register_search_route` never calls `require_authenticated_user` and passes no user to the handler | Authenticate + thread `user_uid` (or route via SearchRouter) |
| G8 | Askesis chunk (RAG) retrieval — found after the census, 2026-08-30 | `core/orchestrator/search_router.py` `retrieve_scoped_chunks` discarded its `user_uid` (`del user_uid`, "reserved" since canon P3 #615) and `VectorSearchBackend.semantic_search_chunks` composed no audience clause, while the chunk index held non-private knowledge UserEntries from 2 users (303 of 998 chunks) — any user's Askesis answer could ground in any other user's notes | **Closed the same day:** the backend composes the clause per parent on EVERY chunk query — `viewer_uid` → published curriculum + own UserEntry (the `OWNER_ONLY` predicate via `build_search_visibility_clause`, plus the private gate); `None` → published curriculum only. Pinned by `tests/integration/test_chunk_retrieval_visibility.py` (real index, two users) |

Adjacent, closed with the census: `IntelligenceRouteFactory` only *warns* when a USER_OWNED
domain is wired without an ownership service (`intelligence_route_factory.py:240-244`; the
silent skips it enables sit at `:318`/`:371`) — becomes fail-fast per the fail-fast dependency
philosophy.

## Consequences

- Cross-user disclosure stops being a per-call-site discipline and becomes a two-point audit:
  grep the clause's composers and `verify_ownership`'s callers, and everything else must be
  provably internal.
- Service-to-service reads gain a uniform idiom (`get_visible_to_user` + the domain's
  declaration) instead of each service deciding whether `get()` is safe here.
- Bare `get()` survives — internal mechanics stay simple, and no repo-wide signature change
  lands.
- The census is a bounded worklist, not an open hunt: new gaps can only enter through code
  that violates §4, which review can check locally.
- `SearchRouter`'s existing refusals (OWNER_ONLY without a user; default-deny for undeclared
  domains) are unchanged — this ADR generalizes their principle to non-search reads.

## Follow-ups

- Gap closures G1–G7 + the fail-fast conversion land in the arc's read-side PR (arc contract
  PR-3), each with a pinning test.
- The write-side ratification, residue collapse, and attendance design are ADR-086 (arc
  contract PR-2); the Group declaration fix and `User.uid` uniqueness constraint follow in
  PR-4.
