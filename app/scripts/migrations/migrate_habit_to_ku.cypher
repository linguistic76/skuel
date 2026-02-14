// ============================================================================
// Migration: Habit → Ku (February 2026)
// ============================================================================
// Phase 4 of Unified Ku Model migration (Activity Domains).
//
// Converts all :Habit nodes to :Ku nodes with ku_type='habit'.
//
// Changes:
//   1. :Habit nodes → :Ku label + ku_type='habit'
//   2. Status mapping: HabitStatus → KuStatus (abandoned → cancelled)
//   3. Field rename: name → title (Ku uses 'title')
//   4. Enum field renames: category → habit_category, difficulty → habit_difficulty
//   5. Convert HAS_HABIT → HAS_KU relationships
//   6. Verify no :Habit nodes remain
//
// Status mapping:
//   active    → active
//   paused    → paused
//   completed → completed
//   abandoned → cancelled
//   archived  → archived
//
// Preconditions:
//   - Habit nodes exist with status property (HabitStatus values)
//   - Ku model already expanded with STREAK fields (Phase 1)
//   - UniversalNeo4jBackend supports default_filters (Phase 2)
//
// Safe to re-run: All steps use SET (idempotent) and conditional matching.
// ============================================================================

// --- Step 1: Convert :Habit nodes to :Ku with ku_type='habit' ---
// Also renames: name → title, category → habit_category, difficulty → habit_difficulty
MATCH (n:Habit)
SET n:Ku,
    n.ku_type = 'habit',
    n.title = COALESCE(n.title, n.name),
    n.habit_category = COALESCE(n.habit_category, n.category),
    n.habit_difficulty = COALESCE(n.habit_difficulty, n.difficulty),
    n.status = CASE n.status
        WHEN 'active' THEN 'active'
        WHEN 'paused' THEN 'paused'
        WHEN 'completed' THEN 'completed'
        WHEN 'abandoned' THEN 'cancelled'
        WHEN 'archived' THEN 'archived'
        ELSE COALESCE(n.status, 'active')
    END
REMOVE n:Habit, n.name
RETURN count(n) as habit_nodes_converted;

// --- Step 2: Clean up old field names (only if new fields were set from old) ---
// Remove old category/difficulty fields after migration to habit_category/habit_difficulty
MATCH (n:Ku {ku_type: 'habit'})
WHERE n.category IS NOT NULL AND n.habit_category IS NOT NULL
REMOVE n.category
RETURN count(n) as category_fields_cleaned;

MATCH (n:Ku {ku_type: 'habit'})
WHERE n.difficulty IS NOT NULL AND n.habit_difficulty IS NOT NULL
REMOVE n.difficulty
RETURN count(n) as difficulty_fields_cleaned;

// --- Step 3: Convert HAS_HABIT → HAS_KU relationships ---
MATCH (u)-[old:HAS_HABIT]->(k:Ku {ku_type: 'habit'})
MERGE (u)-[:HAS_KU]->(k)
DELETE old
RETURN count(old) as has_habit_relationships_converted;

// --- Step 4: Convert OWNS relationships (if any) ---
// Habits use OWNS relationship for ownership
MATCH (u:User)-[old:OWNS]->(k:Ku {ku_type: 'habit'})
WHERE NOT EXISTS { (u)-[:HAS_KU]->(k) }
MERGE (u)-[:HAS_KU]->(k)
RETURN count(old) as owns_relationships_verified;

// --- Step 5: Verify no :Habit nodes remain ---
MATCH (n:Habit)
RETURN count(n) as remaining_habit_nodes;

// --- Step 6: Count migrated habit nodes ---
MATCH (n:Ku {ku_type: 'habit'})
RETURN count(n) as total_habit_ku_nodes;
