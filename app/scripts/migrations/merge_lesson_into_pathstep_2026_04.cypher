// Migration: Merge Lesson INTO PathStep
// Date: 2026-04-01
// Context: Collapsing 4-level hierarchy (LP → PS → Lesson → Ku) to 3-level (LP → PS → Ku).
//          PathStep absorbs all Lesson capabilities. EntityType.LESSON is removed.
//
// What this does:
// 1. For standalone :Lesson nodes (no parent PathStep): relabel to :PathStep
// 2. For :Lesson nodes WITH a parent PathStep via HAS_LESSON:
//    - Copy body/content fields onto parent PathStep
//    - Move relationships (USES_KU, activity wiring, ORGANIZES, learning states) to PathStep
// 3. Remove all HAS_LESSON relationships
// 4. Remove orphaned Lesson nodes
// 5. Validate migration
//
// Run with: cypher-shell -f scripts/migrations/merge_lesson_into_pathstep_2026_04.cypher

// =============================================================================
// Step 1: Standalone Lessons (no parent PathStep via HAS_LESSON)
// Relabel directly to PathStep
// =============================================================================

MATCH (n:Lesson)
WHERE NOT ()-[:HAS_LESSON]->(n)
SET n:PathStep
REMOVE n:Lesson
SET n.entity_type = "path_step",
    n.mastery_threshold = COALESCE(n.mastery_threshold, 0.7),
    n.current_mastery = COALESCE(n.current_mastery, 0.0)
RETURN count(n) AS standalone_lessons_migrated;

// =============================================================================
// Step 2a: Parented Lessons — copy body/content fields to parent PathStep
// =============================================================================

MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)
SET ps.body = COALESCE(ps.body, lesson.body),
    ps.content = COALESCE(ps.content, lesson.content),
    ps.summary = COALESCE(ps.summary, lesson.summary),
    ps.word_count = COALESCE(ps.word_count, lesson.word_count),
    ps.learning_objectives = COALESCE(ps.learning_objectives, lesson.learning_objectives)
RETURN count(ps) AS pathsteps_with_content_copied;

// =============================================================================
// Step 2b: Move USES_KU relationships from Lesson to parent PathStep
// =============================================================================

MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)-[r:USES_KU]->(ku)
MERGE (ps)-[:USES_KU]->(ku)
DELETE r
RETURN count(r) AS uses_ku_moved;

// =============================================================================
// Step 2c: Move activity wiring relationships from Lesson to parent PathStep
// =============================================================================

// BUILDS_HABIT
MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)-[r:BUILDS_HABIT]->(target)
MERGE (ps)-[:BUILDS_HABIT]->(target)
DELETE r
RETURN count(r) AS builds_habit_moved;

// ASSIGNS_TASK
MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)-[r:ASSIGNS_TASK]->(target)
MERGE (ps)-[:ASSIGNS_TASK]->(target)
DELETE r
RETURN count(r) AS assigns_task_moved;

// SCHEDULES_EVENT
MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)-[r:SCHEDULES_EVENT]->(target)
MERGE (ps)-[:SCHEDULES_EVENT]->(target)
DELETE r
RETURN count(r) AS schedules_event_moved;

// SUPPORTS_GOAL
MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)-[r:SUPPORTS_GOAL]->(target)
MERGE (ps)-[:SUPPORTS_GOAL]->(target)
DELETE r
RETURN count(r) AS supports_goal_moved;

// GUIDED_BY_PRINCIPLE
MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)-[r:GUIDED_BY_PRINCIPLE]->(target)
MERGE (ps)-[:GUIDED_BY_PRINCIPLE]->(target)
DELETE r
RETURN count(r) AS guided_by_principle_moved;

// INFORMS_CHOICE
MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)-[r:INFORMS_CHOICE]->(target)
MERGE (ps)-[:INFORMS_CHOICE]->(target)
DELETE r
RETURN count(r) AS informs_choice_moved;

// =============================================================================
// Step 2d: Move ORGANIZES relationships (both directions)
// =============================================================================

// Outgoing ORGANIZES
MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)-[r:ORGANIZES]->(target)
MERGE (ps)-[nr:ORGANIZES]->(target)
ON CREATE SET nr = properties(r)
DELETE r
RETURN count(r) AS organizes_outgoing_moved;

// Incoming ORGANIZES
MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)<-[r:ORGANIZES]-(source)
MERGE (source)-[nr:ORGANIZES]->(ps)
ON CREATE SET nr = properties(r)
DELETE r
RETURN count(r) AS organizes_incoming_moved;

// =============================================================================
// Step 2e: Move user learning state relationships
// =============================================================================

// VIEWED
MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)<-[r:VIEWED]-(user)
MERGE (user)-[nr:VIEWED]->(ps)
ON CREATE SET nr = properties(r)
DELETE r
RETURN count(r) AS viewed_moved;

// IN_PROGRESS
MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)<-[r:IN_PROGRESS]-(user)
MERGE (user)-[nr:IN_PROGRESS]->(ps)
ON CREATE SET nr = properties(r)
DELETE r
RETURN count(r) AS in_progress_moved;

// MASTERED
MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)<-[r:MASTERED]-(user)
MERGE (user)-[nr:MASTERED]->(ps)
ON CREATE SET nr = properties(r)
DELETE r
RETURN count(r) AS mastered_moved;

// BOOKMARKED
MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)<-[r:BOOKMARKED]-(user)
MERGE (user)-[nr:BOOKMARKED]->(ps)
ON CREATE SET nr = properties(r)
DELETE r
RETURN count(r) AS bookmarked_moved;

// MARKED_AS_READ
MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)<-[r:MARKED_AS_READ]-(user)
MERGE (user)-[nr:MARKED_AS_READ]->(ps)
ON CREATE SET nr = properties(r)
DELETE r
RETURN count(r) AS marked_as_read_moved;

// =============================================================================
// Step 2f: Move incoming activity wiring (reverse direction)
// =============================================================================

// APPLIES_KNOWLEDGE (from activity domains to Lesson)
MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)<-[r:APPLIES_KNOWLEDGE]-(source)
MERGE (source)-[nr:APPLIES_KNOWLEDGE]->(ps)
ON CREATE SET nr = properties(r)
DELETE r
RETURN count(r) AS applies_knowledge_moved;

// REINFORCES_KNOWLEDGE
MATCH (ps:PathStep)-[:HAS_LESSON]->(lesson:Lesson)<-[r:REINFORCES_KNOWLEDGE]-(source)
MERGE (source)-[nr:REINFORCES_KNOWLEDGE]->(ps)
ON CREATE SET nr = properties(r)
DELETE r
RETURN count(r) AS reinforces_knowledge_moved;

// =============================================================================
// Step 3: Remove all HAS_LESSON relationships
// =============================================================================

MATCH ()-[r:HAS_LESSON]->()
DELETE r
RETURN count(r) AS has_lesson_removed;

// =============================================================================
// Step 4: Delete orphaned Lesson nodes (content already migrated)
// =============================================================================

MATCH (n:Lesson)
DETACH DELETE n
RETURN count(n) AS orphaned_lessons_deleted;

// =============================================================================
// Step 5: Validate — no :Lesson nodes should remain
// =============================================================================

MATCH (n:Lesson)
RETURN count(n) AS remaining_lesson_nodes;
// Expected: 0
