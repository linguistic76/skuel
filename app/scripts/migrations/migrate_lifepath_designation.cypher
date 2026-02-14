// ============================================================================
// Migration: LifePath Designation to Unified Ku Model
// ============================================================================
//
// Phase 5 of Ku unification: LifePath is NOT a stored entity — it's a
// designation that elevates a Learning Path (ku_type='learning_path') to
// life-path status (ku_type='life_path'). The ULTIMATE_PATH relationship
// is the designation mechanism.
//
// Changes:
// 1. Set ku_type from 'learning_path' to 'life_path' on designated LPs
// 2. Move alignment scores from User node to ULTIMATE_PATH relationship
// 3. Clean up User node properties (alignment data now on relationship)
//
// Date: 2026-02-14
// ============================================================================

// Step 1: Update ku_type for designated life paths
// Find all Ku nodes designated via ULTIMATE_PATH and change ku_type
MATCH (u:User)-[:ULTIMATE_PATH]->(lp:Ku {ku_type: 'learning_path'})
SET lp.ku_type = 'life_path'
RETURN count(lp) AS life_paths_migrated;

// Step 2: Move alignment scores from User node to ULTIMATE_PATH relationship
MATCH (u:User)-[r:ULTIMATE_PATH]->(lp:Ku {ku_type: 'life_path'})
SET r.alignment_score = u.life_path_alignment_score,
    r.alignment_level = u.life_path_alignment_level,
    r.alignment_updated_at = u.life_path_alignment_updated_at,
    r.knowledge_alignment = u.knowledge_alignment,
    r.activity_alignment = u.activity_alignment,
    r.goal_alignment = u.goal_alignment,
    r.principle_alignment = u.principle_alignment,
    r.momentum = u.momentum
RETURN count(r) AS relationships_updated;

// Step 3: Clean up User node properties (alignment data now on relationship)
// Keep on User: vision_statement, vision_themes, vision_captured_at
// (these are about the user's words, not a specific LP)
MATCH (u:User)-[:ULTIMATE_PATH]->(lp:Ku {ku_type: 'life_path'})
REMOVE u.life_path_alignment_score,
       u.life_path_alignment_level,
       u.life_path_alignment_updated_at,
       u.knowledge_alignment,
       u.activity_alignment,
       u.goal_alignment,
       u.principle_alignment,
       u.momentum,
       u.life_path_uid
RETURN count(u) AS users_cleaned;

// ============================================================================
// Verification queries (run after migration)
// ============================================================================

// Verify: Count designated life paths
// MATCH (n:Ku {ku_type: 'life_path'}) RETURN count(n);

// Verify: Alignment scores on relationship
// MATCH (u:User)-[r:ULTIMATE_PATH]->(lp:Ku) RETURN u.uid, r.alignment_score, lp.uid;

// Verify: No stale properties on User nodes
// MATCH (u:User) WHERE u.life_path_uid IS NOT NULL RETURN count(u);
// Expected: 0
