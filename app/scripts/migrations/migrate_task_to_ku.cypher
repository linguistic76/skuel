// ============================================================================
// Migration: Task → Ku (February 2026)
// ============================================================================
// Phase 4 of Unified Ku Model migration (Activity Domains).
//
// Converts all :Task nodes to :Ku nodes with ku_type='task'.
//
// Changes:
//   1. :Task nodes → :Ku label + ku_type='task'
//   2. Status mapping: ActivityStatus → KuStatus (in_progress → active)
//   3. Convert HAS_TASK → HAS_KU relationships
//   4. Convert HAS_CHILD → HAS_CHILD (preserved, just label change on nodes)
//   5. Verify no :Task nodes remain
//
// Status mapping:
//   draft       → draft
//   scheduled   → scheduled
//   in_progress → active
//   paused      → paused
//   blocked     → blocked
//   completed   → completed
//   cancelled   → cancelled
//   postponed   → postponed
//
// Preconditions:
//   - Task nodes exist with status property (ActivityStatus values)
//   - Ku model already expanded with SCHEDULING/PROGRESS fields (Phase 1)
//   - UniversalNeo4jBackend supports default_filters (Phase 2)
//
// Safe to re-run: All steps use SET (idempotent) and conditional matching.
// ============================================================================

// --- Step 1: Convert :Task nodes to :Ku with ku_type='task' ---
MATCH (n:Task)
SET n:Ku,
    n.ku_type = 'task',
    n.status = CASE n.status
        WHEN 'in_progress' THEN 'active'
        WHEN 'draft' THEN 'draft'
        WHEN 'scheduled' THEN 'scheduled'
        WHEN 'paused' THEN 'paused'
        WHEN 'blocked' THEN 'blocked'
        WHEN 'completed' THEN 'completed'
        WHEN 'cancelled' THEN 'cancelled'
        WHEN 'postponed' THEN 'postponed'
        ELSE COALESCE(n.status, 'draft')
    END
REMOVE n:Task
RETURN count(n) as task_nodes_converted;

// --- Step 2: Convert HAS_TASK → HAS_KU relationships ---
MATCH (u)-[old:HAS_TASK]->(k:Ku {ku_type: 'task'})
MERGE (u)-[:HAS_KU]->(k)
DELETE old
RETURN count(old) as has_task_relationships_converted;

// --- Step 3: Convert OWNS relationships (if any) ---
// Tasks use OWNS relationship for ownership
MATCH (u:User)-[old:OWNS]->(k:Ku {ku_type: 'task'})
WHERE NOT EXISTS { (u)-[:HAS_KU]->(k) }
MERGE (u)-[:HAS_KU]->(k)
RETURN count(old) as owns_relationships_verified;

// --- Step 4: Verify no :Task nodes remain ---
MATCH (n:Task)
RETURN count(n) as remaining_task_nodes;

// --- Step 5: Count migrated task nodes ---
MATCH (n:Ku {ku_type: 'task'})
RETURN count(n) as total_task_ku_nodes;
