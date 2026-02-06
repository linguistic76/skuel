// ============================================================================
// ADR-040: Assignment Relationship Infrastructure
// ============================================================================
// Creates indexes for assignment-related relationships.
//
// Run: cat scripts/migrations/add_assignment_relationships.cypher | cypher-shell -u neo4j -p <password>
// Or: Execute each statement in Neo4j Browser
// ============================================================================

// Index for ReportProject scope (fast lookup of assigned projects)
CREATE INDEX report_project_scope_idx IF NOT EXISTS
FOR (rp:ReportProject) ON (rp.scope);

// Index for ReportProject group_uid (fast lookup of group assignments)
CREATE INDEX report_project_group_idx IF NOT EXISTS
FOR (rp:ReportProject) ON (rp.group_uid);

// Note: FOR_GROUP and FULFILLS_PROJECT relationships don't need separate indexes
// as they are traversed via node-based queries (Neo4j automatically indexes relationships).
