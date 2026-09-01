---
updated: 2026-08-14
---

# user_uid ↔ :OWNS Ownership-Signal Reconciliation

**Date:** 2026-06-06
**Status:** Implemented
**Scope:** The denormalized `user_uid` **property** on owned `:Entity` nodes — realigned to its
authoritative `(User)-[:OWNS]->(entity)` edge. A stale-data fix; no code/read-path change.

## Problem

SKUEL carries ownership as **two signals**:

1. The `(User)-[:OWNS]->(entity)` **edge** — authoritative. `DomainConfig.user_ownership_relationship`
   is `OWNS`; the unified faceted-search path (`faceted_search_raw`), `get_user_entities`, ownership
   verification, and the GDPR cascade all traverse it.
2. The `user_uid` **property** on the node — a denormalized convenience. Every
   `UniversalNeo4jBackend.find_by(user_uid=…)` caller (68 sites across analytics, intelligence, and
   the dual-track calculators) matches on this property, **not** the edge.

These are meant to agree, and the live write-paths keep them in sync:
`_user_entity_mixin` auto-creates the `:OWNS` edge from the entity's own `user_uid`, and the
PS-engagement spawn (`_spawn_orchestrator._build`) sets `user_uid=student_uid`.

But onboarding/demo seed content ingested on **2026-04-01** was `:OWNS`-linked to a real user while
keeping `user_uid="user_system"`. For those nodes the two signals **disagreed**: edge-based reads saw
them, property-based `find_by(user_uid=…)` did not — silently dropping the user's entities from
analytics and intelligence.

Observed on the local dev DB: **11 nodes** owned by `user_linguistic76` (3 task, 2 each
goal/habit/event/choice) carried `user_uid="user_system"`. No live write-path can reproduce this —
it is one-time stale seed data.

## Decision

The `:OWNS` edge is canonical; the property is denormalized from it. Since the live write-paths
already maintain `property == owner`, the fix is to **backfill the property to match the `:OWNS`
owner** — not to refactor the 68 property-based read sites. Ownerless system catalog/template nodes
(`user_uid="user_system"` with no `:OWNS` edge) are legitimately system-owned and are left untouched.

## Data migration

Run once per environment (after backup):

```bash
# Phase 1 backfills; Phase 2 validates (expect 0). The MCP read tool is read-only,
# so apply the write via cypher-shell in the Neo4j container:
docker exec skuel-neo4j cypher-shell -u neo4j -p "$PW" \
  -f /path/to/scripts/migrations/backfill_user_uid_to_owns_owner_2026_06.cypher
```

`scripts/migrations/backfill_user_uid_to_owns_owner_2026_06.cypher` sets `e.user_uid = owner.uid` for
every `(owner:User)-[:OWNS]->(e:Entity)` whose property diverges from — or is null for — its owner.
The explicit `IS NULL` arm matters: `owner.uid <> null` evaluates to null and `WHERE` keeps only true
rows, so a null property would otherwise be skipped (and the validation phase would falsely report 0).
Idempotent (re-run is a no-op). Verify:

```cypher
MATCH (o:User)-[:OWNS]->(e:Entity)
WHERE e.user_uid IS NULL OR o.uid <> e.user_uid RETURN count(e)   // expect 0
```

Applied to the local dev DB on 2026-06-06: **11 nodes** backfilled, 0 mismatches remaining,
38 ownerless system catalog nodes correctly untouched.

## Guard

`tests/integration/migrations/test_backfill_user_uid_to_owns_owner.py` seeds a diverging node, a
consistent node, and an ownerless catalog node; asserts the diverging node is realigned, the catalog
node is untouched, the global `property == :OWNS-owner` invariant holds, and the migration is
idempotent.

## Related

- `docs/migrations/USER_UID_CANONICALIZATION_2026-05.md` — sibling fix for the user-id *format*
  (colon → underscore). This fix addresses the *value* (property vs edge), not the format.
