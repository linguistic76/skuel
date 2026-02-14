// ============================================================================
// Migration: Goal → Ku (February 2026)
// ============================================================================
// Phase 4 of Unified Ku Model migration (Activity Domains).
//
// Converts all :Goal nodes to :Ku nodes with ku_type='goal'.
//
// Changes:
//   1. :Goal nodes → :Ku label + ku_type='goal'
//   2. Status mapping: GoalStatus → KuStatus
//   3. Convert HAS_GOAL → HAS_KU relationships
//   4. Convert OWNS relationships (if any)
//   5. Verify no :Goal nodes remain
//
// Status mapping:
//   planned   → draft
//   active    → active
//   paused    → paused
//   achieved  → completed
//   cancelled → cancelled
//   archived  → archived
//
// Preconditions:
//   - Goal nodes exist with status property (GoalStatus values)
//   - Ku model already expanded with GOAL fields (Phase 1)
//   - UniversalNeo4jBackend supports default_filters (Phase 2)
//
// Safe to re-run: All steps use SET (idempotent) and conditional matching.
// ============================================================================

// --- Step 1: Convert :Goal nodes to :Ku with ku_type='goal' ---
MATCH (n:Goal)
SET n:Ku,
    n.ku_type = 'goal',
    n.status = CASE n.status
        WHEN 'planned' THEN 'draft'
        WHEN 'active' THEN 'active'
        WHEN 'paused' THEN 'paused'
        WHEN 'achieved' THEN 'completed'
        WHEN 'cancelled' THEN 'cancelled'
        WHEN 'archived' THEN 'archived'
        ELSE COALESCE(n.status, 'draft')
    END
REMOVE n:Goal
RETURN count(n) as goal_nodes_converted;

// --- Step 2: Convert HAS_GOAL → HAS_KU relationships ---
MATCH (u)-[old:HAS_GOAL]->(k:Ku {ku_type: 'goal'})
MERGE (u)-[:HAS_KU]->(k)
DELETE old
RETURN count(old) as has_goal_relationships_converted;

// --- Step 3: Convert OWNS relationships (if any) ---
MATCH (u:User)-[old:OWNS]->(k:Ku {ku_type: 'goal'})
WHERE NOT EXISTS { (u)-[:HAS_KU]->(k) }
MERGE (u)-[:HAS_KU]->(k)
RETURN count(old) as owns_relationships_verified;

// --- Step 4: Verify no :Goal nodes remain ---
MATCH (n:Goal)
RETURN count(n) as remaining_goal_nodes;

// --- Step 5: Count migrated goal nodes ---
MATCH (n:Ku {ku_type: 'goal'})
RETURN count(n) as total_goal_ku_nodes;
