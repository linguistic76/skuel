// ============================================================================
// Migration: LP (Learning Path) → Ku (February 2026)
// ============================================================================
// Phase 3 of Unified Ku Model migration.
//
// Converts all :Lp nodes to :Ku nodes with ku_type='learning_path'.
// LP is shared curriculum content (no ownership relationships to convert).
//
// Changes:
//   1. :Lp nodes → :Ku label + ku_type='learning_path'
//   2. Field rename: name → title (Ku uses 'title' universally)
//   3. Field rename: goal → description (LP goal maps to Ku description)
//   4. Field rename: difficulty → step_difficulty (unified enum field)
//   5. Default status to 'draft' if not set
//
// Preconditions:
//   - Lp nodes exist with name property
//   - Ku model already expanded with CURRICULUM_STRUCTURE fields (Phase 1)
//   - UniversalNeo4jBackend supports default_filters (Phase 2)
//
// Relationships preserved as-is (HAS_STEP, ALIGNED_WITH_GOAL, etc.)
// — only node labels change, relationship types stay the same.
//
// Note: ULTIMATE_PATH relationships (User→Lp) will continue to work
// because they target specific nodes by UID, not by label.
//
// Safe to re-run: All steps use SET (idempotent) and conditional matching.
// ============================================================================

// --- Step 1: Convert :Lp nodes to :Ku with ku_type='learning_path' ---
// Rename name → title, goal → description, difficulty → step_difficulty
// Default status to 'draft' if not set

MATCH (n:Lp)
SET n:Ku,
    n.ku_type = 'learning_path',
    n.title = COALESCE(n.name, n.title),
    n.description = COALESCE(n.goal, n.description),
    n.step_difficulty = COALESCE(n.difficulty, n.step_difficulty),
    n.status = COALESCE(n.status, 'draft')
REMOVE n:Lp, n.name, n.goal, n.difficulty
RETURN count(n) as lp_nodes_converted;

// --- Step 2: Verify no :Lp nodes remain ---
MATCH (n:Lp)
RETURN count(n) as remaining_lp_nodes;
