// ============================================================================
// Migration: Assignment → Exercise
// Phase 3 of Ku Hierarchy Refactoring
// ============================================================================
//
// This migration converts :Assignment nodes to :Ku:Exercise nodes and
// renames the FULFILLS_PROJECT relationship to FULFILLS_EXERCISE.
//
// Run each step individually in Neo4j Browser.
// ============================================================================

// STEP 1: Add :Ku:Exercise labels to existing :Assignment nodes
// and set ku_type = 'exercise'
MATCH (a:Assignment)
SET a:Ku:Exercise, a.ku_type = 'exercise'
RETURN count(a) as nodes_updated;

// STEP 2: Rename FULFILLS_PROJECT → FULFILLS_EXERCISE relationships
// (Create new relationship, copy properties, delete old)
MATCH (submission)-[old:FULFILLS_PROJECT]->(exercise)
CREATE (submission)-[new:FULFILLS_EXERCISE]->(exercise)
SET new = properties(old)
DELETE old
RETURN count(new) as relationships_migrated;

// STEP 3: Update UID prefix from kp_ to ex_ (for Assignment nodes with kp_ prefix)
MATCH (e:Ku:Exercise)
WHERE e.uid STARTS WITH 'kp_'
SET e.uid = 'ex_' + substring(e.uid, 3)
RETURN count(e) as uids_updated;

// STEP 4: Also update any instruction-set UIDs (instructions:* format stays unchanged)
// These are instruction templates created by content_enrichment_service.
// They already have uid format like "instructions:default-report-formatting"
// No UID change needed for these.

// STEP 5: Remove the :Assignment label (One Path Forward — no dual labels)
MATCH (e:Assignment)
REMOVE e:Assignment
RETURN count(e) as labels_removed;

// STEP 6: Verify migration
// Should return 0 (no :Assignment nodes remaining)
MATCH (a:Assignment) RETURN count(a) as remaining_assignment_nodes;

// Should return all exercise nodes with correct structure
MATCH (e:Ku:Exercise {ku_type: 'exercise'})
RETURN e.uid as uid, e.name as name, e.scope as scope
ORDER BY e.created_at DESC
LIMIT 10;

// Should return all FULFILLS_EXERCISE relationships (and 0 FULFILLS_PROJECT)
MATCH ()-[r:FULFILLS_EXERCISE]->() RETURN count(r) as fulfills_exercise_count;
MATCH ()-[r:FULFILLS_PROJECT]->() RETURN count(r) as fulfills_project_count;
