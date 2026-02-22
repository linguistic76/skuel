// Schema Cleanup Migration - 2026-02-23
// Cleans up stale data from successive renames and migrations
// Run each statement individually via Neo4j MCP tool

// =============================================================================
// Step 1: Unify Assignment/KuProject → Exercise
// Two separate nodes with uid 'jp.transcript_default' exist as :Assignment and :KuProject.
// Keep the :Assignment node (newer updated_at), delete the :KuProject duplicate.
// =============================================================================

// 1a. Delete the HAS_KUPROJECT relationship (empty properties, older duplicate)
MATCH (u:User)-[r:HAS_KUPROJECT]->(n:KuProject)
DELETE r;

// 1b. Delete the KuProject node (older duplicate)
MATCH (n:KuProject)
DELETE n;

// 1c. Add :Exercise label to the Assignment node, remove :Assignment
MATCH (n:Assignment)
SET n:Exercise
REMOVE n:Assignment;

// 1d. Set ku_type for consistency
MATCH (n:Exercise)
SET n.ku_type = 'exercise';

// =============================================================================
// Step 2: Migrate HAS_ASSIGNMENT → HAS_EXERCISE relationship
// =============================================================================

MATCH (u:User)-[r:HAS_ASSIGNMENT]->(n:Exercise)
CREATE (u)-[r2:HAS_EXERCISE]->(n)
SET r2 = properties(r)
DELETE r;

// =============================================================================
// Step 3: Fix Submission ku_type 'assignment' → 'submission'
// 6 Submission nodes still have the old value from before the rename migration
// =============================================================================

MATCH (n:Ku)
WHERE n.ku_type = 'assignment'
SET n.ku_type = 'submission';

// =============================================================================
// Step 4: Remove stale journal_type property
// 2 nodes have journal_type='voice' left from before the voice-first refactoring
// =============================================================================

MATCH (n)
WHERE n.journal_type IS NOT NULL
REMOVE n.journal_type;

// =============================================================================
// Step 5: Add Ku.uid and Ku.ku_type indexes
// MEGA-QUERY and most Cypher patterns match on :Ku {uid: ...}
// Entity indexes exist but don't help when matching by :Ku label
// =============================================================================

CREATE INDEX ku_uid_idx IF NOT EXISTS FOR (n:Ku) ON (n.uid);
CREATE INDEX ku_type_idx IF NOT EXISTS FOR (n:Ku) ON (n.ku_type);

// =============================================================================
// Verification queries (run after all steps complete):
// =============================================================================
// MATCH (n:Assignment) RETURN count(n);           -- expect 0
// MATCH (n:KuProject) RETURN count(n);            -- expect 0
// MATCH (n) WHERE n.journal_type IS NOT NULL RETURN count(n);  -- expect 0
// MATCH (n:Ku) WHERE n.ku_type = 'assignment' RETURN count(n); -- expect 0
// MATCH (n:Exercise) RETURN count(n), collect(n.uid);          -- expect 1 node
// MATCH ()-[r:HAS_ASSIGNMENT]->() RETURN count(r);             -- expect 0
// MATCH ()-[r:HAS_KUPROJECT]->() RETURN count(r);              -- expect 0
// SHOW INDEXES YIELD name WHERE name IN ['ku_uid_idx', 'ku_type_idx'] RETURN name;
