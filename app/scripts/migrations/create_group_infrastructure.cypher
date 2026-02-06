// ============================================================================
// ADR-040: Group Infrastructure Migration
// ============================================================================
// Creates constraints and indexes for Group nodes.
//
// Run: cat scripts/migrations/create_group_infrastructure.cypher | cypher-shell -u neo4j -p <password>
// Or: Execute each statement in Neo4j Browser
// ============================================================================

// Unique constraint on Group.uid
CREATE CONSTRAINT group_uid_unique IF NOT EXISTS
FOR (g:Group) REQUIRE g.uid IS UNIQUE;

// Index for fast lookup by owner (teacher listing their groups)
CREATE INDEX group_owner_idx IF NOT EXISTS
FOR (g:Group) ON (g.owner_uid);

// Index for active groups filter
CREATE INDEX group_active_idx IF NOT EXISTS
FOR (g:Group) ON (g.is_active);
