// Migration: Derive HAS_LESSON relationships from shared KU references
// Date: 2026-03-15
//
// Creates (LS)-[:HAS_LESSON]->(Lesson) by finding LSs and Lessons
// that share KU references via CONTAINS_KNOWLEDGE/TRAINS_KU and USES_KU.
//
// This relationship enables LS progress tracking based on Lesson completion.
// Run once after deploying the LsProgressService feature.

MATCH (ls:Entity {entity_type: 'learning_step'})-[:CONTAINS_KNOWLEDGE|TRAINS_KU]->(ku:Entity)
MATCH (lesson:Entity {entity_type: 'lesson'})-[:USES_KU]->(ku)
WITH DISTINCT ls, lesson
MERGE (ls)-[:HAS_LESSON]->(lesson)
RETURN count(*) as relationships_created;
