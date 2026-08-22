---
title: "ADR-086: Universal :OWNS Ratified; Attendance Is ATTENDS"
updated: 2026-08-21
status: accepted
category: decisions
tags: [adr, decisions, ownership, owns, attends, events, graph-schema, relationships]
related: [ADR-026, ADR-038, ADR-040, ADR-085]
related_skills: [security, neo4j-cypher-patterns, activity-domains]
---

# ADR-086: Universal `:OWNS` Ratified; Attendance Is `ATTENDS`

**Status:** Accepted — founder-ratified 2026-08-21
**Date:** 2026-08-21
**Deciders:** MCF
**Arc:** Ownership bundle — the write half. ADR-085 is the read-enforcement half.
**Related:** Supersedes ADR-026's registry-schema claim (the per-domain
`ownership_relationship` declaration). Related to ADR-038 (sharing), ADR-040 (assignment),
ADR-085 (read contract), `/docs/patterns/OWNERSHIP_VERIFICATION.md`.

> Contract numbering note: the arc contract drafted these as "ADR-084/ADR-085"; ADR-084 was
> already taken (compact font-size tokens), so they shipped as ADR-085/ADR-086.

## Context

ADR-026's registry schema gave every domain an `ownership_relationship: RelationshipName |
None` declaration (`core/models/relationship_registry.py:332`), and the enum grew a per-domain
family to fill it: `HAS_TASK`, `HAS_GOAL`, `HAS_HABIT`, `HAS_EVENT`, `HAS_CHOICE`,
`HAS_PRINCIPLE`, `HAS_KU`, plus `MADE_REFLECTION`. Reality diverged: every production write
door writes the universal `(User)-[:OWNS]->(entity)` edge, and the per-domain family became
paper.

Measured on the live graph (AuraDB `d2d160c4`, 2026-08-21): **199 `:OWNS` edges; zero**
`HAS_TASK`/`HAS_GOAL`/`HAS_EVENT`/`ATTENDS`/`MADE_REFLECTION` relationships of any kind.
`get_recent_activities` traversing `HAS_TASK`/`HAS_GOAL` legs had matched nothing since the
initial commit (#1116). The only code path that could still write a `HAS_*` edge is the
generic interpolation in `_user_entity_mixin.py:178`, reached via
`UnifiedRelationshipService.create_user_relationship` from four "gravity" writers — all with
zero production callers of their own. Meanwhile the generated `GRAPH_CONTRACT.yaml` traits the
six paper edges "ownership" while `OWNS` — the edge actually carrying it — has no trait
(`is_ownership_relationship()`, `core/models/relationship_names.py:556-566`, lists the six and
excludes `OWNS`).

The same arc needed an answer for Events attendance: the staged attendee methods
(`core/services/events/_orchestration_mixin.py` — `get_event_attendees` `:100`, `add_attendee`
`:113`, `remove_attendee` `:151`) rode the paper channel, writing `HAS_EVENT` as if a second
user could "own" someone else's event — ownership semantics forced onto what is actually
membership/consent semantics.

## Decision

### 1. Universal `:OWNS` is ratified as THE ownership edge

The accreted reality becomes the contract. `(User)-[:OWNS]->(entity)` is the single ownership
edge for every user-owned entity. The **four write doors** (file:line as of 2026-08-21):

1. **Generic CRUD create** — `_crud_mixin.py:157-168`: the `MERGE (owner)-[:OWNS]->(n)` is
   composed into the same statement as the node CREATE; the owner is `MATCH`ed, so a
   `user_uid` naming a non-existent User aborts the whole write.
2. **Ingestion bulk upsert** — `bulk_upsert_backend.py:99-108`: `MERGE` plus a stale-owner
   guard that deletes any previous owner's edge — single-owner invariant.
3. **UserEntry** — `_user_entry_crud_mixin.py:128-129`: strictest door — `WHERE n.user_uid =
   owner.uid` guards the MERGE against an ownership race.
4. **Hand-written domain writers** — Exercise (`backends/exercise_backends.py:253-269`,
   invoked warn-only from `exercise_service.py:211-216` — property lands even if the edge
   write fails), Group (`backends/collab_backends.py:51`), FormSubmission
   (`backends/forms_backends.py:561`).

**The invariant:** wherever both exist, `user_uid` property `== :OWNS` owner. Doors 1–3
enforce it structurally (same statement / guarded MERGE); door 4 is the known warn-only soft
spot (documented in OWNERSHIP_VERIFICATION.md § Entity Requirements). `owner_uid` domains
(Exercise, Group) carry edge + `owner_uid` property instead of `user_uid`.

**Sanctioned consequence — property-scoped reads are sound.** The standing ruling that
`find_by(user_uid=…)` and other property predicates are legitimate (distinct from `:OWNS`
traversal, by ruling) rests on this invariant: search scopes by property (the August 2026
faceted convergence, SEARCH_ARCHITECTURE § Ownership Scoping), while the edge remains the
signal for cascade deletes, sharing checks, and the adapter Cypher that traverses it
(MEGA-QUERY/CONSOLIDATED anchors `user_context_queries.py:94/:1294`, `get_user_entities`
`_user_entity_mixin.py:270`, GDPR cascade `user_backend.py:444`, one SCOPE_AWARE disjunct).

### 2. The paper residue collapses

Deleted (executed by the arc's mechanical PR — arc contract PR-2; each site re-enumerated
there before deletion):

- Registry: the `ownership_relationship` field (`relationship_registry.py:332`) + its 16
  per-config values; `USER_CONFIG`'s six `HAS_*` + `MADE_REFLECTION` relationship definitions
  (`:1501-1551`).
- Service channel: `UnifiedRelationshipService.create_user_relationship` (`:334-373`) and
  `delete_user_relationship` (`:375-401`). (Note the pair's asymmetry: create routed to the
  backend's generic `create_user_relationship`; delete routed to plain
  `backend.delete_relationship` — the backend's `delete_user_relationship` was already
  caller-less.)
- The four gravity writers: `goals_service.py:651`, `habits/_orchestration_mixin.py:150`,
  `principles/_gravity_mixin.py:59`, `events/_orchestration_mixin.py:71`.
- Backend generic pair: `_user_entity_mixin.py` `create_user_relationship` (`:126-198`, the
  one interpolation that could write a `HAS_*` edge) + `delete_user_relationship`
  (`:418-466`), with their `UserEntityRelationshipOperations` protocol declarations.
- Enum members: `HAS_TASK`, `HAS_GOAL`, `HAS_HABIT`, `HAS_PRINCIPLE`, `HAS_CHOICE`, `HAS_KU`,
  `MADE_REFLECTION` (and `HAS_EVENT` once the attendee retarget removes its last reference).
- `is_ownership_relationship()` rewritten to `{OWNS}` — the generated contract finally traits
  the edge that carries ownership.

Explicitly **untouched**: `create_user_relationships` (plural,
`relationship_backend_protocols.py:72`) is a different, live method; the
`HAS_TASK_TEMPLATE`-family template edges are a distinct, live family; and the service-layer
`DomainConfig.user_ownership_relationship` (`core/services/domain_config.py:161`) is a
**different field** from the registry's — `get_search_visibility()` (`:238-252`) tests only
its None-ness to derive OWNER_ONLY vs PUBLIC. Do not conflate the two when working near
either.

**Deferred design note — adoption/gravity.** The gravity writers expressed "this user has
pulled this entity into their orbit" (adoption, engagement) — a semantic that is *not*
ownership. If SKUEL wants it later, it returns as its own named edge with its own design,
never by resurrecting the `HAS_*` family.

### 3. Attendance is `ATTENDS` — the designed shape

Staged design, **not wired in this arc** (phase directive: no routes, no UI). No writer may
emit `ATTENDS` before this shape lands in code; the attendee method triple is retargeted onto
it and stays registered as staged work in the bloat detector's PLANNED tier.

**Edge shape:**

```cypher
(User)-[:ATTENDS {joined_at, role, added_by, status}]->(Event)
```

- Idempotent `MERGE`, `ON CREATE SET joined_at` only — the `GroupBackend.add_member` shape
  (`collab_backends.py:94-128`) applied to attendance. Re-adding never rewrites `joined_at`.
- `ATTENDS` is already a `RelationshipName` member (`relationship_names.py:171`) — SKUEL030/
  CYP011 clean.

**Consent state machine** (`status: invited | accepted | declined`):

| Actor | May do |
|---|---|
| User adding themself | Create with `status: accepted` (self-add is consent) |
| Organizer (event owner) | Create with `status: invited` — **only** `invited`; an organizer can never write acceptance for someone else. May revoke (delete) a still-`invited` edge |
| The target user | The only actor who transitions `status` (`invited → accepted / declined`); may always delete their own `ATTENDS` edge, whatever its status |

The **actor is always resolved from the auth layer** (`current_user`), never from the request
body — `AddAttendeeRequest`/`RemoveAttendeeRequest` carry the *target*, not the actor.
`added_by` records the acting user at create.

**Creator auto-attends:** event creation writes `:OWNS` + the creator's own
`ATTENDS {status: accepted}` edge — the organizer is an attendee of their own event. Wired
when the attendee surface ships, not before.

**Visibility — designed now, implemented at wiring:** Events stay `OWNER_ONLY` until the
attendee surface ships. The same PR that wires the surface adds a `SearchVisibility` member
(working name `OWNER_OR_ATTENDEE`) rendering:

```cypher
(n.user_uid = $user_uid OR EXISTS {(:User {uid: $user_uid})-[:ATTENDS]->(n)})
```

fail-closed with no user (no user ⇒ no predicate emitted ⇒ refused upstream, per the
`has_user=True` convention). Whether accepted-only attendance suffices for visibility, or
`invited` should also see the event, is decided at wiring — the invite flow needs the invitee
to *see something*, which may be a dedicated invite surface rather than search visibility.

**GDPR / deletion semantics:**

- Attendee side is free: the hard-delete cascade's `DETACH DELETE u` removes the departing
  user's `ATTENDS` edges with them. No new work.
- Soft delete leaves ghost attendee UIDs: attendee reads must filter to live users (a
  wiring-PR obligation, recorded here so the read is designed with the filter from day one).
- **Parked, by name (open — NOT solved here):** an event whose organizer is hard-deleted
  while living attendees hold `ATTENDS` edges. The GDPR cascade
  (`user_backend.py:440-450`) DETACH-DELETEs all `:OWNS`-owned nodes, silently destroying the
  event under its attendees. Options (transfer to an attendee, orphan-with-tombstone, cascade
  as today) are deliberately not chosen in this arc.

**Wiring-PR notes** (obligations recorded, not implemented): `max_attendees` enforcement at
the add door; `role` becomes an enum (at minimum organizer/attendee), not a free string.

### 4. `User.uid` gains a uniqueness constraint

Measured live: 6 users, zero duplicates — the constraint builds cleanly. It doubles as the
index every edge-anchored ownership read currently lacks (`EXPLAIN` on the `:OWNS` anchor
today = `NodeByLabelScan`; only email + pairing_code_hash indexes exist on `:User`). Applied
via startup DDL (`neo4j_schema_manager.py`) in the arc's final PR; AuraDB Free permits schema
DDL (only user-admin Cypher is refused).

## Consequences

- The graph contract stops lying: after regeneration, no label traits a never-written edge as
  "ownership", and `OWNS` carries the trait.
- One channel fewer: with the generic interpolation gone, every `:OWNS` edge enters through
  one of the four named doors — the invariant becomes auditable at the doors instead of
  "doors plus a generic bypass".
- Events attendance gets consent semantics instead of inherited ownership semantics; the
  staged methods stop implying a second user can own someone's event.
- ADR-026 remains authoritative for the registry's *relationship* definitions; only its
  ownership-declaration claim is superseded.
- The `owner_uid` vs `user_uid` split survives (Exercise, Group); the Group search-declaration
  fix (`ownership_property` on the service-layer DomainConfig) lands in the arc's final PR —
  see SEARCH_ARCHITECTURE § Ownership Scoping for why Group is currently unsearchable on
  purpose.

## Follow-ups

- Residue collapse + attendee retarget: arc contract PR-2 (re-enumerates every site before
  deleting; regenerates `GRAPH_CONTRACT.yaml`; repairs the round-trip and tracking tests).
- Read-side gap closures: ADR-085 §5 (PR-3).
- Group `ownership_property` + the `User.uid` constraint + arc close-out: PR-4.
- Attendance wiring (routes, UI, `OWNER_OR_ATTENDEE`, auto-attend, ghost filter,
  `max_attendees`, role enum): a future arc, on Mike's explicit decision — the surface stays
  staged until then.
