// ============================================================================
// Migration: LS (Learning Step) → Ku (February 2026)
// ============================================================================
// Phase 3 of Unified Ku Model migration.
//
// Converts all :Ls nodes to :Ku nodes with ku_type='learning_step'.
// LS is shared curriculum content (no ownership relationships to convert).
//
// Changes:
//   1. :Ls nodes → :Ku label + ku_type='learning_step'
//   2. Status mapping: StepStatus → KuStatus
//   3. Field rename: difficulty → step_difficulty
//
// Preconditions:
//   - Ls nodes exist with status property (StepStatus values)
//   - Ku model already expanded with CURRICULUM_STRUCTURE fields (Phase 1)
//   - UniversalNeo4jBackend supports default_filters (Phase 2)
//
// Relationships preserved as-is (HAS_STEP, CONTAINS_KNOWLEDGE, etc.)
// — only node labels change, relationship types stay the same.
//
// Safe to re-run: All steps use SET (idempotent) and conditional matching.
// ============================================================================

// --- Step 1: Convert :Ls nodes to :Ku with ku_type='learning_step' ---
// Map StepStatus → KuStatus:
//   not_started → draft
//   in_progress → active
//   completed   → completed
//   mastered    → completed
//   archived    → archived

MATCH (n:Ls)
SET n:Ku,
    n.ku_type = 'learning_step',
    n.status = CASE n.status
        WHEN 'not_started' THEN 'draft'
        WHEN 'in_progress' THEN 'active'
        WHEN 'completed' THEN 'completed'
        WHEN 'mastered' THEN 'completed'
        WHEN 'archived' THEN 'archived'
        ELSE COALESCE(n.status, 'draft')
    END,
    n.step_difficulty = COALESCE(n.difficulty, n.step_difficulty)
REMOVE n:Ls, n.difficulty
RETURN count(n) as ls_nodes_converted;

// --- Step 2: Clean up completed boolean property ---
// Ku uses status='completed' instead of completed=true
// Ensure any completed=true nodes have status='completed', then remove the field
MATCH (n:Ku {ku_type: 'learning_step'})
WHERE n.completed = true AND n.status <> 'completed'
SET n.status = 'completed';

MATCH (n:Ku {ku_type: 'learning_step'})
WHERE n.completed IS NOT NULL
REMOVE n.completed
RETURN count(n) as completed_fields_cleaned;

// --- Step 3: Verify no :Ls nodes remain ---
MATCH (n:Ls)
RETURN count(n) as remaining_ls_nodes;
