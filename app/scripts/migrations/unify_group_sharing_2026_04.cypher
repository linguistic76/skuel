// Unify Group Sharing — Retire FOR_GROUP, migrate to SHARED_WITH_GROUP
// ======================================================================
//
// ADR-053: Groups First-Class + Unified Sharing
//
// Before this migration, assigned Exercises connected to groups via
// :FOR_GROUP. ADR-053 retires FOR_GROUP in favour of :SHARED_WITH_GROUP
// (which already carries shared_at + share_version metadata and is
// entity-agnostic, so PathStep and LearningPath can share through the
// same mechanism).
//
// This migration is idempotent — re-running it after a successful run
// leaves the graph unchanged.
//
// Run:
//   cypher-shell -u neo4j -p <password> -f scripts/migrations/unify_group_sharing_2026_04.cypher

// ----------------------------------------------------------------------
// 1. Migrate every FOR_GROUP edge to SHARED_WITH_GROUP with backfilled
//    metadata. MERGE on the new edge keeps the operation idempotent.
// ----------------------------------------------------------------------
MATCH (e:Entity)-[old:FOR_GROUP]->(g:Group)
MERGE (e)-[new:SHARED_WITH_GROUP]->(g)
ON CREATE SET new.shared_at = coalesce(e.updated_at, toString(datetime())),
              new.share_version = 'original',
              new.migrated_from = 'FOR_GROUP'
DELETE old
RETURN count(new) AS migrated;

// ----------------------------------------------------------------------
// 2. Acceptance gate — must return 0.
// ----------------------------------------------------------------------
MATCH ()-[r:FOR_GROUP]->()
RETURN count(r) AS remaining_for_group_edges;
