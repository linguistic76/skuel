// ============================================================================
// Migration: event PRACTICES_KNOWLEDGE → APPLIES_KNOWLEDGE — 2026-06
// ============================================================================
//
// Context: ADR-046. The shadow `PRACTICES_KNOWLEDGE` edge — written only by
// `create_study_session` and read only by askesis + `get_practicing_event_uids`
// — is removed. Everything event→knowledge now uses the single `APPLIES_KNOWLEDGE`
// edge (registry / MEGA-QUERY / facade). Pre-existing study-session edges must be
// backfilled so their knowledge stays visible to the MEGA-QUERY (UserContext /
// substance / ZPD) and the Ku→events reverse lookup.
//
// Run this against the active Neo4j instance BEFORE deploying the updated code:
// the new readers match only `APPLIES_KNOWLEDGE`, so any remaining
// `PRACTICES_KNOWLEDGE` edge disappears from KU application lookups until migrated.
//
// Plain Cypher (no APOC, per ADR-044). `MERGE` makes it idempotent and dup-safe;
// `PRACTICES_KNOWLEDGE` edges carry no properties, so none are lost.
// ============================================================================


// ----------------------------------------------------------------------------
// Step 1: Backfill — re-point each PRACTICES_KNOWLEDGE edge to APPLIES_KNOWLEDGE
// ----------------------------------------------------------------------------

MATCH (e:Event)-[r:PRACTICES_KNOWLEDGE]->(k:Entity)
MERGE (e)-[:APPLIES_KNOWLEDGE]->(k)
DELETE r
RETURN count(*) AS practices_edges_migrated;


// ----------------------------------------------------------------------------
// Step 2: Verification
// ----------------------------------------------------------------------------

// Confirm no PRACTICES_KNOWLEDGE edges remain
MATCH (:Event)-[r:PRACTICES_KNOWLEDGE]->(:Entity)
RETURN count(r) AS practices_remaining;
// Expected: 0
