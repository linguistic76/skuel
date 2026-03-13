// Migration: Cleanup stale Exercise nodes in Neo4j
// Date: 2026-03-13
// Context: Exercise label has 48 nodes, most are stale test artifacts from early
//          development (Feb 24-27), before the Ku→Article refactoring.
//
// Breakdown:
//   35 nodes with entity_type="ku" — ingestion test artifacts
//   12 nodes with entity_type="exercise" — some legitimate, some test data
//    1 node (jp.transcript_default) — orphan with null entity_type
//
// Run with: cat scripts/migrations/cleanup_stale_exercises_2026_03.cypher | cypher-shell -u neo4j -p <password>

// ============================================================================
// Step 1: Audit — count stale nodes before deletion (read-only)
// ============================================================================

// Exercise nodes by entity_type
MATCH (n:Exercise)
RETURN n.entity_type AS entity_type, count(n) AS count
ORDER BY count DESC;

// Exercise nodes with wrong entity_type (not 'exercise' or null)
MATCH (n:Exercise) WHERE n.entity_type <> 'exercise' OR n.entity_type IS NULL
RETURN n.uid AS uid, n.title AS title, n.entity_type AS entity_type;

// Exercise nodes with malformed UIDs (not starting with 'ex_')
MATCH (n:Exercise) WHERE NOT n.uid STARTS WITH 'ex_'
RETURN n.uid AS uid, n.title AS title, n.entity_type AS entity_type;

// ============================================================================
// Step 2: Delete stale Exercise nodes with wrong entity_type
// ============================================================================

// Remove 36 nodes: 35 with entity_type='ku' + 1 orphan with null entity_type
MATCH (n:Exercise) WHERE n.entity_type <> 'exercise' OR n.entity_type IS NULL
DETACH DELETE n
RETURN count(n) AS wrong_entity_type_deleted;

// ============================================================================
// Step 3: Delete known test exercises (entity_type='exercise' but test data)
// ============================================================================

// Remove test exercises by title pattern
MATCH (n:Exercise)
WHERE n.title CONTAINS 'test'
   OR n.title CONTAINS 'Transcripts 0'
   OR n.title CONTAINS 'instructions journal chatgpt.md'
DETACH DELETE n
RETURN count(n) AS test_exercises_deleted;

// ============================================================================
// Step 4: Verification
// ============================================================================

// Count remaining Exercise nodes
MATCH (n:Exercise)
RETURN count(n) AS remaining_exercises;

// Verify no entity_type='ku' Exercise nodes remain
MATCH (n:Exercise) WHERE n.entity_type = 'ku'
RETURN count(n) AS stale_ku_exercises;

// Verify no null entity_type Exercise nodes remain
MATCH (n:Exercise) WHERE n.entity_type IS NULL
RETURN count(n) AS null_entity_type_exercises;

// List remaining exercises for manual review
MATCH (n:Exercise)
RETURN n.uid AS uid, n.title AS title, n.entity_type AS entity_type
ORDER BY n.title;
