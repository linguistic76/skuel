---
title: "ADR-085: Ownership Read-Enforcement Contract"
updated: 2026-10-02
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

## Related Skills

For implementation guidance, see:
- [@security](../../.claude/skills/security/SKILL.md)
- [@skuel-search-architecture](../../.claude/skills/skuel-search-architecture/SKILL.md)

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
(`adapters/persistence/neo4j/_crud_mixin.py:330`, declared on `CrudOperations[T]` in
`core/ports/base_protocols.py:499`) is promoted from a single-caller convenience
(`ExerciseService`, `core/services/exercises/exercise_service.py:351`) to the canonical
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

> **2026-09-25 — Amended by [ADR-088](ADR-088-submit-and-share.md) (Submit & Share arc, PR 5).**
> Callers pass the domain's `read_visibility` (`DomainConfig.get_read_visibility()`, default:
> the search declaration), not `search_visibility`. A direct read and a search still agree by
> construction for every domain that declares no `read_visibility`; UserEntry diverges by
> declaration — it opens for its audience (`OWNER_OR_AUDIENCE`: the owner arm OR the audience
> fragment of ADR-088 §3) and searches owner-only, because a search row carries the teacher's
> verdict and the processed body. Same clause builder, one more declared member, the same
> chokepoint: not a third mechanism (§4).

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

> **2026-10-01 — entity-anchored traversals (G9).** The same obligation holds for a read
> anchored on an *entity* whose access a chokepoint has already decided (the route's
> `verify_ownership` on the center uid): the path-aware neighbourhood producer
> (`build_domain_context_with_paths`) keeps every node on a path tied to the anchor's owner —
> the owner's nodes and shared content, ownership read in all three spellings, a `:User` node
> its own owner. It decides no audience question (a share link does not widen it, and it
> takes no viewer), so it is an anchor re-tie in the statement, not a predicate home. A
> traversal that needs a *viewer's* audience — "what may this user see around a shared
> Ku" — is an audience read and belongs to a chokepoint.

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
| G9 | Path-aware neighbourhood — found after the census, 2026-10-01 | `adapters/persistence/neo4j/query/cypher/semantic_queries.py` `build_domain_context_with_paths` — the one producer under `get_cross_domain_context` (all six activity dashboards/insights) and `query_with_intent` (`GraphContext`, full property maps) — walked `(center)-[*1..depth]-(related)` undirected with no owner predicate. Two users who each link their own entity to one shared Ku are two hops apart, every edge on the path one its own owner may write: the reader returned the other user's nodes (uid + title in the shared-neighbour buckets; the whole property map on the intent reader). On that path the consumers traced dropped the rows before a response (typed contexts read no shared-neighbour bucket; knowledge readers filter by `entity_type`; the context route returns counts), so what left through a route was a count. Across a *direct* cross-user edge the dashboards returned the far node's uid and title — and a link door that does not verify its target writes one (`link_goal_to_knowledge` accepted another user's task as the knowledge; measured) | **Closed the same day:** the statement ties every node on a path to the center's owner (§4, entity-anchored). Pinned by `tests/integration/test_neighbourhood_owner_scope.py` (real graph, two users, six domain vocabularies, each ownership spelling) |
| G10 | Orchestration routes — found after the census, 2026-10-01 | `adapters/inbound/orchestration_routes.py`: nine routes took a goal or habit uid from the query string and handed it to a service whose read is a bare `get` — the §3 gap by definition, a uid from user input with no chokepoint in the path. Measured over real HTTP with two users: another user's goal uid returned its title (task templates, success prediction) and a habit uid its title and description (event templates); `/goals/generate-tasks?uid=…&auto_create=true` declared no method, so a GET reached it, and it created tasks owned by the goal's owner; and the three goal-analytics routes (`predict-success`, `habit-impact`, `risk-assessment`) called no `require_authenticated_user`, so the composed app answered them with no session at all | **Closed the same day:** every uid-taking route runs `verify_entity_ownership` before its service (the facade reaches each factory as an `OwnershipVerifier`, and a factory refuses to register without one); all fourteen routes require a session; the three that write are POST behind `@csrf_protected`. Pinned by `tests/integration/routes/test_orchestration_route_ownership.py` (real HTTP, two users) |
| G11 | Link doors — found after the census, 2026-10-01 | `UnifiedRelationshipService.create_relationship` wrote whatever edge its registry key named between any two uids. The three `link-knowledge` doors skip the route's target check (`CrossDomainLinkSpec.target` is unset for a Ku), and `EventsService.update_event` verified the event only. Measured over real HTTP with two users: `POST /api/{goals,habits,principles}/link-knowledge` accepted another user's Task as `knowledge_uid` (200, edge written — while a uid that names nothing answered 400, an existence oracle for any uid); `POST /api/events/update` wrote `CELEBRATES_GOAL` to another user's goal and `REINFORCES_HABIT` to another user's habit, and to a Task. A WRITE gap, registered here for what reads the edge back: the Events list, detail and edit pages rendered the linked goal's and habit's title, and the rich user context carried a linked node's uid and title (`entities_rich`' graph context, `goal_knowledge_required`) — another user's text, reached through the caller's own entity. `POST /api/principles/link?uid=` could name no far end at all — a query parameter replaces a same-named JSON body field, and both were `uid` — so it linked a principle to itself | **Closed the same day, at the write:** the service admits the far end of every edge it writes — it exists, is the kind the caller declares (`far_end`, required), and is shared content or owned by the source's owner, read from the source node — and refuses all three as not found (`core/services/mixins/link_edge_guard.py`); the Events update admits both far ends before its first write; the principle link's body names its target `target_uid`. Pinned by `tests/integration/routes/test_link_door_far_end.py` (real HTTP, two users) and `tests/unit/services/test_link_writer_census.py` (every `create_relationship` / `create_relationships_batch` call site under `core/services/` names its admission). **Open:** the readers above still take a link edge at face value, so an edge another door writes (a personal-vault file) is rendered the same way; and `InteractionService.create_interaction` admits none of an Interaction's context uids |

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
