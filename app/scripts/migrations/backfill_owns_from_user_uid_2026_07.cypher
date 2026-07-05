// Migration: Backfill :OWNS edges from the user_uid property (2026-07)
// =====================================================================
// Problem: the bulk ingestion engine stamped `user_uid` on vault-authored
//   activity entities (Task/Event/Choice/Habit/Principle files in the content
//   vault, batch of 2026-07-04) but never wrote the (User)-[:OWNS]->(entity)
//   edge — only the UserEntry pipeline and Group ingestion wrote OWNS. Every
//   OWNS-consuming read path (faceted search's ownership MATCH,
//   get_user_entities, the ":OWNS canonical" contract) silently missed those
//   nodes: /search filtered to Principles returned NOTHING for the owner.
//
// Relationship to backfill_user_uid_to_owns_owner_2026_06.cypher (the June
//   migration, which went the OPPOSITE direction — property from edge):
//   both enforce the SAME invariant, `user_uid property == :OWNS owner`.
//   In June the :OWNS edge existed and was authoritative, so the property was
//   rewritten to match it. Here the property is the ONLY signal that exists
//   (the ingestion write-path bug meant no edge was ever created), so the
//   edge is restored from the property. The live write paths now hold the
//   invariant on both sides: CRUD via _user_entity_mixin auto-OWNS, and bulk
//   ingestion via the OWNS clause in build_node_upsert_template (this PR).
//
// SAFE:
//   - MERGE is idempotent — already-consistent nodes gain nothing; Phase 1b
//     only deletes edges whose owner disagrees with the user_uid property
//     (single-owner invariant; Kody #514 finding accepted + Mike's ruling).
//   - Only nodes whose user_uid matches an EXISTING :User node are touched;
//     a dangling user_uid creates neither an edge nor a stub User.
//   - `user_uid = "user_system"` is explicitly excluded: per the June
//     migration, ownerless system catalog content is legitimately
//     system-owned-by-property, with no :OWNS edge (no :User node with that
//     uid exists; the exclusion is documented belt-and-suspenders).
//   - Curriculum content (Exercise/Ku/PathStep/LearningPath) carries no
//     user_uid at ingestion (the validator forces ownerless
//     `scope: curriculum` exercises), so it is untouched by construction.
//   - Edge properties mirror the CRUD path's create_user_relationship
//     defaults (created_at / last_accessed / access_count / is_active).
//
// CRITICAL: Back up the database before running.
//
// Run phases in order. Phase 2 is a validation query — expected result: 0.

// --------------------------------------------------------------------
// Phase 1: Backfill — create the missing :OWNS edge for every Entity
// whose user_uid names an existing User that does not yet own it.
// --------------------------------------------------------------------
MATCH (e:Entity)
WHERE e.user_uid IS NOT NULL AND e.user_uid <> 'user_system'
MATCH (owner:User {uid: e.user_uid})
WHERE NOT (owner)-[:OWNS]->(e)
MERGE (owner)-[o:OWNS]->(e)
  ON CREATE SET
    o.created_at = toString(localdatetime()),
    o.last_accessed = toString(localdatetime()),
    o.access_count = 0,
    o.is_active = true
RETURN count(o) AS owns_edges_created;

// --------------------------------------------------------------------
// Phase 1b: Single-owner enforcement — delete :OWNS edges from users
// OTHER than the user_uid property owner. Here (unlike the June migration,
// where the edge was authoritative) the property is authoritative: the live
// write paths now keep property == edge on both doors, so any residual
// multi-owner edge is an out-of-band artifact (e.g. the bare propertyless
// PR-3-walk-era edges found 2026-07-05) whose survivor must be the property
// owner. Scoped to entities that HAVE a user_uid — ownerless curriculum
// content and Exercise owner_uid ownership are untouched.
// --------------------------------------------------------------------
MATCH (stale:User)-[r:OWNS]->(e:Entity)
WHERE e.user_uid IS NOT NULL AND e.user_uid <> 'user_system'
  AND stale.uid <> e.user_uid
DELETE r
RETURN count(r) AS stale_owns_edges_removed;

// --------------------------------------------------------------------
// Phase 2: Validation — expected result: 0 / 0
// missing_owns_edges: a user_uid-bearing Entity whose owner exists still
// lacks its :OWNS edge. stale_owns_edges: an :OWNS edge from a user other
// than the property owner survived (single-owner invariant).
// --------------------------------------------------------------------
MATCH (e:Entity)
WHERE e.user_uid IS NOT NULL AND e.user_uid <> 'user_system'
OPTIONAL MATCH (owner:User {uid: e.user_uid})
WITH e, owner
OPTIONAL MATCH (other:User)-[:OWNS]->(e)
WITH e, owner, collect(other.uid) AS edge_owners
RETURN
  sum(CASE WHEN owner IS NOT NULL AND NOT e.user_uid IN edge_owners THEN 1 ELSE 0 END)
    AS missing_owns_edges,
  sum(CASE WHEN any(o IN edge_owners WHERE o <> e.user_uid) THEN 1 ELSE 0 END)
    AS stale_owns_edges;
